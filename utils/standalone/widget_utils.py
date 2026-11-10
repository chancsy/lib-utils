from ..utilities import *
from .._internal.util_demo import resolve_demo_input, call_demo_function
import re
utils = UtilityFunctions()

# IPython is a core dependency of lib-utils (see pyproject.toml), so it's fine to import
# here at module level too. ipywidgets is NOT core, though - it's checked/imported lazily
# below, only once Widgets is actually constructed.
from IPython.display import display

class Widgets:
    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require ipywidgets - only actually instantiating
        # Widgets does. Cached on self so __getattr__ below doesn't need its own import
        # statement.
        utils.exit_if_not_in_ipython()
        utils.exit_if_module_missing('ipywidgets')
        import ipywidgets as widgets
        self._widgets = widgets
        self.user_button_width = None
        self.user_button_height = None
        self.user_checkbox_width = None
        self.show_widget_on_create = True
        self.continuous_update = False

    def demo(self):
        _ = self.Button(description='Click Me!', cb=lambda x: setattr(x, 'description', 'Clicked!'))

    def default_cb(self, sender=None):
        return

    def enable_widget_group(self, widget_array):
        for widget in widget_array:
            widget.disabled = 0

    def disable_widget_group(self, widget_array):
        for widget in widget_array:
            widget.disabled = 1

    def print_to_output(self, output_widget, msg, append=False):
        if not append:
            output_widget.outputs = ()
        if isinstance(msg, str):
            output_widget.append_stdout(msg + '\n')
        else:
            output_widget.append_display_data(msg)

    def __getattr__(self, a):
        widget_class = getattr(self._widgets, a)
        def wrapper(*args, **kwargs):
            # Pre-method call - Begin
            # Translate 'desc' argument to 'description' argument
            if 'desc' in kwargs:
                kwargs = utils.update_kwargs_param(kwargs, 'description', kwargs['desc'])

            # Get layout from kwargs, if not present, set to empty dict
            kwargs_layout = kwargs.get('layout', {})
            # Set default styles for widgets
            if (widget_class == self._widgets.Button):
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', self.user_button_width))
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'height', kwargs.get('height', self.user_button_height))
            elif (widget_class == self._widgets.Checkbox):
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', self.user_checkbox_width))
            # elif (widget_class == self._widgets.Output):
                # kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'overflow', 'scroll hidden')
            else:
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', None))
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'height', kwargs.get('height', None))
            # Finally, update the layout parameter in kwargs
            kwargs = utils.update_kwargs_param(kwargs, 'layout', self._widgets.Layout(**kwargs_layout))

            # Apply continuous_update setting
            kwargs = utils.update_kwargs_param(kwargs, 'continuous_update', self.continuous_update)

            # Set default values for some widgets
            if (widget_class == self._widgets.Dropdown or
                widget_class == self._widgets.RadioButtons or
                widget_class == self._widgets.Select or
                widget_class == self._widgets.ToggleButtons
                ):
                kwargs = utils.update_kwargs_param(kwargs, 'options', [])
                kwargs = utils.update_kwargs_param(kwargs, 'value', None)
            elif (widget_class == self._widgets.SelectMultiple):
                kwargs = utils.update_kwargs_param(kwargs, 'options', [])
                # kwargs = utils.update_kwargs_param(kwargs, 'value', [])
            elif (widget_class == self._widgets.Text or
                widget_class == self._widgets.Textarea or
                widget_class == self._widgets.Password):
                kwargs = utils.update_kwargs_param(kwargs, 'placeholder', 'Type here')
            elif (widget_class == self._widgets.Combobox):
                kwargs = utils.update_kwargs_param(kwargs, 'placeholder', 'Choose one')
            elif (widget_class == self._widgets.Checkbox):
                kwargs = utils.update_kwargs_param(kwargs, 'indent', False)

            # set rows automatically to the length of options, minimum 2
            if (widget_class == self._widgets.Select or
                widget_class == self._widgets.SelectMultiple
                ):
                kwargs = utils.update_kwargs_param(kwargs, 'rows', max(2, len(kwargs.get('options'))))
            # Post-method call - End

            # Call original methods
            obj = widget_class(*args, **kwargs)

            # Post-method call - Begin
            # Set callback function
            if widget_class == self._widgets.Output: # skip for Output widget
                pass
            elif widget_class == self._widgets.Button: # Set on_click callback for Button widget
                if 'cb' in kwargs:
                    obj.on_click(kwargs['cb'])
                else:
                    obj.on_click(self.default_cb)
            else:  # Set observe callback for all other widgets
                if 'cb' in kwargs:
                    obj.observe(kwargs['cb'], 'value')
                else:
                    obj.observe(self.default_cb)

            # Display widget according to 'show_widget_on_create' setting or 'show' argument
            if 'show' in kwargs:
                if kwargs['show'] == True:
                    display(obj)
            else:
                if self.show_widget_on_create:
                    display(obj)
            # Post-method call section - End

            return obj
        return wrapper

