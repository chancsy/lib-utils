# %% [markdown]
# # Env Path Editor
# View, check and edit the Windows **User** and **System** PATH (read straight from the registry,
# entries kept exactly as written). Entries are flagged when empty, relative, using an unknown
# `%VARIABLE%`, pointing to a folder that doesn't exist, duplicated (same expanded absolute path),
# or - for User entries - already in the System PATH (System is searched first, so the User copy is
# never used).
#
# Edits are kept in memory until **Save**. The User PATH needs no admin rights; the System PATH is
# read-only unless Jupyter runs as administrator. Programs started after saving see the new PATH;
# already-open terminals, VS Code and Jupyter keep the old one until restarted.
#
# Run this notebook, or from code: `from utils.tools.env_path_editor.env_path_editor import show_gui; display(show_gui())`

# %%
import datetime
import html
import os
import threading
import traceback
from collections import Counter

from IPython.display import display

from utils.tools.env_path_editor import (BACKUP_DIR, SYSTEM, USER, PathWriteError, Scope, backup, broadcast_change,
                                       check_entries, is_admin, normalize, read_raw, remove_duplicates, split, write)

_GRAY, _GREEN, _ORANGE, _RED, _BLUE = '#888', '#2e7d32', '#e67e22', '#c0392b', '#1565c0'


