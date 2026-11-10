# %% [markdown]
# # Task Scheduler
# List, add, enable / disable, run, stop and remove Windows scheduled tasks - e.g. start a monitor at boot, or
# resume a test script after a restart. Covers the basic settings; **Show XML** prints a task's full definition.
#
# - **Run whether user is logged on or not** needs the account password each time a task is added or updated:
#   the Windows password dialog asks for it (Windows keeps it with the task; this tool doesn't). Such a task runs in
#   the background: no windows or plots are shown.
# - **Only when user is logged on** runs in the user's desktop session, so windows are visible.
# - An **at-startup** trigger, logon S4U, **highest privileges**, changing (e.g. enabling / disabling) a task
#   registered with administrator rights (even your own; Run now and Remove don't need them) and other users' tasks
#   need administrator rights.
#   Jupyter stays non-elevated: just that change runs in an elevated helper after a **UAC prompt**.
# - The UAC prompt and the password dialog appear on the screen of the PC that runs Jupyter; the UI waits for them.
#
# Run this notebook, or from code: `from utils.tools.task_scheduler.task_scheduler import show_gui; display(show_gui())`

# %%
import datetime
import html
import os
import shlex
import traceback

from IPython.display import display

from utils.tools.task_scheduler import (ROOT, TaskSchedulerError, add_python_script, at_logon, at_startup,
                                        current_user, daily, default_python, delete_folder, delete_task, export_xml,
                                        get_task, set_notify,
                                        is_admin, list_tasks, needs_admin, once, register_task, run_task, set_enabled,
                                        stop_task)

_GRAY, _GREEN, _ORANGE, _RED, _BLUE = '#888', '#2e7d32', '#e67e22', '#c0392b', '#1565c0'
_STATE_COLORS = {'ready': _GREEN, 'running': _BLUE, 'disabled': _GRAY, 'queued': _ORANGE}
_OK_RESULTS = {0, 0x41300, 0x41301, 0x41303, 0x41306}
_TRIGGERS = [('At startup (admin)', 'startup'), ('At log on', 'logon'), ('Daily', 'daily'), ('Once', 'once'),
             ('None - run on demand only', 'none')]
_LOGONS = [('Run whether user is logged on or not (password)', 'password'),
           ('Run only when user is logged on (desktop, windows visible)', 'interactive'),
           ('Run whether logged on or not, no password (S4U: local only, admin)', 's4u')]
_PRIORITIES = [('Normal (4)', 4), ('Below normal (7, Windows default)', 7)]
_COLUMNS = ('Name', 'State', 'Triggers', 'Runs as', 'Last run', 'Last result', 'Next run', 'Action')


def _t(dt) -> str:
    return f'{dt:%Y-%m-%d %H:%M}' if dt else '—'