# widget class that contains two multi-select widgets, and buttons to move items between the two widgets, move items up and down, sort items, and clear items
class MultiSelectMoveButtons:
    def __init__(self, select_L_onchange_cb=None, select_R_onchange_cb=None, R_options_onchange_cb=None, sanitize_cb=None, show=False):
        self.w = Widgets()
        self.w.show_widget_on_create = False
        if select_L_onchange_cb==None:
            self.select_L = self.w.SelectMultiple(rows=12)
        else:
            self.select_L = self.w.SelectMultiple(rows=12, cb=select_L_onchange_cb)
        self.add_button = self.w.Button(icon='plus', width='40px', cb=self.add)
        self.remove_button = self.w.Button(icon='minus', width='40px', cb=self.remove)
        self.move_up_button = self.w.Button(icon='chevron-up', width='40px', cb=self.move_up)
        self.move_down_button = self.w.Button(icon='chevron-down', width='40px', cb=self.move_down)
        self.sort_button = self.w.Button(icon='sort-alpha-asc', width='40px', cb=self.sort_select_R)
        self.clear_button = self.w.Button(icon='trash', width='40px', cb=self.clear_select_R)
        if select_R_onchange_cb==None:
            self.select_R = self.w.SelectMultiple(rows=12)
        else:
            self.select_R = self.w.SelectMultiple(rows=12, cb=select_R_onchange_cb)
        if sanitize_cb:
            self.sanitize_selection = sanitize_cb
        else:
            self.sanitize_selection = None
        if R_options_onchange_cb:
            self.select_R.observe(R_options_onchange_cb, 'options')

        # Create the widget layout
        buttons = [
            self.add_button,
            self.remove_button,
            self.move_up_button,
            self.move_down_button,
            self.sort_button,
            self.clear_button,
        ]

        self.widget = self.w.HBox([
            self.select_L,
            self.w.VBox(buttons),
            self.select_R,
            ])
        if show:
            display(self.widget)

    def add(self, sender):
        # if at least one item is selected
        if self.select_L.value:
            if self.sanitize_selection:
                options = self.sanitize_selection(self.select_R.options)
            else:
                options = self.select_R.options
            self.select_R.options = [x for x in self.select_R.options] + [x for x in self.select_L.value if x not in options]
    def remove(self, sender):
        # if at least one item is selected
        if self.select_R.value:
            self.select_R.options = [x for x in self.select_R.options if x not in self.select_R.value]
    def move_up(self, sender):
        # if at least one item is selected
        if self.select_R.value:
            select_R = self.select_R.value
            select_R_index = self.select_R.options.index(select_R[0])
            if select_R_index > 0:
                new_options = [x for x in self.select_R.options if x not in select_R]
                # insert all the selected items before the select_R index
                for i, item in enumerate(select_R):
                    new_options.insert(select_R_index-1+i, item)
                self.select_R.options = new_options
                # restore original selection
                self.select_R.value = select_R
    def move_down(self, sender):
        # if at least one item is selected
        if self.select_R.value:
            select_R = self.select_R.value
            select_R_index = self.select_R.options.index(select_R[0])
            if select_R_index < len(self.select_R.options)-1:
                new_options = [x for x in self.select_R.options if x not in select_R]
                # insert all the selected items after the select_R index
                for i, item in enumerate(select_R):
                    new_options.insert(select_R_index+1+i, item)
                self.select_R.options = new_options
                # restore original selection
                self.select_R.value = select_R
    def sort_select_R(self, sender):
        self.select_R.options = sorted(self.select_R.options, key=utils.natural_sort_key)
    def clear_select_R(self, sender):
        self.select_R.options = []


