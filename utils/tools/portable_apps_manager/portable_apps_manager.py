# %% [markdown]
# # Portable Apps Manager
# Deploy, track, update and remove portable Windows apps published as GitHub releases or at a
# fixed download URL. Apps and their installed versions are kept in `portable_apps.ini` inside
# the root folder (default `~\Downloads\Programs`; change it per session in the Root field).
#
# **Prerequisites:** `pip install requests truststore ipywidgets`; 7-Zip installed for .7z / .7z.exe assets.
# `truststore` makes HTTPS verification use the Windows certificate store - without it, hosts behind
# the corporate TLS inspection fail with `CERTIFICATE_VERIFY_FAILED`.
#
# Run this notebook, or from code: `from utils.tools.portable_apps_manager.portable_apps_manager import show_gui; display(show_gui())`

# %%
import datetime
import html
import os
import re
import time
import traceback

from IPython.display import display

from utils.tools.portable_apps_manager import (CATALOG_PATH, CHECK_MODES, DEFAULT_ROOT, AppsConfig, AppSpec, InstallError,
                                       ManifestWriteError, PrerequisiteError, SourceError, check, finish, folder_missing, load_catalog,
                                       match_assets, parse_repo, prepare, probe_url, save_to_catalog, suggest_name,
                                       suggest_name_from_file, suggest_pattern, untrack, up_to_date)
from utils.tools.portable_apps_manager._sources import get_source
from utils.tools.portable_apps_manager import _pathlink

_SOURCE_LABELS = {'GitHub release': 'github', 'Direct URL': 'url'}
_VERSION_FROM = [   # (label, AppSpec.version_from) - see _installer.resolve_version
    ('Auto - version file if set, else top folder, else file name, else date', 'auto'),
    ('Version file in the archive', 'file'),
    ("Archive's top folder name (e.g. node-v26.13.0-win-x64)", 'top_folder'),
    ('Downloaded file name (e.g. ffmpeg-9.0.2-essentials_build.zip)', 'file_name'),
    ('Date (or the version in the redirect URL)', 'date'),
]

_POLICIES = {'Ask per app': 'ask', 'Keep all': 'keep', 'Remove all': 'remove'}
_NAME_RE = re.compile(r'^[\w.+\- ]+$')   # also the manifest file name: portable_apps.manifests/<name>.json
_GRAY, _GREEN, _ORANGE, _RED, _BLUE = '#888', '#2e7d32', '#e67e22', '#c0392b', '#1565c0'


def _mb(n: int) -> str:
    return f'{n / 1048576:.1f} MB'


def _guess_asset(names: list[str]) -> str | None:
    """Most likely Windows-x64 portable archive among the release assets."""
    def score(n):
        n = n.lower()
        return ((('win' in n) or n.endswith('.exe')) * 4 + any(k in n for k in ('x64', 'win64', 'amd64', '64-bit', 'x86_64')) * 2
                + ('portable' in n) * 2 + n.endswith(('.zip', '.7z')) - any(k in n for k in ('arm', 'win32', 'x86.', 'i686', 'setup', 'install', 'debug', 'symbols')) * 3)
    return max(names, key=score) if names else None


