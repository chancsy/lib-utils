"""Find the tools under utils/tools and launch them from one widget (embedded by work_dir/tools_launcher.py).

A tool is a subfolder of utils/tools holding a ``tool.toml`` manifest::

    name        = "Env Path Editor"                                        # button label
    entry       = "utils.tools.env_path_editor.env_path_editor:show_gui"   # function returning a widget
    description = "View, check and edit the Windows User and System PATH"  # tooltip (optional)
    order       = 100                                                      # button order (optional; then by name)

Manifests are read without importing anything. A tool's module is imported only when its button is clicked,
so a tool whose optional packages are missing fails on its own button, not the whole launcher.

    from utils.tools.launcher import show_gui, discover_tools
    display(show_gui())        # Jupyter
    discover_tools()           # -> [ToolSpec, ...]
"""
import html
import importlib
import tomllib
import traceback
from dataclasses import dataclass
from importlib.resources import files

MANIFEST = 'tool.toml'
DEFAULT_ORDER = 100


@dataclass(frozen=True)
class ToolSpec:
    name: str
    entry: str              # 'package.module:function'
    description: str = ''
    order: int = DEFAULT_ORDER
    folder: str = ''        # subfolder of utils/tools
    error: str = ''         # set when the manifest couldn't be read; the tool can't be launched

    def load(self):
        """Import the tool's module and call its entry function; returns what it returns (normally a widget)."""
        module, func = self.entry.split(':')
        return getattr(importlib.import_module(module), func)()


def _read_manifest(folder: str, text: str) -> ToolSpec:
    m = tomllib.loads(text)
    name, entry = m.get('name'), m.get('entry')
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' is missing")
    if not isinstance(entry, str) or entry.count(':') != 1 or not all(entry.split(':')):
        raise ValueError(f"'entry' must be 'package.module:function', got {entry!r}")
    return ToolSpec(name.strip(), entry.strip(), str(m.get('description', '')), int(m.get('order', DEFAULT_ORDER)), folder)


def discover_tools(package: str = 'utils.tools') -> list[ToolSpec]:
    """Every subfolder of `package` with a tool.toml, sorted by (order, name).

    A manifest that can't be read still gives a ToolSpec (named after its folder) with `error` set,
    so the problem shows up in the UI instead of the tool silently disappearing.
    """
    tools = []
    for d in files(package).iterdir():
        f = d / MANIFEST
        if d.name.startswith(('_', '.')) or not f.is_file():
            continue
        try:
            tools.append(_read_manifest(d.name, f.read_text(encoding='utf-8')))
        except (tomllib.TOMLDecodeError, ValueError, TypeError) as e:
            tools.append(ToolSpec(d.name, '', folder=d.name, error=f'{MANIFEST}: {e}'))
    return sorted(tools, key=lambda t: (t.order, t.name.lower()))


def show_gui(package: str = 'utils.tools'):
    """One button per discovered tool; a click loads the tool below (once) and shows / hides it."""
    from IPython.display import display
    from utils.standalone.widget_utils import Widgets

    w = Widgets()
    w.show_widget_on_create = False
    tools = discover_tools(package)
    status = w.HTML(value=f'<i>{len(tools)} tools found in {package}. Select one.</i>' if tools
                    else f'<i>No tools found: no {package} subfolder has a {MANIFEST}.</i>')
    if not tools:
        return w.VBox([status])

    width = f'{max(len(t.name) for t in tools) * 9 + 24}px'
    outputs = {t.folder: w.Output() for t in tools}
    boxes = {t.folder: w.VBox([outputs[t.folder]]) for t in tools}
    loaded, active, buttons = set(), [None], {}

    def show_status(text, color=None):
        status.value = f'<span style="color:{color}">{text}</span>' if color else f'<i>{text}</i>'

    def load(t: ToolSpec) -> bool:
        if t.folder in loaded:
            return True
        show_status(f'Launching <b>{html.escape(t.name)}</b>...')
        out = outputs[t.folder]
        out.clear_output()
        try:
            result = t.load()
            if result is not None:
                with out:
                    display(result)
        except Exception as e:
            with out:
                print(traceback.format_exc())
            show_status(f'[Error] {html.escape(t.name)}: {html.escape(str(e))}', 'red')
            return False
        loaded.add(t.folder)
        show_status(f'&#10003; {html.escape(t.name)} loaded.', 'green')
        return True

    def on_click(t: ToolSpec):
        def handler(_):
            prev = active[0]
            if prev is not None:
                boxes[prev].layout.display = 'none'
                buttons[prev].button_style = ''
            if prev == t.folder:
                active[0] = None
                show_status('Select a tool.')
                return
            load(t)
            boxes[t.folder].layout.display = ''
            buttons[t.folder].button_style = 'primary'
            active[0] = t.folder
        return handler

    for t in tools:
        boxes[t.folder].layout.display = 'none'
        if t.error:
            b = w.Button(description=t.name, width=width, disabled=True, tooltip=f'{t.folder}: {t.error}')
        else:
            b = w.Button(description=t.name, width=width, tooltip=t.description or t.entry)
            b.on_click(on_click(t))
        buttons[t.folder] = b
    if any(t.error for t in tools):
        show_status('Some tool manifests could not be read (disabled buttons; hover for the reason).', 'orange')

    bar = w.HBox(list(buttons.values()))
    bar.layout.flex_flow = 'row wrap'
    return w.VBox([bar, status, *boxes.values()])