class TabbedTextareaPanel:
    """A Tab widget containing one scrollable Textarea per tab.

    A generic, reusable panel for displaying pre-formatted text in tabbed
    panes.  The number of tabs and their titles are fully configurable.
    Injected CSS gives each Textarea native OS scrollbars, no text-wrap,
    and no resize handle.

    Attributes:
        outputs (list[Textarea]): One Textarea per tab, in title order.
        tab (Tab): The ipywidgets Tab widget.
        css (HTML): Invisible CSS injection widget; must be included
            somewhere in the displayed widget tree.

    Args:
        w (Widgets): A ``Widgets`` proxy instance (``show_widget_on_create``
            should be ``False`` before calling).
        tab_titles (sequence[str]): Ordered tab title strings.  One
            Textarea is created for each title.
            Defaults to ``('Result', 'Source Code')``.
        min_width (str): CSS ``min-width`` for the Tab widget.
            Defaults to ``'300px'``.

    Usage::

        from utils.standalone.widget_utils import TabbedTextareaPanel
        panel = TabbedTextareaPanel(w, tab_titles=['Output', 'Log', 'Source'])
        panel.outputs[0].value = 'Hello!'
        display(panel.tab)   # or embed panel.tab in an HBox
    """

    _CSS = '''<style>
        .widget-textarea textarea { white-space: pre; overflow: auto; resize: none; }
        [class*="TabPanel-tabContents"] { padding: 0 !important; overflow: hidden !important; }
        [class*="TabPanel"] { overflow: hidden !important; }
        .widget-tab { overflow: hidden !important; }
    </style>'''

    def __init__(self, w: Widgets, tab_titles=('Text'), min_width='300px'):
        self.outputs = [w.Textarea(disabled=True, width='100%', height='100%') for _ in tab_titles]
        self.tab     = w.Tab(children=self.outputs)
        for i, title in enumerate(tab_titles):
            self.tab.set_title(i, title)
        self.tab.layout.flex      = '1'
        self.tab.layout.min_width = min_width
        self.tab.layout.overflow  = 'hidden'
        self.css = w.HTML(self._CSS)