class PortableAppsGUI:
    def __init__(self, root: str = DEFAULT_ROOT):
        from utils.standalone.widget_utils import Widgets
        self.w = Widgets()
        self.w.show_widget_on_create = False
        self.cfg: AppsConfig | None = None
        self.latest = {}       # name -> (ReleaseInfo, Asset) from the last check
        self.status = {}       # name -> (text, color); overrides the computed status
        self.queue = []        # [(spec, is_new)] still to install/update
        self.pending = None    # (spec, is_new, plan) waiting for a stale-file decision
        self.form_mode = None  # 'add' | 'edit'
        self.form_release = None
        self.form_probe = None
        self._auto_name = ''
        self._add_path_after = {}   # name -> add bin to PATH once its first install finishes
        self._untrack_pending = []  # names waiting for the untrack PATH question
        self.row_cb = {}
        self._build(root)
        self.load_root()

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self, root):
        w = self.w
        lbl = {'description_width': '70px'}
        self.root_text = w.Text(desc='Root:', value=root, width='560px', style=lbl, placeholder='folder holding the portable apps')
        self.load_btn = w.Button(desc='Load', icon='folder-open', cb=lambda _: self.load_root(), width='90px')
        self.root_info = w.HTML()

        self.check_btn = w.Button(desc='Check all', icon='refresh', cb=lambda _: self._run(self.check_all), width='110px')
        self.upd_sel_btn = w.Button(desc='Update selected', icon='download', cb=lambda _: self.start_update(self._selected()), width='140px')
        self.upd_all_btn = w.Button(desc='Update all', icon='download', cb=lambda _: self.start_update(None), width='110px')
        self.force_cb = w.Checkbox(desc='Reinstall even if up to date', value=False, width='210px')
        self.policy_dd = w.Dropdown(desc='Stale files:', options=list(_POLICIES), value='Ask per app', width='210px', style={'description_width': '75px'})
        self.add_btn = w.Button(desc='Add app', icon='plus', cb=lambda _: self.open_form('add'), width='100px')

        self.table = w.GridBox(layout={'grid_template_columns': '30px 160px 160px 150px 150px 60px auto', 'grid_gap': '2px 8px', 'width': '100%'})
        self.path_cb = {}          # name -> PATH checkbox of the current table
        self.sel_all_cb = w.Checkbox(value=False, width='28px', cb=self._toggle_all)

        self.edit_btn = w.Button(desc='Edit', icon='pencil', cb=lambda _: self.open_form('edit'), width='80px')
        self.untrack_btn = w.Button(desc='Untrack', icon='eye-slash', cb=lambda _: self._run(self.untrack_selected, False), width='100px', tooltip='Remove from the ini; the folder stays on disk')
        self.delete_btn = w.Button(desc='Untrack & delete', icon='trash', cb=lambda _: self.confirm_delete(), width='150px', button_style='danger')
        self.catalog_btn = w.Button(desc='Save to catalog', icon='book', cb=lambda _: self._run(self.save_selected_to_catalog, False),
                                    width='140px', tooltip='Write the selected apps\' settings to apps_catalog.ini (git-tracked) for sharing')

        # add / edit form
        fl = {'description_width': '90px'}
        self.f_title = w.HTML()
        self.catalog = {}
        self.f_catalog = w.Dropdown(desc='From catalog:', width='590px', style=fl, cb=self._catalog_picked)
        self.f_catalog_note = w.HTML()
        self.catalog_box = w.VBox([self.f_catalog, self.f_catalog_note])
        self.f_source = w.ToggleButtons(options=list(_SOURCE_LABELS), value='GitHub release', cb=self._source_changed,
                                        style={'button_width': '130px'})
        self.f_repo = w.Text(desc='Repo:', width='460px', style=fl, placeholder='owner/name or https://github.com/owner/name')
        self.f_fetch = w.Button(desc='Fetch release', icon='cloud-download', cb=lambda _: self._run(self.fetch_release, False), width='130px')
        self.f_release = w.HTML()
        self.f_asset = w.Dropdown(desc='Asset:', width='590px', style=fl, cb=self._asset_changed)
        self.f_pattern = w.Text(desc='Pattern:', width='460px', style=fl, placeholder='glob, e.g. app-win64-*.zip, or re:<regex>', cb=self._pattern_changed)
        self.f_match = w.HTML()
        self.gh_box = w.VBox([w.HBox([self.f_repo, self.f_fetch]), self.f_release, self.f_asset,
                              w.HBox([self.f_pattern, self.f_match])])
        self.f_url = w.Text(desc='URL:', width='460px', style=fl, placeholder='https://.../app-latest-windows.zip')
        self.f_probe = w.Button(desc='Probe URL', icon='search', cb=lambda _: self._run(self.probe, False), width='130px')
        self.f_probe_info = w.HTML()
        self.f_check_by = w.Dropdown(desc='Check by:', width='590px', style=fl)
        self.f_version_from = w.Dropdown(desc='Version from:', options=_VERSION_FROM, value='auto', width='590px', style=fl,
                                         cb=self._version_from_changed)
        self.f_version_file = w.Text(desc='Version file:', width='590px', style=fl,
                                     placeholder='optional, e.g. source.properties:Pkg.Revision, or source.properties (finds a version key)')
        self.url_box = w.VBox([w.HBox([self.f_url, self.f_probe]), self.f_probe_info, self.f_check_by,
                               self.f_version_from, self.f_version_file],
                              layout={'display': 'none'})
        self.f_name = w.Text(desc='Name:', width='300px', style=fl, placeholder='ini section name')
        self.f_folder = w.Text(desc='Folder:', width='300px', style=fl, placeholder='fixed folder name under the root')
        self.f_bin = w.Text(desc='Bin:', width='300px', style=fl, placeholder='blank = auto-detect after install')
        self.f_preserve = w.Text(desc='Preserve:', width='590px', style=fl, placeholder='never overwrite/remove, comma-separated globs, e.g. *.ini, data/*')
        self.f_add_path = w.Checkbox(desc="Add the app's bin folder to the User PATH after install", value=False, width='590px')
        self.f_ok = w.Button(desc='Deploy & track', icon='check', button_style='success', cb=lambda _: self._run(self.submit_form, False), width='150px')
        self.f_cancel = w.Button(desc='Cancel', cb=lambda _: self.close_form(), width='90px')
        self.form = w.VBox([self.f_title, self.catalog_box, self.f_source, self.gh_box, self.url_box, self.f_name, self.f_folder,
                            self.f_bin, self.f_preserve, self.f_add_path, w.HBox([self.f_ok, self.f_cancel])],
                           layout={'border': '1px solid #ccc', 'padding': '6px', 'margin': '6px 0', 'display': 'none'})

        # stale / modified-file decision
        def select_all(sel, on):
            return lambda _: setattr(sel, 'value', tuple(v for _, v in sel.options) if on else ())
        self.d_title = w.HTML()
        self.d_stale_lbl = w.HTML()
        self.d_files = w.SelectMultiple(rows=10, width='100%')
        self.d_files.add_class('pau-mono')
        self.d_all = w.Button(desc='Remove all', cb=select_all(self.d_files, True), width='110px')
        self.d_none = w.Button(desc='Keep all', cb=select_all(self.d_files, False), width='100px')
        self.d_stale_box = w.VBox([self.d_stale_lbl, self.d_files, w.HBox([self.d_all, self.d_none])])
        self.d_mod_lbl = w.HTML()
        self.d_mod = w.SelectMultiple(rows=6, width='100%')
        self.d_mod.add_class('pau-mono')
        self.d_mod_all = w.Button(desc='Overwrite all', cb=select_all(self.d_mod, True), width='120px')
        self.d_mod_none = w.Button(desc='Keep all mine', cb=select_all(self.d_mod, False), width='120px')
        self.d_mod_box = w.VBox([self.d_mod_lbl, self.d_mod, w.HBox([self.d_mod_all, self.d_mod_none])])
        self.d_apply = w.Button(desc='Apply', icon='check', button_style='success', cb=lambda _: self._run(self.decide, False, 'apply'), width='100px')
        self.d_skip = w.Button(desc='Skip this app', cb=lambda _: self._run(self.decide, False, 'skip'), width='120px')
        self.d_cancel = w.Button(desc='Cancel all', cb=lambda _: self._run(self.decide, False, 'cancel'), width='100px')
        self.decision = w.VBox([self.d_title, self.d_stale_box, self.d_mod_box, w.HBox([self.d_apply, self.d_skip, self.d_cancel])],
                               layout={'border': f'1px solid {_ORANGE}', 'padding': '6px', 'margin': '6px 0', 'display': 'none'})

        # delete confirmation
        self.c_text = w.HTML()
        self.c_yes = w.Button(desc='Delete', icon='trash', button_style='danger', cb=lambda _: self._run(self.delete_selected, False), width='100px')
        self.c_no = w.Button(desc='Cancel', cb=lambda _: self._hide(self.confirm), width='90px')
        self.confirm = w.VBox([self.c_text, w.HBox([self.c_yes, self.c_no])],
                              layout={'border': f'1px solid {_RED}', 'padding': '6px', 'margin': '6px 0', 'display': 'none'})

        # untrack: the app's bin folder is in the User PATH - remove it too?
        self.u_text = w.HTML()
        self.u_remove = w.Button(desc='Untrack, remove from PATH', icon='eye-slash', cb=lambda _: self._run(self.finish_untrack, False, True), width='210px')
        self.u_keep = w.Button(desc='Untrack, keep in PATH', cb=lambda _: self._run(self.finish_untrack, False, False), width='180px')
        self.u_cancel = w.Button(desc='Cancel', cb=lambda _: self._hide(self.untrack_box), width='90px')
        self.untrack_box = w.VBox([self.u_text, w.HBox([self.u_remove, self.u_keep, self.u_cancel])],
                                  layout={'border': f'1px solid {_ORANGE}', 'padding': '6px', 'margin': '6px 0', 'display': 'none'})

        self.progress = w.IntProgress(value=0, min=0, max=1, width='400px')
        self.progress_lbl = w.Label()
        self.log_out = w.Output(layout={'border': '1px solid #eee', 'max_height': '260px', 'overflow': 'auto'})

        self.controls = [self.root_text, self.load_btn, self.check_btn, self.upd_sel_btn, self.upd_all_btn,
                         self.force_cb, self.policy_dd, self.add_btn, self.edit_btn, self.untrack_btn, self.delete_btn,
                         self.catalog_btn,
                         self.sel_all_cb]
        css = w.HTML('<style>.pau-mono select { font-family: monospace; }</style>')
        self.ui = w.VBox([
            css,
            w.HBox([self.root_text, self.load_btn]), self.root_info,
            w.HBox([self.check_btn, self.upd_sel_btn, self.upd_all_btn, self.force_cb, self.policy_dd, self.add_btn]),
            self.table,
            w.HBox([self.edit_btn, self.untrack_btn, self.delete_btn, self.catalog_btn]),
            self.form, self.decision, self.confirm, self.untrack_box,
            w.HBox([self.progress, self.progress_lbl]),
            self.log_out,
        ])

    # ── helpers ───────────────────────────────────────────────────────────────
    def log(self, msg: str, color: str | None = None):
        line = f'{datetime.datetime.now():%H:%M:%S}  {msg}'
        if color:
            self.log_out.append_display_data(_HTMLobj(f'<pre style="margin:0;color:{color}">{html.escape(line)}</pre>'))
        else:
            self.log_out.append_stdout(line + '\n')

    @staticmethod
    def _hide(box):
        box.layout.display = 'none'

    @staticmethod
    def _show(box):
        box.layout.display = ''

    def _busy(self, on: bool):
        self._is_busy = on
        for c in self.controls + list(self.row_cb.values()):
            c.disabled = on
        for c in self.path_cb.values():
            c.disabled = on or getattr(c, '_pam_locked', False)

    def _run(self, fn, lock: bool = True, *args):
        """Run a callback with controls disabled; log unexpected exceptions instead of losing them."""
        if lock:
            self._busy(True)
        try:
            fn(*args)
        except (SourceError, InstallError, PrerequisiteError, ValueError) as e:
            self.log(str(e), _RED)
        except Exception:
            self.log(traceback.format_exc(), _RED)
        finally:
            if lock and not self.pending:
                self._busy(False)

    def _selected(self) -> list[str]:
        return [n for n, cb in self.row_cb.items() if cb.value]

    def _still_tracked(self, names: list[str]) -> list[str]:
        """names minus the apps no longer in the ini (after a _reload), logging the dropped ones."""
        for n in names:
            if n not in self.cfg.apps:
                self.log(f'{n}: no longer in {self.cfg.path} - skipped', _ORANGE)
        return [n for n in names if n in self.cfg.apps]

    def _reload_selected(self) -> list[str]:
        """The selected apps, after re-reading the ini if it changed on disk."""
        sel = self._selected()
        self._reload()
        return self._still_tracked(sel)

    def _toggle_all(self, change):
        for cb in self.row_cb.values():
            cb.value = change['new']

    def _set_status(self, name, text, color=_GRAY):
        self.status[name] = (text, color)
        self.refresh_table()

    def _status_of(self, spec: AppSpec):
        if spec.name in self.status:
            return self.status[spec.name]
        if folder_missing(self.cfg, spec):
            return 'Missing on disk', _RED
        if not spec.is_installed:
            return 'Not installed', _GRAY
        if spec.name in self.latest:
            rel = self.latest[spec.name][0]
            current = up_to_date(spec, rel)
            if current is None:
                return 'Unknown - Update downloads and compares', _GRAY
            if current:
                return 'Up to date', _GREEN
            return f'Update available → {rel.version}', _ORANGE
        return 'Not checked', _GRAY

    def _progress_cb(self, asset):
        last = [0.0]
        def cb(done, total):
            now = time.monotonic()
            if now - last[0] < 0.2 and done < total:
                return
            last[0] = now
            self.progress.max = max(total, 1)
            self.progress.value = min(done, self.progress.max)
            self.progress_lbl.value = f'{asset.name}: {_mb(done)} / {_mb(total)}'
        return cb

    def _reset_progress(self):
        self.progress.value = 0
        self.progress_lbl.value = ''

    # ── root / table ──────────────────────────────────────────────────────────
    def load_root(self):
        self.cfg = AppsConfig(self.root_text.value.strip() or DEFAULT_ROOT).load()
        self.latest.clear()
        self.status.clear()
        self.row_cb.clear()
        if self.cfg.exists():
            self._root_info()
        else:
            self.root_info.value = (f'<span style="color:{_GRAY}">No <code>portable_apps.ini</code> in {html.escape(self.cfg.root)} yet '
                                    '— it is created when the first app is added.</span>')
        self.refresh_table()

    def _root_info(self):
        self.root_info.value = f'<code>{html.escape(self.cfg.path)}</code> — {len(self.cfg.apps)} app(s)'

    def _reload(self) -> bool:
        """Re-read portable_apps.ini when it changed on disk since it was last loaded or written here
        (edited by hand, or by another copy of the tool). Check results are dropped for apps that are
        gone or whose settings changed. Called at the start of every action."""
        if not self.cfg.changed_on_disk():
            return False
        recipe_of = lambda s: {k: v for k, v in s.to_section().items() if not k.startswith('installed_')}
        old = {n: recipe_of(s) for n, s in self.cfg.apps.items()}
        self.cfg.load()
        for n in set(self.latest) | set(self.status):
            if n not in self.cfg.apps or recipe_of(self.cfg.apps[n]) != old.get(n):
                self.latest.pop(n, None)
                self.status.pop(n, None)
        self.log(f'{self.cfg.path} changed on disk - reloaded ({len(self.cfg.apps)} app(s))', _BLUE)
        self._root_info()
        self.refresh_table()
        return True

    def refresh_table(self):
        w = self.w
        hdr = lambda t: w.HTML(f'<b>{t}</b>')
        cells = [self.sel_all_cb, hdr('App'), hdr('Folder'), hdr('Installed'), hdr('Latest'), hdr('PATH'), hdr('Status')]
        try:
            snap = _pathlink.Snapshot()
        except OSError as e:
            snap = None
            self.log(f'Could not read PATH: {e}', _RED)
        self.path_cb = {}
        for name in sorted(self.cfg.apps, key=str.lower):
            spec = self.cfg.apps[name]
            cb = self.row_cb.get(name) or w.Checkbox(value=False, width='28px')
            self.row_cb[name] = cb
            text, color = self._status_of(spec)
            latest = ''
            if name in self.latest:
                rel = self.latest[name][0]
                # same file as installed: show the installed version (e.g. v26.13.0) rather than the
                # pre-download stand-in (a Last-Modified date)
                latest = spec.installed_version if up_to_date(spec, rel) else rel.version
            cells += [cb,
                      w.HTML(f'<span title="{html.escape(spec.origin)}">{html.escape(name)}</span>'),
                      w.HTML(html.escape(spec.folder)),
                      w.HTML(html.escape(spec.installed_version or '—')),
                      w.HTML(html.escape(latest)),
                      self._path_cell(spec, snap),
                      w.HTML(f'<span style="color:{color}">{html.escape(text)}</span>')]
        for gone in set(self.row_cb) - set(self.cfg.apps):
            del self.row_cb[gone]
        if not self.cfg.apps:
            cells += [w.HTML(''), w.HTML(f'<i style="color:{_GRAY}">No apps tracked - use "Add app".</i>')] + [w.HTML('')] * 5
        self.table.children = cells

    def _path_cell(self, spec: AppSpec, snap):
        """Checkbox: ticked = the app's bin folder is in PATH now. Disabled when there's no bin, the
        folder is missing, or the entry is in the System PATH (User PATH edits can't change that)."""
        folder = _pathlink.bin_dir(self.cfg.root, spec)
        state = snap.state(folder) if snap else 'n/a'
        tip = {'user': f'In User PATH: {folder}', 'system': f'In System PATH (read-only here): {folder}',
               'none': f'Not in PATH: {folder}', 'n/a': 'No bin folder set (Edit to set one)'}[state]
        if state == 'none' and folder and not os.path.isdir(folder):
            state, tip = 'n/a', f'bin folder not found: {folder}'
        cb = self.w.Checkbox(value=state in ('user', 'system'), width='50px', tooltip=tip, description_tooltip=tip)
        cb._pam_locked = state in ('system', 'n/a')
        cb.disabled = cb._pam_locked or getattr(self, '_is_busy', False)
        cb.observe(lambda ch, n=spec.name: self._run(self.toggle_path, True, n, ch['new']), 'value')
        self.path_cb[spec.name] = cb
        return cb

    # ── check / update ────────────────────────────────────────────────────────
    def check_all(self):
        self._reload()
        for name, spec in sorted(self.cfg.apps.items()):
            self.status.pop(name, None)
            try:
                self.latest[name] = check(spec)
            except (SourceError, PrerequisiteError) as e:
                self.latest.pop(name, None)
                self.status[name] = ('Error - see log', _RED)
                self.log(f'{name}: {e}', _RED)
                if 'rate limit' in str(e):
                    break
            self.refresh_table()
        self.log(f'Checked {len(self.cfg.apps)} app(s).')

    def start_update(self, names: list[str] | None):
        """names = None: every tracked app (as the ini is now)."""
        self._reload()
        names = list(self.cfg.apps) if names is None else self._still_tracked(names)
        if not names:
            self.log('Select at least one app.', _ORANGE)
            return
        self.queue = [(self.cfg.apps[n], False) for n in names]
        self._busy(True)
        self._run(self._continue, False)

    def _continue(self):
        try:
            while self.queue:
                spec, is_new = self.queue.pop(0)
                if not is_new:   # take the app's settings as the ini has them now
                    self._reload()
                    if not self._still_tracked([spec.name]):
                        continue
                    spec = self.cfg.apps[spec.name]
                if self._process(spec, is_new) == 'paused':
                    return
        finally:
            if not self.pending:
                self.queue.clear()
                self._reset_progress()
                self._busy(False)
                self.refresh_table()

    def _process(self, spec: AppSpec, is_new: bool):
        name = spec.name
        p = None
        try:
            if is_new and name in self.latest:
                release, asset = self.latest[name]
            else:
                release, asset = self.latest[name] = check(spec)
            skip_current = not is_new and not self.force_cb.value and not folder_missing(self.cfg, spec)
            if skip_current and up_to_date(spec, release):
                self.status.pop(name, None)
                self.log(f'{name}: up to date ({spec.installed_version})')
                return
            self._set_status(name, f'Downloading {release.version}…', _BLUE)
            p = prepare(self.cfg, spec, release, asset, self._progress_cb(asset))
            if skip_current and p.marker == spec.installed_marker:   # check_by = download: same file content
                p.cleanup()
                self.status[name] = ('Up to date', _GREEN)
                self.log(f'{name}: downloaded file is identical to the installed one ({spec.installed_version})')
                return
            self.log(f'{name}: {asset.name} → {p.summary()}')
            in_use = [r for r in p.locked if r not in p.stale and r not in p.modified]   # those two can be kept
            if in_use:
                p.cleanup()
                self._set_status(name, 'Needs action - close the program', _RED)
                self.log(f'{name}: files in use, close the program and retry:\n  ' + '\n  '.join(in_use), _RED)
                return
            policy = _POLICIES[self.policy_dd.value]
            if (p.stale or p.modified) and policy == 'ask':
                self.pending = (spec, is_new, p)
                need = [f'{len(p.stale)} stale'] * bool(p.stale) + [f'{len(p.modified)} modified'] * bool(p.modified)
                self._set_status(name, f'Needs action - {" + ".join(need)} file(s)', _ORANGE)
                self._show_decision()
                return 'paused'
            # files edited since the last install are never removed / overwritten without asking
            remove = [r for r in p.stale if r not in p.locked and r not in p.edited] if policy == 'remove' else []
            self._finish(spec, p, remove)
        except (SourceError, InstallError, OSError, ValueError) as e:
            if p:
                p.cleanup()
            self._set_status(name, 'Error - see log', _RED)
            self.log(f'{name}: {e}', _RED)

    def _finish(self, spec, p, remove, overwrite=()):
        try:
            finish(self.cfg, spec, p, remove, overwrite)
        except ManifestWriteError as e:   # installed and recorded; only the manifest write failed
            self.log(str(e), _RED)
        self.status.pop(spec.name, None)
        if spec.name in self.latest and up_to_date(spec, self.latest[spec.name][0]) is None:
            self.status[spec.name] = ('Up to date (as of this download)', _GREEN)   # check_by = download
        kept = len(p.stale) - len(remove)
        mine = [r for r in p.modified if r not in set(overwrite)]
        self.log(f'{spec.name}: installed {p.version} into {spec.folder_path(self.cfg.root)}'
                 + (f'; removed {len(remove)} stale file(s)' if remove else '') + (f'; kept {kept} stale file(s)' if kept else '')
                 + (f'; overwrote {len(overwrite)} modified file(s)' if overwrite else ''), _GREEN)
        if mine:
            self.log(f'{spec.name}: kept {len(mine)} locally modified file(s) (the new release has its own version):\n  '
                     + '\n  '.join(mine), _ORANGE)
        if self._add_path_after.pop(spec.name, False):
            self._path_update(spec.name, add=[_pathlink.bin_dir(self.cfg.root, spec)])
        self._root_info()
        self.refresh_table()

    def _show_decision(self):
        spec, _, p = self.pending
        locked = set(p.locked)
        note = lambda r: (('   (modified since install)' if r in p.edited else '')
                          + ('   (in use - keep, or close the program)' if r in locked else ''))
        self.d_title.value = (f'<b>{html.escape(spec.name)}</b> {html.escape(p.version)}: {html.escape(p.summary())}.<br>'
                              f'Folder: <code>{html.escape(p.dest)}</code> (Ctrl/Shift+click to select).')
        self.d_stale_lbl.value = (f'{len(p.stale)} file(s) are not in the new release. '
                                  '<b>Highlighted files will be removed</b>, the rest kept.')
        self.d_files.options = [(r + note(r), r) for r in p.stale]
        self.d_files.value = ()
        self.d_mod_lbl.value = (f'{len(p.modified)} file(s) differ from what the last install wrote (edited, or not written by it), '
                                'and the new release has its own version. <b>Highlighted files will be overwritten</b>, the rest kept.')
        self.d_mod.options = [(r + note(r), r) for r in p.modified]
        self.d_mod.value = ()
        (self._show if p.stale else self._hide)(self.d_stale_box)
        (self._show if p.modified else self._hide)(self.d_mod_box)
        self._show(self.decision)

    def decide(self, action: str):
        spec, is_new, p = self.pending
        if action == 'apply':
            try:
                self._finish(spec, p, list(self.d_files.value), list(self.d_mod.value))
            except (InstallError, OSError) as e:
                # most likely a file still in use: keep the decision panel open so the user can retry
                self.log(f'{spec.name}: {e}', _RED)
                return
        else:
            p.cleanup()
            self._set_status(spec.name, 'Skipped', _GRAY)
            self.log(f'{spec.name}: skipped')
            if action == 'cancel':
                self.queue.clear()
        self.pending = None
        self._hide(self.decision)
        self._continue()

    # ── add / edit ────────────────────────────────────────────────────────────
    def open_form(self, mode: str):
        if mode == 'edit':
            sel = self._reload_selected()
            if len(sel) != 1:
                self.log('Select exactly one app to edit.', _ORANGE)
                return
            spec = self.cfg.apps[sel[0]]
        self.form_mode, self.form_release, self.form_probe, self._auto_name = mode, None, None, ''
        for t in (self.f_repo, self.f_pattern, self.f_url, self.f_version_file, self.f_name, self.f_folder,
                  self.f_bin, self.f_preserve):
            t.value = ''
        self.f_asset.options, self.f_check_by.options = [], []
        self.f_release.value = self.f_match.value = self.f_probe_info.value = ''
        self.f_version_from.value = 'auto'
        self.f_catalog_note.value = ''
        if mode == 'add':
            self.f_title.value = '<b>Add app</b> - deploy a GitHub release asset or a download URL into a fixed folder and track it'
            self.f_ok.description = 'Deploy & track'
            self.catalog = load_catalog()
            self.f_catalog.options = [('(none - fill in below)', '')] + [
                (f'{n}   ({e.spec.source}: {e.spec.origin})', n) for n, e in sorted(self.catalog.items(), key=lambda kv: kv[0].lower())]
            self.f_catalog.value = ''
            self.f_add_path.value = False
            self._show(self.f_add_path)
            self._show(self.catalog_box)
        else:
            self.f_title.value = f'<b>Edit {html.escape(spec.name)}</b> (source, name and folder are fixed - untrack and re-add to change them)'
            self.f_ok.description = 'Save'
            self._hide(self.catalog_box)
            self._hide(self.f_add_path)   # PATH is toggled in the table's PATH column for tracked apps
            self._fill_form(spec)
        for t in (self.f_source, self.f_repo, self.f_fetch, self.f_url, self.f_probe, self.f_name, self.f_folder):
            t.disabled = mode == 'edit'
        self._source_changed()
        self._version_from_changed()
        self._hide(self.confirm)
        self._show(self.form)
        if mode == 'edit':
            self._run(self._fetch_for, False, spec)

    def _fill_form(self, spec: AppSpec):
        self.f_source.value = next(k for k, v in _SOURCE_LABELS.items() if v == spec.source)
        self.f_repo.value, self.f_pattern.value = spec.repo, spec.asset
        self.f_url.value, self.f_version_file.value = spec.url, spec.version_file
        self.f_version_from.value = spec.version_from or 'auto'
        self.f_name.value, self.f_folder.value = spec.name, spec.folder
        self.f_bin.value, self.f_preserve.value = spec.bin, ', '.join(spec.preserve)
        self._source_changed()
        self._version_from_changed()

    def _fetch_for(self, spec: AppSpec):
        """Fetch the release / probe the URL for a filled-in form, keeping spec's own choices."""
        if spec.source == 'github':
            self.fetch_release()
        else:
            self.probe()
            if spec.check_by in [v for _, v in self.f_check_by.options]:
                self.f_check_by.value = spec.check_by

    def _catalog_picked(self, change=None):
        name = self.f_catalog.value
        if self.form_mode != 'add' or not name:
            self.f_catalog_note.value = ''
            return
        e = self.catalog[name]
        self._fill_form(e.spec)
        self.f_add_path.value = e.add_to_path
        self.f_catalog_note.value = f'<span style="color:{_GRAY}">{html.escape(e.note)}</span>' if e.note else ''
        self._run(self._fetch_for, False, e.spec)

    def _form_source(self) -> str:
        return _SOURCE_LABELS[self.f_source.value]

    def _version_from_changed(self, change=None):
        # the version file is only read for 'file' and 'auto'
        self.f_version_file.disabled = self.f_version_from.value not in ('auto', 'file')

    def _source_changed(self, change=None):
        github = self._form_source() == 'github'
        (self._show if github else self._hide)(self.gh_box)
        (self._hide if github else self._show)(self.url_box)

    def probe(self):
        self.f_probe_info.value = 'Probing…'
        try:
            p = self.form_probe = probe_url(self.f_url.value)
        except SourceError as e:
            self.f_probe_info.value = f'<span style="color:{_RED}">{html.escape(str(e))}</span>'
            return
        row = lambda k, v, ok=True: (f'<tr><td style="padding-right:12px">{k}</td>'
                                     f'<td style="color:{_GREEN if ok else _GRAY}">{html.escape(v) if v else "(not sent)"}</td></tr>')
        self.f_probe_info.value = (
            '<table style="font-size:90%">'
            + row('File', f'{p.filename}  ({_mb(p.size)})' if p.size else p.filename)
            + row('Redirects to', p.final_url if p.final_url != p.url else '(no redirect)', p.final_url != p.url)
            + row('Version in URL', p.url_version, bool(p.url_version))
            + row('ETag', p.etag, bool(p.etag)) + row('Last-Modified', p.last_modified, bool(p.last_modified))
            + '</table>')
        self.f_check_by.options = [(f'{m} - {CHECK_MODES[m]}', m) for m in p.modes()]
        self.f_check_by.value = p.modes()[0]
        if self.form_mode == 'add':
            auto = suggest_name_from_file(p.filename)
            for t in (self.f_name, self.f_folder):
                if not t.value or t.value == self._auto_name:
                    t.value = auto
            self._auto_name = auto

    def close_form(self):
        self._hide(self.form)
        self.form_mode = None

    def fetch_release(self):
        repo = parse_repo(self.f_repo.value)
        self.f_repo.value = repo
        self.f_release.value = 'Fetching…'
        try:
            rel = self.form_release = get_source('github').latest_release(repo)
        except SourceError as e:
            self.f_release.value = f'<span style="color:{_RED}">{html.escape(str(e))}</span>'
            return
        self.f_release.value = (f'Latest release <b>{html.escape(rel.version)}</b> ({rel.published_at[:10]}), '
                                f'{len(rel.assets)} asset(s) - <a href="{html.escape(rel.html_url)}" target="_blank">release page</a>')
        keep_pattern = self.f_pattern.value
        self.f_asset.options = [(f'{a.name}   ({_mb(a.size)})', a.name) for a in rel.assets]
        hits = match_assets(keep_pattern, rel.assets) if keep_pattern else []
        self.f_asset.value = hits[0].name if len(hits) == 1 else _guess_asset([a.name for a in rel.assets])
        if keep_pattern:   # edit: don't let the dropdown's change handler replace the saved pattern
            self.f_pattern.value = keep_pattern
            self._pattern_changed()
        self._suggest_name()

    def _asset_changed(self, change=None):
        if self.form_release and self.f_asset.value:
            self.f_pattern.value = suggest_pattern(self.f_asset.value, self.form_release.version)
            self._pattern_changed()
            self._suggest_name()

    def _suggest_name(self):
        """Fill name/folder from the repo + chosen asset, unless the user has typed their own."""
        if self.form_mode != 'add' or not self.form_release:
            return
        auto = suggest_name(self.f_repo.value, self.f_asset.value)
        for t in (self.f_name, self.f_folder):
            if not t.value or t.value == self._auto_name:
                t.value = auto
        self._auto_name = auto

    def _pattern_changed(self, change=None):
        if not self.form_release or not self.f_pattern.value:
            self.f_match.value = ''
            return
        try:
            hits = match_assets(self.f_pattern.value, self.form_release.assets)
        except re.error as e:
            self.f_match.value = f'<span style="color:{_RED}">bad regex: {html.escape(str(e))}</span>'
            return
        if len(hits) == 1:
            self.f_match.value = f'<span style="color:{_GREEN}">✓ {html.escape(hits[0].name)}</span>'
        else:
            self.f_match.value = f'<span style="color:{_RED}">matches {len(hits)} assets - must match exactly 1</span>'

    def _form_release(self, spec: AppSpec):
        """(ReleaseInfo, Asset) for the form's current inputs; ValueError if not ready/valid."""
        if spec.source == 'github':
            if not self.form_release:
                raise ValueError('Fetch the release first.')
            hits = match_assets(spec.asset, self.form_release.assets)
            if len(hits) != 1:
                raise ValueError(f'Pattern "{spec.asset}" matches {len(hits)} assets - it must match exactly 1.')
            return self.form_release, hits[0]
        if not self.form_probe:
            raise ValueError('Probe the URL first.')
        src = get_source('url')
        release = src.release_from_probe(spec, self.form_probe)
        return release, src.resolve(spec, release)

    def submit_form(self):
        preserve = [g.strip() for g in self.f_preserve.value.split(',') if g.strip()]
        if self.form_mode == 'edit':
            self._reload()   # build on the app's settings as the ini has them now
            if self.f_name.value not in self.cfg.apps:
                raise ValueError(f'{self.f_name.value}: no longer in {self.cfg.path} - nothing saved.')
            spec = self.cfg.apps[self.f_name.value]
            edited = AppSpec(**{**spec.__dict__, 'asset': self.f_pattern.value.strip(),
                                'check_by': self.f_check_by.value or spec.check_by,
                                'version_from': self.f_version_from.value if spec.source == 'url' else '',
                                'version_file': self.f_version_file.value.strip(),
                                'bin': self.f_bin.value.strip(), 'preserve': preserve})
            self.latest[spec.name] = self._form_release(edited)   # validates before saving
            self.cfg.save_app(edited)
            self.log(f'{spec.name}: saved', _GREEN)
            old_dir, new_dir = _pathlink.bin_dir(self.cfg.root, spec), _pathlink.bin_dir(self.cfg.root, edited)
            if old_dir != new_dir and _pathlink.Snapshot().state(old_dir) == 'user':   # bin changed: swap the PATH entry
                self._path_update(spec.name, add=[new_dir] if new_dir else [], remove=[old_dir])
            self.close_form()
            self.refresh_table()
            return
        name, folder = self.f_name.value.strip(), self.f_folder.value.strip()
        if not _NAME_RE.match(name) or name.strip(' .') != name:
            raise ValueError('Name: letters, digits, space, . _ + - only (not starting/ending with a space or dot).')
        if not _NAME_RE.match(folder) or folder in ('.', '..'):
            raise ValueError('Folder: a single folder name (letters, digits, space, . _ + -).')
        common = dict(name=name, folder=folder, bin=self.f_bin.value.strip(), preserve=preserve)
        if self._form_source() == 'github':
            spec = AppSpec(**common, source='github', repo=self.f_repo.value, asset=self.f_pattern.value.strip())
        else:
            spec = AppSpec(**common, source='url', url=self.form_probe.url if self.form_probe else self.f_url.value.strip(),
                           check_by=self.f_check_by.value or '', version_from=self.f_version_from.value,
                           version_file=self.f_version_file.value.strip())
        if spec.version_from == 'file' and not spec.version_file:
            raise ValueError('Version from = version file, but no version file is set.')
        release_asset = self._form_release(spec)
        self._reload()
        clash = AppsConfig(self.cfg.root)
        clash.apps = dict(self.cfg.apps)
        clash.add(spec)    # raises on duplicate name / folder, before anything is downloaded
        self.close_form()
        self.latest[name] = release_asset
        self._add_path_after[name] = self.f_add_path.value
        self.queue = [(spec, True)]
        self._busy(True)
        self._continue()

    # ── catalog ───────────────────────────────────────────────────────────────
    def save_selected_to_catalog(self):
        sel = self._reload_selected()
        if not sel:
            self.log('Select at least one app.', _ORANGE)
            return
        snap = _pathlink.Snapshot()
        for name in sel:
            spec = self.cfg.apps[name]
            on_path = snap.state(_pathlink.bin_dir(self.cfg.root, spec)) in ('user', 'system')
            replaced = save_to_catalog(spec, add_to_path=on_path)
            self.log(f'{name}: {"updated in" if replaced else "added to"} the catalog (add_to_path = {on_path})', _GREEN)
        self.log(f'Catalog: {CATALOG_PATH} - commit it to share; add or edit a "note" there to explain the choices.')

    # ── PATH ──────────────────────────────────────────────────────────────────
    def _path_update(self, name: str, add=(), remove=()):
        """One User PATH write (backup first) via env_path_editor; logs what changed."""
        added, removed = _pathlink.update(add=[f for f in add if f], remove=[f for f in remove if f])
        for e in added:
            self.log(f'{name}: added to the User PATH: {e}', _GREEN)
        for e in removed:
            self.log(f'{name}: removed from the User PATH: {e}', _GREEN)
        if added or removed:
            self.log(_pathlink.RESTART_NOTE)
        else:
            self.log(f'{name}: User PATH already as wanted')

    def toggle_path(self, name: str, on: bool):
        self._reload()
        if not self._still_tracked([name]):
            self.refresh_table()
            return
        folder = _pathlink.bin_dir(self.cfg.root, self.cfg.apps[name])
        try:
            self._path_update(name, add=[folder] if on else [], remove=[] if on else [folder])
        finally:
            self.refresh_table()   # the checkbox always shows the real PATH, also after an error

    # ── untrack / delete ──────────────────────────────────────────────────────
    def untrack_selected(self):
        sel = self._reload_selected()
        if not sel:
            self.log('Select at least one app.', _ORANGE)
            return
        snap = _pathlink.Snapshot()
        in_path = [(n, _pathlink.bin_dir(self.cfg.root, self.cfg.apps[n])) for n in sel]
        in_path = [(n, f) for n, f in in_path if snap.state(f) == 'user']
        self._untrack_pending = sel
        if not in_path:
            self.finish_untrack(False)
            return
        items = ''.join(f'<li>{html.escape(n)}: <code>{html.escape(f)}</code></li>' for n, f in in_path)
        self.u_text.value = (f'<b>Untrack {", ".join(html.escape(n) for n in sel)}</b> (folders are kept).<br>'
                             f'These bin folders are in your User PATH - remove them too?<ul>{items}</ul>')
        self._hide(self.form)
        self._hide(self.confirm)
        self._show(self.untrack_box)

    def finish_untrack(self, remove_path: bool):
        self._hide(self.untrack_box)
        names, self._untrack_pending = self._untrack_pending, []
        self._reload()
        names = self._still_tracked(names)
        if remove_path:
            folders = [_pathlink.bin_dir(self.cfg.root, self.cfg.apps[n]) for n in names]
            self._path_update(', '.join(names), remove=folders)
        for name in names:
            untrack(self.cfg, name)
            self.latest.pop(name, None)
            self.status.pop(name, None)
            self.log(f'{name}: untracked (folder kept)')
        self.refresh_table()

    def confirm_delete(self):
        sel = self._reload_selected()
        if not sel:
            self.log('Select at least one app.', _ORANGE)
            return
        items = ''.join(f'<li>{html.escape(n)}: <code>{html.escape(self.cfg.apps[n].folder_path(self.cfg.root))}</code></li>' for n in sel)
        self.c_text.value = f'<b>Untrack and permanently delete these folders?</b><ul>{items}</ul>'
        self._hide(self.form)
        self._show(self.confirm)

    def delete_selected(self):
        self._hide(self.confirm)
        gone = []   # bin folders of deleted apps: their PATH entries would point nowhere
        for name in self._reload_selected():
            folder = _pathlink.bin_dir(self.cfg.root, self.cfg.apps[name])
            try:
                untrack(self.cfg, name, delete_folder=True)
                self.latest.pop(name, None)
                self.status.pop(name, None)
                self.log(f'{name}: untracked and folder deleted', _GREEN)
                gone.append((name, folder))
            except (InstallError, OSError) as e:
                self.log(f'{name}: {e}', _RED)
        snap = _pathlink.Snapshot()
        gone = [(n, f) for n, f in gone if snap.state(f) == 'user']
        if gone:
            self._path_update(', '.join(n for n, _ in gone), remove=[f for _, f in gone])
        self.refresh_table()


def _HTMLobj(s):
    from IPython.display import HTML
    return HTML(s)


def show_gui(root: str = DEFAULT_ROOT):
    """Build the updater UI and return its top-level widget (for embedding, e.g. tools_launcher)."""
    return PortableAppsGUI(root).ui


# %%
if __name__ == '__main__':
    display(show_gui())