class TaskSchedulerGUI:
    def __init__(self, folder: str = ROOT):
        from utils.standalone.widget_utils import Widgets
        self.w = Widgets()
        self.w.show_widget_on_create = False
        self.admin = is_admin()
        self.user = current_user()
        self.tasks = []          # TaskInfo list of the shown folder
        self.selected = set()    # task names
        self._armed = None       # names awaiting a second Remove click
        self._syncing = False
        self._build(folder)
        set_notify(lambda msg: self.log(msg, _BLUE))   # 'UAC prompt: ...' notices into this UI's log
        self._run(self.reload)

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self, folder):
        w = self.w
        self.header = w.HTML()
        self.folder_text = w.Text(value=folder, desc='Folder:', width='320px', style={'description_width': '50px'},
                                  placeholder='\\ or \\SubFolder')
        self.reload_btn = w.Button(desc='Reload', icon='refresh', cb=lambda _: self._run(self.reload), width='100px')
        self.del_folder_btn = w.Button(desc='Delete folder', icon='trash', width='130px', cb=lambda _: self._run(self.delete_folder),
                                       tooltip='Delete this task folder if it is empty (click twice)')
        self.table = w.GridBox(layout={'grid_template_columns': '28px minmax(120px, 1.2fr) 70px minmax(150px, 1.4fr) '
                                                                'minmax(150px, 1fr) 125px minmax(110px, 1fr) 125px minmax(200px, 2.2fr)',
                                       'grid_gap': '1px 8px', 'width': '100%'})
        self.sel_all_cb = w.Checkbox(value=False, width='26px', cb=lambda ch: self._run(self._toggle_all, ch))
        self._header = [w.HTML(f'<b>{c}</b>') for c in _COLUMNS]
        self._empty_row = [w.HTML(), w.HTML(f'<i style="color:{_GRAY}">(no tasks in this folder)</i>')] + [w.HTML() for _ in range(7)]
        self._rows = []

        b = lambda desc, icon, fn, width, **k: w.Button(desc=desc, icon=icon, cb=lambda _: self._run(fn), width=width, **k)
        self.enable_btn = b('Enable', 'check', lambda: self.set_enabled(True), '90px')
        self.disable_btn = b('Disable', 'ban', lambda: self.set_enabled(False), '90px')
        self.run_btn = b('Run now', 'play', self.run_now, '100px', tooltip='Start the selected tasks now, as their own user')
        self.stop_btn = b('Stop', 'stop', self.stop, '80px', tooltip='Terminate the running instances of the selected tasks')
        self.remove_btn = b('Remove', 'trash', self.remove, '150px', tooltip='Delete the selected tasks (click twice)')
        self.xml_btn = b('Show XML', 'code', self.show_xml, '110px', tooltip="Print the selected task's full definition")
        self.load_btn = b('Load into form', 'pencil', self.load_into_form, '140px',
                          tooltip='Copy the selected task into the form below, to change and update it')

        # add / update form
        lw = {'description_width': '110px'}
        self.name_text = w.Text(desc='Task name:', width='420px', style=lw, placeholder='e.g. RestartMon, or \\Tests\\resume_x')
        self.program_text = w.Text(desc='Program / .py:', width='760px', style=lw,
                                   placeholder=r'C:\...\restart_mon.py, or a program, e.g. C:\Tools\tool.exe')
        self.python_text = w.Text(value=default_python(), desc='Python (.py):', width='760px', style=lw,
                                  placeholder='the python.exe that runs a .py script')
        self.args_text = w.Text(desc='Arguments:', width='760px', style=lw, placeholder='optional')
        self.start_in_text = w.Text(desc='Start in:', width='760px', style=lw, placeholder="blank = the script's / program's folder")
        self.trigger_dd = w.Dropdown(options=_TRIGGERS, value='startup', desc='Trigger:', width='420px', style=lw,
                                     cb=lambda ch: self._run(self._form_changed))
        self.delay_int = w.BoundedIntText(value=0, min=0, max=86400, desc='Delay (s):', width='170px',
                                          style={'description_width': '70px'})
        self.time_text = w.Text(desc='Time:', width='300px', style={'description_width': '40px'},
                                placeholder='HH:MM, or YYYY-MM-DD HH:MM', cb=lambda ch: self._run(self._form_changed))
        self.logon_dd = w.Dropdown(options=_LOGONS, value='password', desc='Security:', width='560px', style=lw,
                                   cb=lambda ch: self._run(self._form_changed))
        self.user_text = w.Text(value=self.user, desc='Run as:', width='420px', style=lw, placeholder='DOMAIN\\user')
        self.highest_cb = w.Checkbox(desc='Highest privileges (admin)', value=False, width='210px',
                                     cb=lambda ch: self._run(self._form_changed))
        self.enabled_cb = w.Checkbox(desc='Enabled', value=True, width='90px')
        self.battery_cb = w.Checkbox(desc='Run on battery', value=True, width='130px')
        self.replace_cb = w.Checkbox(desc='Replace an existing task', value=False, width='200px')
        self.priority_dd = w.Dropdown(options=_PRIORITIES, value=4, desc='Priority:', width='420px', style=lw)
        self.limit_int = w.BoundedIntText(value=0, min=0, max=9999, desc='Stop after (h):', width='210px',
                                          style={'description_width': '100px'}, tooltip='0 = never')
        self.desc_text = w.Text(desc='Description:', width='760px', style=lw, placeholder='optional')
        self.add_btn = w.Button(desc='Add / update', icon='plus', button_style='success', width='140px',
                                cb=lambda _: self._run(self.add))
        self.clear_btn = w.Button(desc='Clear form', icon='eraser', width='110px', cb=lambda _: self._run(self.clear_form))
        self.form_note = w.HTML()
        self.log_out = w.Output(layout={'border': '1px solid #eee', 'max_height': '260px', 'overflow': 'auto'})

        css = w.HTML('<style>.tsg-mono, .tsg-mono * { font-family: monospace; font-size: 90%; }</style>')
        self.ui = w.VBox([
            css, self.header,
            w.HBox([self.folder_text, self.reload_btn, self.del_folder_btn]),
            self.table,
            w.HBox([self.enable_btn, self.disable_btn, self.run_btn, self.stop_btn, self.remove_btn, self.xml_btn, self.load_btn]),
            w.HTML('<b>Add / update a task</b>'),
            self.name_text, self.program_text, self.python_text, self.args_text, self.start_in_text,
            w.HBox([self.trigger_dd, self.delay_int, self.time_text]),
            self.logon_dd,
            self.user_text,
            w.HBox([self.priority_dd, self.limit_int]),
            w.HBox([self.enabled_cb, self.battery_cb, self.highest_cb, self.replace_cb]),
            self.desc_text,
            w.HBox([self.add_btn, self.clear_btn]),
            self.form_note,
            self.log_out,
        ])
        self._form_changed()

    # ── helpers ───────────────────────────────────────────────────────────────
    def log(self, msg: str, color: str | None = None, pre: bool = False):
        line = f'{datetime.datetime.now():%H:%M:%S}  {msg}'
        if color or pre:
            style = f'margin:0;white-space:pre-wrap;color:{color or "inherit"}'
            self.log_out.append_display_data(_HTMLobj(f'<pre style="{style}">{html.escape(line)}</pre>'))
        else:
            self.log_out.append_stdout(line + '\n')

    def _run(self, fn, *args):
        try:
            fn(*args)
        except (TaskSchedulerError, ValueError, OSError) as e:
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
    def folder(self) -> str:
        return self.folder_text.value.strip() or ROOT

    def _need_selection(self, exactly_one: bool = False) -> list[str]:
        sel = [t.name for t in self.tasks if t.name in self.selected]
        if not sel:
            raise ValueError('Select at least one task.')
        if exactly_one and len(sel) != 1:
            raise ValueError('Select exactly one task.')
        return sel

    def _disarm(self):
        if self._armed is not None:
            self._armed = None
            self.remove_btn.description, self.remove_btn.button_style = 'Remove', ''
            self.del_folder_btn.description, self.del_folder_btn.button_style = 'Delete folder', ''

    # ── load / render ─────────────────────────────────────────────────────────
    def reload(self):
        self._disarm()
        try:
            self.tasks = list_tasks(self.folder)
        except TaskSchedulerError as e:
            self.tasks = []
            if e.code != 0x80070002:
                raise
            self.log(f'Folder {self.folder} does not exist yet - Add / update creates it.', _ORANGE)
        finally:
            self.selected &= {t.name for t in self.tasks}
            self.refresh()

    def _toggle_all(self, change):
        if self._syncing:
            return
        self._disarm()
        self.selected = {t.name for t in self.tasks} if change['new'] else set()
        self.refresh()

    def _row_toggled(self, i, change):
        if self._syncing or i >= len(self.tasks):
            return
        self._disarm()
        (self.selected.add if change['new'] else self.selected.discard)(self.tasks[i].name)
        self._sync(self.sel_all_cb, 'value', len(self.selected) == len(self.tasks) > 0)

    def _row(self, i: int) -> list:
        """Row i's widgets, created on first use and then reused (creating widgets is the slow part)."""
        while len(self._rows) <= i:
            w, n = self.w, len(self._rows)
            cb = w.Checkbox(value=False, width='26px')
            cb.observe(lambda ch, n=n: self._run(self._row_toggled, n, ch), 'value')
            cells = [w.HTML() for _ in _COLUMNS]
            cells[-1].add_class('tsg-mono')
            self._rows.append([cb] + cells)
        return self._rows[i]

    def refresh(self):
        self._sync(self.sel_all_cb, 'value', bool(self.tasks) and len(self.selected) == len(self.tasks))
        cells = [self.sel_all_cb] + self._header
        for i, t in enumerate(self.tasks):
            row = self._row(i)
            cb, name, state, trig, runs, last, result, nxt, action = row
            self._sync(cb, 'value', t.name in self.selected)
            name.value = f'<span title="{html.escape(t.description or t.path)}">{html.escape(t.name)}</span>'
            state.value = f'<span style="color:{_STATE_COLORS.get(t.state, _ORANGE)}">{html.escape(t.state)}</span>'
            trig.value = html.escape('; '.join(t.triggers) or 'on demand only')
            runs.value = (f'{html.escape(t.user)}<br><span style="color:{_GRAY}">{html.escape(t.runs)}'
                          + (', highest' if t.run_level == 'highest' else '') + '</span>') if not t.error else \
                f'<span style="color:{_GRAY}">{html.escape(t.error)}</span>'
            last.value = _t(t.last_run)
            ok = t.last_result is None or (t.last_result & 0xFFFFFFFF) in _OK_RESULTS
            result.value = f'<span style="color:{_GRAY if ok else _RED}">{html.escape(t.result)}</span>'
            nxt.value = _t(t.next_run)
            cmd = f'{t.command} {t.arguments}'.strip()
            action.value = (f'<span title="Start in: {html.escape(t.working_dir or "(not set)")}">{html.escape(cmd)}</span>')
            cells += row
        if not self.tasks:
            cells += self._empty_row
        if tuple(cells) != self.table.children:
            self.table.children = cells
        rights = ('<b>administrator</b>' if self.admin else
                  f'a normal user - <span style="color:{_ORANGE}">changes that need administrator rights (at-startup '
                  "triggers, S4U, highest privileges, changing tasks registered with administrator rights) show a UAC "
                  "prompt on this PC's screen</span>")
        self.header.value = (f'Running as {html.escape(self.user)}, {rights}.<br>'
                             f'Folder <code>{html.escape(self.folder)}</code>: {len(self.tasks)} task(s); '
                             f'loaded {datetime.datetime.now():%H:%M:%S}.')

    # ── task actions ──────────────────────────────────────────────────────────
    # all selected tasks go in one call, so tasks that need administrator rights share one UAC prompt
    def set_enabled(self, enabled: bool):
        names = self._need_selection()
        try:
            for t in set_enabled(names, enabled, self.folder):
                self.log(f'{t.name}: {t.state}.', _GREEN)
        finally:
            self.reload()

    def run_now(self):
        names = self._need_selection()
        try:
            for t in run_task(names, self.folder):
                self.log(f'{t.name}: started ({t.state}).', _GREEN)
        finally:
            self.reload()

    def stop(self):
        names = self._need_selection()
        try:
            for t in stop_task(names, self.folder):
                self.log(f'{t.name}: stopped ({t.state}).', _GREEN)
        finally:
            self.reload()

    def remove(self):
        names = self._need_selection()
        if self._armed != names:
            self._armed = names
            self.remove_btn.description, self.remove_btn.button_style = f'Confirm remove ({len(names)})', 'danger'
            self.log(f'Click "Confirm remove" to delete: {", ".join(names)}', _ORANGE)
            return
        self._disarm()
        try:
            delete_task(names, self.folder)
            self.log(f'Removed: {", ".join(names)}.', _GREEN)
            self.selected -= set(names)
        finally:
            self.reload()

    def delete_folder(self):
        folder = self.folder
        if folder.strip('\\') == '':
            raise ValueError('The root folder cannot be deleted.')
        if self.tasks:
            raise ValueError(f'{folder} still has {len(self.tasks)} task(s) - remove them first.')
        if self._armed != ['<folder>']:
            self._disarm()
            self._armed = ['<folder>']
            self.del_folder_btn.description, self.del_folder_btn.button_style = 'Confirm delete', 'danger'
            self.log(f'Click "Confirm delete" to delete the folder {folder}', _ORANGE)
            return
        self._disarm()
        delete_folder(folder)
        self.log(f'Folder {folder} deleted.', _GREEN)
        self.folder_text.value = ROOT
        self.reload()

    def show_xml(self):
        n = self._need_selection(exactly_one=True)[0]
        self.log(f'{n} XML:\n{export_xml(n, self.folder)}', pre=True)

    # ── form ──────────────────────────────────────────────────────────────────
    def _form_changed(self):
        kind, logon = self.trigger_dd.value, self.logon_dd.value
        self.delay_int.disabled = kind not in ('startup', 'logon')
        self.time_text.disabled = kind not in ('daily', 'once')
        notes = []
        if kind in ('daily', 'once') and not self.time_text.value.strip():
            notes.append('Set a Time for a Daily / Once trigger.')
        if kind == 'startup' and logon == 'interactive':
            notes.append('An at-startup trigger with "Run only when user is logged on" only starts if the user is '
                         'already logged on at boot - use "Run whether user is logged on or not".')
        if not self.admin and (kind == 'startup' or logon == 's4u' or self.highest_cb.value):
            notes.append('Needs administrator rights: Add / update shows a UAC prompt on this PC\'s screen'
                         + (', then the password dialog.' if logon == 'password' else '.'))
        elif logon == 'password':
            notes.append("Add / update asks for the password in the Windows password dialog on this PC's screen.")
        self.form_note.value = ''.join(f'<div style="color:{_ORANGE}">{html.escape(n)}</div>' for n in notes)

    def _trigger(self):
        kind = self.trigger_dd.value
        if kind == 'startup':
            return [at_startup(self.delay_int.value)]
        if kind == 'logon':
            return [at_logon(self.delay_int.value)]
        if kind in ('daily', 'once'):
            if not self.time_text.value.strip():
                raise ValueError('Set a Time (HH:MM, or YYYY-MM-DD HH:MM) for a Daily / Once trigger.')
            return [(daily if kind == 'daily' else once)(self.time_text.value)]
        return []

    def add(self):
        self._disarm()
        name, program = self.name_text.value.strip(), self.program_text.value.strip().strip('"')
        if not name:
            raise ValueError('Type a task name.')
        if not program:
            raise ValueError('Type the program or .py script to run.')
        common = dict(triggers=self._trigger(), folder=self.folder, user=self.user_text.value.strip() or None,
                      logon=self.logon_dd.value,
                      run_level='highest' if self.highest_cb.value else 'limited', description=self.desc_text.value.strip(),
                      enabled=self.enabled_cb.value, allow_on_battery=self.battery_cb.value,
                      priority=self.priority_dd.value, time_limit_s=self.limit_int.value * 3600, replace=self.replace_cb.value)
        start_in = self.start_in_text.value.strip().strip('"') or None
        if common['logon'] == 'password':
            self.log(("After the UAC prompt, the" if not self.admin and needs_admin(common['triggers'], 'password', common['run_level'])
                      else 'The') + " password dialog appears on this PC's screen ...", _BLUE)
        if program.lower().endswith('.py'):
            t = add_python_script(program, name, self.args_text.value.strip(), python=self.python_text.value.strip() or None,
                                  working_dir=start_in, **common)
        else:
            t = register_task(name, program, self.args_text.value.strip(), start_in or os.path.dirname(program), **common)
        self.log(f'{t.path}: {"updated" if self.replace_cb.value else "added"} - {"; ".join(t.triggers) or "on demand only"}, '
                 f'{t.runs}, {t.state}.', _GREEN)
        self.selected = {t.name}
        if t.folder.lower() != self.folder.lower():
            self.folder_text.value = t.folder
        self.reload()

    def clear_form(self):
        for widget in (self.name_text, self.program_text, self.args_text, self.start_in_text, self.time_text,
                       self.desc_text):
            widget.value = ''
        self.python_text.value, self.user_text.value = default_python(), self.user
        self.trigger_dd.value, self.logon_dd.value, self.priority_dd.value = 'startup', 'password', 4
        self.delay_int.value = self.limit_int.value = 0
        self.enabled_cb.value, self.battery_cb.value, self.highest_cb.value, self.replace_cb.value = True, True, False, False
        self._form_changed()

    def load_into_form(self):
        n = self._need_selection(exactly_one=True)[0]
        t = get_task(n, self.folder)
        if t.error:
            raise ValueError(f'{n}: {t.error}')
        self.clear_form()
        self.name_text.value = t.name
        program, args = t.command.strip('"'), t.arguments
        if os.path.basename(program).lower() in ('python.exe', 'pythonw.exe') and args:
            parts = shlex.split(args, posix=False)
            if parts and parts[0].strip('"').lower().endswith('.py'):
                self.python_text.value, program = program, parts[0].strip('"')
                args = args.strip()[len(parts[0]):].strip()
                script_dir = os.path.dirname(program)
                if t.working_dir and os.path.normcase(t.working_dir.rstrip('\\')) != os.path.normcase(script_dir):
                    self.start_in_text.value = t.working_dir
        if not self.start_in_text.value and not program.lower().endswith('.py'):
            self.start_in_text.value = t.working_dir
        self.program_text.value, self.args_text.value = program, args
        spec = t.trigger_specs[0] if t.trigger_specs else None
        if spec:
            self.trigger_dd.value = spec.kind
            self.delay_int.value = spec.delay_s
            if spec.at:
                self.time_text.value = f'{spec.at:%H:%M}' if spec.kind == 'daily' else f'{spec.at:%Y-%m-%d %H:%M}'
        else:
            self.trigger_dd.value = 'none'
        if t.logon in dict((v, k) for k, v in _LOGONS):
            self.logon_dd.value = t.logon
        self.user_text.value = t.user
        self.highest_cb.value = t.run_level == 'highest'
        self.enabled_cb.value, self.battery_cb.value = t.enabled, t.allow_on_battery
        if t.priority in dict((v, k) for k, v in _PRIORITIES):
            self.priority_dd.value = t.priority
        self.limit_int.value = (t.time_limit_s + 3599) // 3600
        self.desc_text.value, self.replace_cb.value = t.description, True
        self._form_changed()
        notes = []
        if len(t.triggers) > 1 or (t.triggers and not spec):
            notes.append(f'it has trigger(s) this form can\'t show ({"; ".join(t.triggers)}) - Add / update keeps only the one shown')
        if t.logon == 'password':
            notes.append('Add / update asks for the password again')
        self.log(f'{n}: loaded into the form' + (f' - {"; ".join(notes)}.' if notes else '.'), _ORANGE if notes else None)


def _HTMLobj(s):
    from IPython.display import HTML
    return HTML(s)


def show_gui(folder: str = ROOT):
    """Build the Task Scheduler UI and return its top-level widget (for embedding, e.g. tools_launcher)."""
    return TaskSchedulerGUI(folder).ui


# %%
if __name__ == '__main__':
    display(show_gui())