def build_lib_demo_widget(instance, lib_demo_params: list, extra_tabs: list = None, title: str = None, no_interface_wrap: bool = True):
    """Build a Jupyter widget GUI driven by a lib_demo_params list.

    Generic widget builder for any class exposing ``lib_demo_params`` — both
    utils standalone classes and Equipment subclasses.

    Args:
        instance: The object whose methods (or lambdas) are called by buttons.
        lib_demo_params: Primary list of demo-entry dicts (lib_demo_params schema).
        extra_tabs: Optional list of ``(tab_title, params_list)`` tuples.  Each
            entry adds a sibling button-tab whose buttons share the same output
            widget as the main params.  Used by Equipment to add an
            'Equipment Control' tab alongside 'Instrument Demo'.
        title: Initial text shown in the Result textarea.  Defaults to the class name.
        no_interface_wrap: When False, calls ``instance.interface_open()`` /
            ``interface_close()`` around each button click (Equipment behaviour).

    ``lib_demo_params`` entry schema::

        {
            'key': 'a',            # single-char shortcut for demo_text() menu
            'name': 'My Action',   # display name / button label
            'function': 'method',  # method name string or lambda (self, **kwargs)
            'inputs': [
                {
                    'label':       'My Param',   # widget label (falls back to 'name')
                    'name':        'param',       # kwarg name passed to function
                    'type':        float,         # int | float | str | bool (ignored when 'options' set)
                    'default':     1.0,           # pre-filled value
                    'options':     ['a', 'b'],    # renders Dropdown; 'default' must be one of these
                    'width':       '80px',        # CSS widget width (default '50px')
                    'placeholder': 'hint',        # grey placeholder text
                    'allow_empty': True,          # renders Text (not FloatText/IntText) so the
                                                  # field can be left blank → passes None to function
                    'password':    True,          # renders Password widget (hides typed text)
                    'type':        bool,          # renders Checkbox when bool
                },
            ],
            'button_alt_label': 'Alt\nLabel',    # override button label (optional)
            'same_row':         True,            # place this entry on the same row as the previous one
            'fill_targets': {                    # auto-fill another entry's input after this button runs.
                'OtherEntry.param_name': 'key',  #   key: dict key, list index, or True for scalar result.
            },                                   #   Target must match "<entry name>.<input name>" exactly.
        }

    Returns:
        ipywidgets.HBox: ``HBox([output_tab, buttons_panel])`` ready to display.
        Access ``result.children[0].children[0]`` for the Result textarea and
        ``.children[1]`` for the Source Code textarea.
    """
    import contextlib
    import inspect
    import textwrap

    _title = title or type(instance).__name__

    w = Widgets()
    w.show_widget_on_create = False

    _tab_panel = TabbedTextareaPanel(w, tab_titles=('Result', 'Source Code'))
    w_output        = _tab_panel.outputs[0]
    w_source_output = _tab_panel.outputs[1]
    w_tab           = _tab_panel.tab
    w_css           = _tab_panel.css

    def _demo_button_click(sender, demo_entry, input_bindings):
        function_ref = demo_entry['function']

        # Show source code in the Source Code tab before running.
        # For lambda wrappers, scan the lambda source for the first method name on the instance
        # and show that method's source instead of the lambda itself.
        try:
            if callable(function_ref) and function_ref.__name__ == '<lambda>':
                lambda_src = inspect.getsource(function_ref)
                src_func = next(
                    (getattr(instance, name) for name in dir(instance)
                     if not name.startswith('_') and callable(getattr(instance, name, None))
                     and f'self.{name}(' in lambda_src),
                    function_ref,
                )
            else:
                src_func = function_ref if callable(function_ref) else getattr(instance, function_ref)
            source = textwrap.dedent(inspect.getsource(src_func))
            w_source_output.value = f'Demo: {demo_entry["name"]}\n{"="*80}\n{source}'
        except (OSError, TypeError) as e:
            w_source_output.value = f'Could not retrieve source code for "{demo_entry["name"]}": {e}'

        kwargs = {}
        for inp, (arg_name, widget) in zip(demo_entry.get('inputs', []), input_bindings):
            kwargs[arg_name] = resolve_demo_input(inp, widget.value)
        func_display_name = getattr(src_func, '__name__', str(demo_entry['function']))
        call_str = f'{func_display_name}(' + ', '.join(f'{k}={v!r}' for k, v in kwargs.items()) + ')'
        w_output.value = (
            f'Running Demo: {demo_entry["name"]}...\n'
            f'function: {demo_entry["function"]}, args: {list(kwargs.values())}\n'
            f'{call_str}\n'
            f'{"="*80}\n'
        )

        _no_wrap = demo_entry.get('no_interface_wrap', no_interface_wrap)
        try:
            if not _no_wrap:
                instance.interface_open()

            value_before_call = w_output.value
            # Redirect stdout to the Result textarea so print() and comm-log records
            # (which flow through _EquipmentConsoleHandler → sys.stdout) both appear there.
            #
            # We use contextlib.redirect_stdout(WidgetStdout(w_output)) instead of
            # the idiomatic `with w_output:` because the Output widget context manager
            # routes IOPub messages to the widget AND can append them a second time
            # when the context exits, causing 4× duplication in some JupyterLab
            # environments.  WidgetStdout bypasses IOPub entirely and writes
            # directly to w_output.value, giving exactly one copy.
            #
            # The _EquipmentConsoleHandler also picks this up automatically because
            # its .stream property resolves sys.stdout dynamically.
            with contextlib.redirect_stdout(WidgetStdout(w_output)):
                result = call_demo_function(instance, demo_entry, kwargs)

            # Append return value only if it is not already represented in what
            # was printed during the call.  Functions that both print() and return
            # the same content should not produce duplicates, while functions that
            # return a different/additional value should still show it.
            # Comparison is done line-by-line (not substring) so that a short return
            # value like "SOURCEVOLT" is not suppressed just because it appears as a
            # substring inside a comm-log line (e.g. "SER <- SMU4201 : 'SOURCEVOLT\r\n'").
            if result is not None:
                printed_delta = w_output.value[len(value_before_call):]
                result_str = "\n".join(str(item) for item in result) if isinstance(result, list) else str(result)
                printed_lines = {line.strip() for line in printed_delta.splitlines()}
                if result_str.strip() not in printed_lines:
                    w_output.value += result_str

                # fill_targets: dict mapping "OtherEntry.param_name" → key/index into result.
                # If result is a dict, value is used as a key; if a list/tuple, as an index;
                # if a scalar (str/int/float), the sentinel True or 0 copies it directly.
                # Example: 'fill_targets': {'Connect.ip': 0, 'Read.tag': 'tag_name'}
                for target_key, selector in demo_entry.get('fill_targets', {}).items():
                    target_widget = _input_registry.get(target_key)
                    if target_widget is None:
                        continue
                    try:
                        if callable(selector):
                            fill_val = selector(result)
                        elif isinstance(result, dict):
                            fill_val = result[selector]
                        elif isinstance(result, (list, tuple)):
                            fill_val = result[selector]
                        else:
                            fill_val = result
                        target_widget.value = type(target_widget.value)(fill_val)
                    except (KeyError, IndexError, TypeError, ValueError):
                        pass
        except Exception as e:
            w_output.value += f"\nError: {e}"
            # # Debug traceback for the exception:
            # import traceback
            # w_output.value += f"\nTraceback:\n{traceback.format_exc()}"
        finally:
            if not _no_wrap:
                instance.interface_close()
            # Add 'Done' at the end of the first line to indicate completion — some
            # functions may not print or return a value, so without this the user
            # won't know when the function has finished.
            w_output.value = w_output.value.replace('...', '... Done', 1)

    # Registry: maps "<entry_name>.<input_name>" → widget, populated as widgets are built.
    # Stored on w_main after construction so callers can also access it.
    _input_registry = {}

    def _build_button_rows(params_list):
        rows = []
        current_row_items = []
        for demo_entry in params_list:
            inputs = demo_entry.get("inputs")
            try:
                w_label_list = []
                w_input_list = []
                if inputs:
                    for inp in inputs:
                        label_text = inp.get("label", inp.get("name", ""))
                        w_label_list.append(w.Label(f'{label_text}: '))
                        input_type = inp.get("type", str)
                        default_width = 'auto' if input_type == bool else '50px'
                        width = inp.get("width", default_width)
                        if inp.get("options"):
                            _options = inp["options"]
                            _default = inp.get("default")
                            _value = _default if _default in _options else _options[0]
                            w_input = w.Dropdown(options=_options, value=_value, width=width)
                        elif 'allow_empty' in inp:
                            # Fields that may be left blank are rendered as Text/Password so the
                            # user can clear them; resolve_demo_input converts '' → None.
                            _default = inp.get("default")
                            _str_val = '' if _default is None else str(_default)
                            if inp.get("password"):
                                w_input = w.Password(value=_str_val, width=width, placeholder=inp.get("placeholder", ''))
                            else:
                                w_input = w.Text(value=_str_val, width=width, placeholder=inp.get("placeholder", ''))
                        else:
                            input_type = inp.get("type", str)
                            if input_type == int:
                                w_input = w.IntText(value=inp.get("default"), width=width, placeholder=inp.get("placeholder", ''))
                            elif input_type == float:
                                w_input = w.FloatText(value=inp.get("default"), width=width, placeholder=inp.get("placeholder", ''))
                            elif input_type == bool:
                                w_input = w.Checkbox(value=bool(inp.get("default", False)), width=width)
                            elif inp.get("password"):
                                # Password widget masks input — value is still a plain string.
                                w_input = w.Password(value=inp.get("default", ''), width=width, placeholder=inp.get("placeholder", ''))
                            else:
                                w_input = w.Text(value=inp.get("default", ''), width=width, placeholder=inp.get("placeholder", ''))
                        w_input_list.append(w_input)
                        _input_registry[f'{demo_entry["name"]}.{inp.get("name", "")}'] = w_input

                button_label = demo_entry.get("button_alt_label", demo_entry["name"])
                disabled_if = demo_entry.get('disabled_if')
                is_disabled = disabled_if(instance) if disabled_if else False
                input_bindings = [(inp.get('name'), widget) for inp, widget in zip(inputs or [], w_input_list)]

                w_button = w.Button(
                    desc=button_label,
                    cb=lambda sender, de=demo_entry, ib=input_bindings: _demo_button_click(sender, de, ib),
                    width='auto',
                    disabled=is_disabled)
                w_item = w.HBox([
                    *[w.HBox([label, inp_widget]) for label, inp_widget in zip(w_label_list, w_input_list)],
                    w_button])

                if not demo_entry.get('same_row', False) and current_row_items:
                    rows.append(w.HBox(current_row_items))
                    current_row_items = []
                current_row_items.append(w_item)
            except KeyError as e:
                print(f'Malformed demo entry "{demo_entry.get("name", "?")}": missing key {e}')
        if current_row_items:
            rows.append(w.HBox(current_row_items))
        return rows

    _MIN_DEMO_BUTTONS = 5
    _placeholder = {'key': '-', 'name': 'Placeholder', 'no_interface_wrap': True,
                    'function': lambda self: None, 'inputs': [],
                    'disabled_if': lambda self: True}
    _padded_params = list(lib_demo_params) + [_placeholder] * max(0, _MIN_DEMO_BUTTONS - len(lib_demo_params))

    w_rows = _build_button_rows(_padded_params)
    w_instr_content = w.VBox(w_rows) if w_rows else w.Label('No demo functions defined.')

    if extra_tabs:
        # Multiple tabs share the same output widget — wrap buttons in a Tab on the right side.
        tab_titles = ['Instrument Demo'] + [t for t, _ in extra_tabs]
        tab_contents = [w_instr_content]
        for _, extra_params in extra_tabs:
            extra_rows = _build_button_rows(extra_params)
            tab_contents.append(w.VBox(extra_rows) if extra_rows else w.Label('No functions defined.'))
        w_buttons_tab = w.Tab(children=tab_contents)
        for i, t in enumerate(tab_titles):
            w_buttons_tab.set_title(i, t)
        # CSS must appear somewhere in the displayed tree.
        w_buttons_vbox = w.VBox([w_css, w_buttons_tab])
    else:
        # CSS must appear somewhere in the displayed tree.
        w_buttons_vbox = w.VBox([w_css, w_instr_content])

    w_main = w.HBox([w_tab, w_buttons_vbox], width='100%')
    w_main.layout.align_items = 'stretch'
    w_main._input_registry    = _input_registry   # expose for external pre-fill
    w_main._build_button_rows = _build_button_rows # closure: (params_list,) → list[HBox]
    w_main._buttons_vbox      = w_instr_content    # live-mutable main-tab buttons VBox
    w_output.value        = f'{_title} \u2014 click a button to run a demo function.'
    w_source_output.value = 'Source code will appear here when a demo button is clicked.'
    # Return widget instead of calling display() — returning lets JupyterLab display
    # it as the cell's natural last-expression output, which is reliable in both
    # JupyterLab and VS Code Jupyter. Callers can also pass the result to display().
    return w_main