class EnvPathEditorGUI:
    def __init__(self, user_scope: Scope = USER, system_scope: Scope = SYSTEM):
        from utils.standalone.widget_utils import Widgets
        self.w = Widgets()
        self.w.show_widget_on_create = False
        self.scopes = {'User': user_scope, 'System': system_scope}
        self.admin = is_admin()
        self.loaded = {}     # scope name -> raw value at load (to detect outside changes on save)
        self.entries = {}    # scope name -> working list of entries
        self.selected = set()
        self._syncing = False   # True while refresh() sets widget values (their callbacks then do nothing)
        self._build()
        self.reload()

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self):
        w = self.w
        self.header = w.HTML()
        self.scope_tb = w.ToggleButtons(options=['User', 'System'], value='User', style={'button_width': '120px'},
                                        tooltips=[s.location for s in self.scopes.values()],
                                        cb=lambda ch: self._run(self._scope_changed, ch))
        self.scope_info = w.HTML()
        self.table = w.GridBox(layout={'grid_template_columns': '28px 34px minmax(220px, 3fr) minmax(160px, 2fr) minmax(160px, 1.3fr)',
                                       'grid_gap': '1px 8px', 'width': '100%'})
        self.sel_all_cb = w.Checkbox(value=False, width='26px', cb=lambda ch: self._run(self._toggle_all, ch))
        self._header = [w.HTML(f'<b>{t}</b>') for t in ('#', 'Entry', 'Expanded (if different)', 'Status')]
        self._empty_row = [w.HTML(), w.HTML(), w.HTML(f'<i style="color:{_GRAY}">(no entries)</i>'), w.HTML(), w.HTML()]
        self._rows = []   # reusable row widgets, see _row()

        self.up_btn = w.Button(desc='Move up', icon='arrow-up', cb=lambda _: self._run(self.move, -1), width='100px')
        self.down_btn = w.Button(desc='Move down', icon='arrow-down', cb=lambda _: self._run(self.move, 1), width='110px')
        self.remove_btn = w.Button(desc='Remove selected', icon='minus', cb=lambda _: self._run(self.remove_selected), width='140px')
        self.flagged_btn = w.Button(desc='Select flagged', icon='flag', cb=lambda _: self._run(self.select_flagged), width='130px',
                                    tooltip='Select every entry with a problem (then review and Remove selected)')
        self.dedupe_btn = w.Button(desc='Remove duplicates & empty', icon='compress', cb=lambda _: self._run(self.dedupe), width='210px',
                                   tooltip='Keep the first of each expanded absolute path; for User, also drop entries already in System')

        self.new_text = w.Text(desc='Entry:', width='560px', style={'description_width': '50px'},
                               placeholder=r'folder, e.g. %USERPROFILE%\Downloads\Programs\Git\cmd')
        self.add_btn = w.Button(desc='Add', icon='plus', cb=lambda _: self._run(self.add, False), width='80px', tooltip='Add at the end')
        self.add_top_btn = w.Button(desc='Add at top', icon='plus', cb=lambda _: self._run(self.add, True), width='110px')
        self.replace_btn = w.Button(desc='Replace selected', icon='pencil', cb=lambda _: self._run(self.replace), width='140px',
                                    tooltip='Replace the one selected entry with the text above (select one entry to load it here)')

        self.backup_cb = w.Checkbox(desc='Back up to temp folder before saving', value=True, width='290px')
        self.backup_info = w.HTML(f'<code style="font-size:85%">{html.escape(BACKUP_DIR)}</code>')
        self.open_backup_btn = w.Button(desc='Open', icon='folder-open', cb=lambda _: self._run(self.open_backups), width='80px',
                                        tooltip='Open the backup folder in Explorer')
        self.save_btn = w.Button(desc='Save', icon='save', button_style='success', cb=lambda _: self._run(self.save), width='100px')
        self.discard_btn = w.Button(desc='Discard / Reload', icon='refresh', cb=lambda _: self._run(self.reload), width='140px',
                                    tooltip='Throw away unsaved edits and re-read both PATHs from the registry')
        self.pending = w.HTML()
        self.log_out = w.Output(layout={'border': '1px solid #eee', 'max_height': '220px', 'overflow': 'auto'})

        self.edit_controls = [self.up_btn, self.down_btn, self.remove_btn, self.dedupe_btn,
                              self.new_text, self.add_btn, self.add_top_btn, self.replace_btn]
        css = w.HTML('<style>.epe-mono, .epe-mono * { font-family: monospace; font-size: 90%; }</style>')
        self.ui = w.VBox([
            css, self.header,
            self.scope_tb, self.scope_info,
            self.table,
            w.HBox([self.up_btn, self.down_btn, self.remove_btn, self.flagged_btn, self.dedupe_btn]),
            w.HBox([self.new_text, self.add_btn, self.add_top_btn, self.replace_btn]),
            w.HBox([self.save_btn, self.discard_btn, self.backup_cb, self.backup_info, self.open_backup_btn]),
            self.pending,
            self.log_out,
        ])

    # ── helpers ───────────────────────────────────────────────────────────────
    def log(self, msg: str, color: str | None = None):
        line = f'{datetime.datetime.now():%H:%M:%S}  {msg}'
        if color:
            self.log_out.append_display_data(_HTMLobj(f'<pre style="margin:0;color:{color}">{html.escape(line)}</pre>'))
        else:
            self.log_out.append_stdout(line + '\n')

    def _run(self, fn, *args):
        try:
            fn(*args)
        except (PathWriteError, ValueError, OSError) as e:
            self.log(str(e), _RED)
        except Exception:
            self.log(traceback.format_exc(), _RED)

    def _sync(self, widget, attr, value):
        self._syncing = True
        try:
            setattr(widget, attr, value)
        finally:
            self._syncing = False

    @property
    def scope(self) -> str:
        return self.scope_tb.value

    @property
    def cur(self) -> list[str]:
        return self.entries[self.scope]

    def editable(self, name: str | None = None) -> bool:
        return (name or self.scope) == 'User' or self.admin

    def _changed(self, name: str) -> bool:
        return self.entries[name] != split(self.loaded[name])

    def _checks(self, name: str):
        other = self.entries['System'] if name == 'User' else None
        return check_entries(self.entries[name], other)

    def _need_editable(self):
        if not self.editable():
            raise ValueError('The System PATH is read-only here - run Jupyter as administrator to edit it.')

    def _need_selection(self, exactly_one: bool = False) -> list[int]:
        sel = sorted(self.selected)
        if not sel:
            raise ValueError('Select at least one entry.')
        if exactly_one and len(sel) != 1:
            raise ValueError('Select exactly one entry.')
        return sel

    # ── load / render ─────────────────────────────────────────────────────────
    def reload(self):
        for name, s in self.scopes.items():
            raw, _ = read_raw(s)
            self.loaded[name] = raw
            self.entries[name] = split(raw)
        self.selected.clear()
        longest = max(len(e) for e in self.entries.values())
        if longest:
            self._row(longest - 1)   # build rows for both scopes now, so switching scope creates none
        self.refresh()
        self.log('Loaded User and System PATH from the registry.')

    def _scope_changed(self, change=None):
        self.selected.clear()
        self.refresh()

    def _toggle_all(self, change):
        if self._syncing:
            return
        self.selected = set(range(len(self.cur))) if change['new'] else set()
        self.refresh()

    def _row_toggled(self, i, change):
        if self._syncing:
            return
        (self.selected.add if change['new'] else self.selected.discard)(i)
        if change['new'] and len(self.selected) == 1:
            self.new_text.value = self.cur[i]   # ready for Replace selected
        self._sync(self.sel_all_cb, 'value', len(self.selected) == len(self.cur) > 0)

    def _row(self, i: int) -> list:
        """Row i's widgets, created on first use and then reused: creating widgets is what makes the
        front end slow (each one is a new comm + render), updating an existing one's value is cheap."""
        while len(self._rows) <= i:
            w, n = self.w, len(self._rows)
            cb = w.Checkbox(value=False, width='26px')
            cb.observe(lambda ch, n=n: self._run(self._row_toggled, n, ch), 'value')
            e, x = w.HTML(), w.HTML()
            e.add_class('epe-mono')
            x.add_class('epe-mono')
            self._rows.append([cb, w.HTML(str(n + 1)), e, x, w.HTML()])
        return self._rows[i]

    def refresh(self):
        name = self.scope
        checks = self._checks(name)
        loaded_keys = {normalize(e) for e in split(self.loaded[name])}

        self._sync(self.sel_all_cb, 'value', bool(self.cur) and len(self.selected) == len(self.cur))
        cells = [self.sel_all_cb] + self._header
        for i, c in enumerate(checks):
            cb, _, e, x, st = row = self._row(i)
            expanded = c.expanded if c.expanded and c.expanded != c.entry.strip() else ''
            if c.ok:
                status, color = 'OK', _GREEN
            else:
                serious = any(not p.startswith(('duplicate', 'also in')) for p in c.problems)
                status, color = '; '.join(c.problems), _RED if serious else _ORANGE
            if c.key and c.key not in loaded_keys:
                status += ' (new, unsaved)'
            entry_html = html.escape(c.entry) if c.entry.strip() else f'<i style="color:{_GRAY}">(empty)</i>'
            # unchanged values are not re-sent (traitlets only notifies on a change)
            self._sync(cb, 'value', i in self.selected)
            e.value = f'<span title="{html.escape(c.expanded)}">{entry_html}</span>'
            x.value = html.escape(expanded)
            st.value = f'<span style="color:{color}">{html.escape(status)}</span>'
            cells += row
        if not checks:
            cells += self._empty_row
        if tuple(cells) != self.table.children:
            self.table.children = cells

        # entry / problem counts for both scopes (the scope buttons themselves keep fixed labels)
        counts = []
        for n in ('User', 'System'):
            bad = sum(not c.ok for c in self._checks(n))
            counts.append(f'<b>{n}</b>: {len(self.entries[n])} entries'
                          + (f', <span style="color:{_ORANGE}">{bad} flagged</span>' if bad else '')
                          + (f', <span style="color:{_BLUE}">unsaved changes</span>' if self._changed(n) else ''))
        s = self.scopes[name]
        ro = '' if self.editable() else f' — <b style="color:{_ORANGE}">read-only</b> (not running as administrator)'
        self.scope_info.value = (' &nbsp;·&nbsp; '.join(counts) + '<br>'
                                 f'Showing <code>{html.escape(s.location)}</code> — {len(";".join(self.cur))} characters{ro}')
        self.header.value = (f'Running as {"<b>administrator</b>" if self.admin else "a normal user"}. '
                             'PATH search order: System entries first, then User.')
        for c in self.edit_controls:
            c.disabled = not self.editable()
        self._show_pending()

    def _show_pending(self):
        parts = []
        for n in ('User', 'System'):
            if not self._changed(n):
                continue
            old, new = split(self.loaded[n]), self.entries[n]
            old_c, new_c = Counter(old), Counter(new)
            added, removed = sum((new_c - old_c).values()), sum((old_c - new_c).values())
            common = old_c & new_c
            order = lambda lst: list(dict.fromkeys(e for e in lst if e in common))
            moved = order(old) != order(new)
            bits = ([f'+{added} added'] if added else []) + ([f'−{removed} removed'] if removed else []) \
                   + (['order changed'] if moved else []) + ([] if added or removed or moved else ['edited'])
            parts.append(f'{n}: {", ".join(bits)}')
        self.pending.value = (f'<span style="color:{_BLUE}"><b>Unsaved changes</b> — {html.escape("; ".join(parts))}</span>'
                              if parts else f'<span style="color:{_GRAY}">No unsaved changes.</span>')

    # ── edits ─────────────────────────────────────────────────────────────────
    def move(self, step: int):
        self._need_editable()
        sel = self._need_selection()
        lst = self.cur
        order = sel if step < 0 else list(reversed(sel))
        new_sel = set()
        for i in order:
            j = i + step
            if 0 <= j < len(lst) and j not in new_sel:
                lst[i], lst[j] = lst[j], lst[i]
                new_sel.add(j)
            else:
                new_sel.add(i)   # at the edge, or blocked by a selected neighbour that couldn't move
        self.selected = new_sel
        self.refresh()

    def remove_selected(self):
        self._need_editable()
        sel = self._need_selection()
        gone = [self.cur[i] for i in sel]
        self.entries[self.scope] = [e for i, e in enumerate(self.cur) if i not in self.selected]
        self.selected.clear()
        self.refresh()
        self.log(f'{self.scope}: removed {len(gone)} entr{"y" if len(gone) == 1 else "ies"} (unsaved): ' + '; '.join(gone or ['']))

    def select_flagged(self):
        self.selected = {i for i, c in enumerate(self._checks(self.scope)) if not c.ok}
        self.refresh()
        self.log(f'{self.scope}: {len(self.selected)} flagged entr{"y" if len(self.selected) == 1 else "ies"} selected.')

    def dedupe(self):
        self._need_editable()
        before = self.cur
        other = self.entries['System'] if self.scope == 'User' else None
        self.entries[self.scope] = remove_duplicates(before, other)
        self.selected.clear()
        self.refresh()
        n = len(before) - len(self.cur)
        self.log(f'{self.scope}: removed {n} duplicate/empty entr{"y" if n == 1 else "ies"} (unsaved).' if n else
                 f'{self.scope}: no duplicate or empty entries.')

    def _new_entry(self) -> str:
        e = self.new_text.value.strip().strip('"').strip()
        if not e:
            raise ValueError('Type a folder in the Entry field.')
        if ';' in e:
            raise ValueError('An entry cannot contain ";" - add one folder at a time.')
        return e

    def add(self, top: bool):
        self._need_editable()
        e = self._new_entry()
        k = normalize(e)
        hit = next((i for i, x in enumerate(self.cur) if normalize(x) == k), None)
        if hit is not None:
            raise ValueError(f'Already in the {self.scope} PATH as #{hit + 1}: {self.cur[hit]}')
        if self.scope == 'User':
            hit = next((i for i, x in enumerate(self.entries['System']) if normalize(x) == k), None)
            if hit is not None:
                raise ValueError(f'Already in the System PATH as #{hit + 1} (searched before User): {self.entries["System"][hit]}')
        if top:
            self.cur.insert(0, e)
        else:
            self.cur.append(e)
        self.selected = {0 if top else len(self.cur) - 1}
        self.new_text.value = ''
        self.refresh()
        c = check_entries([e])[0]
        self.log(f'{self.scope}: added {e} (unsaved)' + ('' if c.ok else f' - {"; ".join(c.problems)}'), None if c.ok else _ORANGE)

    def replace(self):
        self._need_editable()
        i = self._need_selection(exactly_one=True)[0]
        e = self._new_entry()
        k = normalize(e)
        hit = next((j for j, x in enumerate(self.cur) if j != i and normalize(x) == k), None)
        if hit is not None:
            raise ValueError(f'Already in the {self.scope} PATH as #{hit + 1}: {self.cur[hit]}')
        old = self.cur[i]
        self.cur[i] = e
        self.refresh()
        self.log(f'{self.scope} #{i + 1}: {old} → {e} (unsaved)')

    # ── save ──────────────────────────────────────────────────────────────────
    def save(self):
        names = [n for n in ('User', 'System') if self._changed(n)]
        if not names:
            self.log('Nothing to save.')
            return
        if any(not self.editable(n) for n in names):
            raise ValueError('System PATH has edits but this session is not administrator - Discard them first.')
        # check every scope against the registry before writing anything
        for n in names:
            if read_raw(self.scopes[n])[0] != self.loaded[n]:
                raise PathWriteError(f'{n} PATH was changed outside this tool since it was loaded - '
                                     'Discard / Reload and redo the edit.')
        if self.backup_cb.value:
            bak = backup(list(self.scopes.values()))
            self.log(f'Backup: {bak}')
        for n in names:
            write(self.scopes[n], self.entries[n], expected_raw=self.loaded[n], notify=False)
            self.loaded[n] = read_raw(self.scopes[n])[0]
            self.log(f'{n} PATH saved ({len(self.entries[n])} entries).', _GREEN)
        # ~1 s here, but each top-level window may take up to 5 s to answer - don't block the kernel
        threading.Thread(target=broadcast_change, daemon=True).start()
        self.log('Programs started from now on see the new PATH; restart open terminals / VS Code / Jupyter to pick it up.')
        self.refresh()

    def open_backups(self):
        if not os.path.isdir(BACKUP_DIR):
            raise ValueError(f'No backups yet ({BACKUP_DIR} does not exist).')
        os.startfile(BACKUP_DIR)


def _HTMLobj(s):
    from IPython.display import HTML
    return HTML(s)


def show_gui(user_scope: Scope = USER, system_scope: Scope = SYSTEM):
    """Build the Env Path Editor UI and return its top-level widget (for embedding, e.g. tools_launcher)."""
    return EnvPathEditorGUI(user_scope, system_scope).ui


# %%
if __name__ == '__main__':
    display(show_gui())