class WidgetStdout:
    """File-like stdout replacement that writes directly to an ipywidgets widget.

    Used with ``contextlib.redirect_stdout`` to capture ``print()`` output
    (and ``logging.StreamHandler`` writes) inside a demo button callback and
    forward them live to either an ``Output`` widget or a ``Textarea`` widget,
    depending on what is passed.

    Using this instead of the ``with output_widget:`` context manager avoids
    the 4x duplication that can occur in some JupyterLab environments when
    IOPub messages are routed to the widget *and* appended again on context
    exit.  ``WidgetStdout`` bypasses IOPub entirely and writes directly to
    ``output_widget.append_stdout()`` (``Output``) or ``widget.value +=``
    (``Textarea``), giving exactly one copy of each line.

    Args:
        output_widget: An ipywidgets ``Output`` or ``Textarea`` widget.

    Usage::

        import contextlib
        from utils.standalone.widget_utils import WidgetStdout
        with contextlib.redirect_stdout(WidgetStdout(w_output)):
            some_function()
    """

    def __init__(self, output_widget):
        self._widget = output_widget
        self._ansi_re = re.compile(r'\x1b\[[0-9;]*m')

    def write(self, s):
        if s:  # skip empty writes
            s = self._ansi_re.sub('', s)  # strip ANSI colour codes — widgets don't render them
            if hasattr(self._widget, 'outputs'):  # ipywidgets Output widget
                self._widget.append_stdout(s)
            else:                                  # ipywidgets Textarea widget
                self._widget.value += s

    def flush(self):
        pass

    def isatty(self):
        return False


# folder browser for picking a file: drive list, folder box, optional home button, and a list of folders and matching files
class FileBrowser:
    """Pick a file by browsing folders, in plain ipywidgets (no extra package). It browses the file system of the
    PC that runs the Jupyter kernel, also when Jupyter is used from another PC's browser.

    Click a folder (📁) to open it, ⬆ .. to go up, a file to pick it; or type a folder in the folder box, or choose a
    drive. Errors (folder not found, no access) show in a line under the list.

    start: first folder (default: the current working directory).
    patterns: file name patterns to list (fnmatch, case-insensitive), e.g. ('*.py',); folders are always listed.
    on_pick: called with the picked file's Path.
    home / home_label: a button that goes back to `home` (e.g. a repo root), if given.
    skip_dirs: folder names never listed (dot folders are skipped unless show_hidden).
    Attributes: widget (the VBox to display), folder (Path shown), picked (Path or None).
    """
    SKIP_DIRS = ('__pycache__', '.ipynb_checkpoints')
    _UP, _DIR = '⬆ ..', '📁 '

    def __init__(self, start=None, patterns=('*',), on_pick=None, home=None, home_label='Home',
                 skip_dirs=SKIP_DIRS, show_hidden=False, rows=10, width='760px', show=False):
        import fnmatch, os, string
        from pathlib import Path
        self._fnmatch, self._os, self._Path = fnmatch, os, Path
        self.w = Widgets()
        self.w.show_widget_on_create = False
        self.patterns = tuple(p.lower() for p in patterns)
        self.on_pick = on_pick
        self.skip_dirs = set(skip_dirs)
        self.show_hidden = show_hidden
        self.picked = None
        self._syncing = False
        if os.name == 'nt':
            drives = [f'{d}:\\' for d in string.ascii_uppercase if os.path.exists(f'{d}:\\')]
        else:
            drives = ['/']
        self.drive_dd = self.w.Dropdown(options=drives, value=drives[0] if drives else None, width='80px',
                                        cb=lambda ch: self._guard(self._drive_changed, ch))
        self.dir_text = self.w.Text(width=f'calc({width} - 180px)', placeholder='folder',
                                    cb=lambda ch: self._guard(self._dir_typed, ch))
        self.home = Path(home) if home else None
        self.home_btn = self.w.Button(desc=home_label, icon='home', width='90px', tooltip=str(home or ''),
                                      cb=lambda _: self._guard(self.browse_to, self.home))
        self.select = self.w.Select(options=[], rows=rows, width=width, cb=lambda ch: self._guard(self._picked, ch))
        self.status = self.w.HTML()
        bar = [self.drive_dd, self.dir_text] + ([self.home_btn] if self.home else [])
        self.widget = self.w.VBox([self.w.HBox(bar), self.select, self.status])
        self.folder = None
        self._guard(self.browse_to, start or os.getcwd())
        if show:
            display(self.widget)

    def _guard(self, fn, *args):
        """Run a callback; show a ValueError / OSError in the status line instead of losing it in the kernel log."""
        try:
            self.status.value = ''
            fn(*args)
        except (ValueError, OSError) as e:
            self.status.value = f'<span style="color:#c0392b">{e}</span>'

    def _sync(self, widget, attr, value):
        self._syncing = True
        try:
            setattr(widget, attr, value)
        finally:
            self._syncing = False

    def _matches(self, name: str) -> bool:
        n = name.lower()
        return any(self._fnmatch.fnmatch(n, p) for p in self.patterns)

    def browse_to(self, folder):
        """Show `folder`'s subfolders and matching files (ValueError if it isn't a folder or can't be read)."""
        folder = self._Path(str(folder).strip().strip('"'))
        if not folder.is_dir():
            raise ValueError(f'Not a folder: {folder}')
        entries = []
        try:
            for e in sorted(self._os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower())):
                if (e.name.startswith('.') and not self.show_hidden) or e.name in self.skip_dirs:
                    continue
                if e.is_dir():
                    entries.append((self._DIR + e.name, e.path))
                elif self._matches(e.name):
                    entries.append((e.name, e.path))
        except PermissionError:
            raise ValueError(f'No access to {folder}') from None
        if folder.parent != folder:
            entries.insert(0, (self._UP, str(folder.parent)))
        self.folder = folder
        self._sync(self.select, 'options', entries)
        self._sync(self.select, 'value', None)
        self._sync(self.dir_text, 'value', str(folder))
        drive = folder.anchor.upper() if self._os.name == 'nt' else '/'
        if drive in self.drive_dd.options:
            self._sync(self.drive_dd, 'value', drive)

    def clear_selection(self):
        """Forget the picked file and unselect the list (the folder stays)."""
        self.picked = None
        self._sync(self.select, 'value', None)

    def _picked(self, change):
        if self._syncing or not change['new']:
            return
        p = self._Path(change['new'])
        if p.is_dir():
            self.browse_to(p)
        else:
            self.picked = p
            if self.on_pick:
                self.on_pick(p)

    def _drive_changed(self, change):
        if not self._syncing and change['new']:
            self.browse_to(change['new'])

    def _dir_typed(self, change):
        if not self._syncing and change['new'].strip():
            self.browse_to(change['new'])
