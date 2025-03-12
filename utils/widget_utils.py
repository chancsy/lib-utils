from utils.utilities import *
utils = UtilityFunctions()
utils.exit_if_not_in_ipython()
utils.exit_if_module_missing('ipywidgets')

import ipywidgets as widgets

class Widgets:
    def __init__(self):
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
        widget_class = getattr(widgets, a)
        def wrapper(*args, **kwargs):
            # Pre-method call - Begin
            # Translate 'desc' argument to 'description' argument
            if 'desc' in kwargs:
                kwargs = utils.update_kwargs_param(kwargs, 'description', kwargs['desc'])

            # Get layout from kwargs, if not present, set to empty dict
            kwargs_layout = kwargs.get('layout', {})
            # Set default styles for widgets
            if (widget_class == widgets.Button):
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', self.user_button_width))
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'height', kwargs.get('height', self.user_button_height))
            elif (widget_class == widgets.Checkbox):
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', self.user_checkbox_width))
            # elif (widget_class == widgets.Output):
                # kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'overflow', 'scroll hidden')
            else:
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'width', kwargs.get('width', None))
                kwargs_layout = utils.update_kwargs_param(kwargs_layout, 'height', kwargs.get('height', None))
            # Finally, update the layout parameter in kwargs
            kwargs = utils.update_kwargs_param(kwargs, 'layout', widgets.Layout(**kwargs_layout))

            # Apply continuous_update setting
            kwargs = utils.update_kwargs_param(kwargs, 'continuous_update', self.continuous_update)

            # Set default values for some widgets
            if (widget_class == widgets.Dropdown or
                widget_class == widgets.RadioButtons or
                widget_class == widgets.Select or
                widget_class == widgets.ToggleButtons
                ):
                kwargs = utils.update_kwargs_param(kwargs, 'options', [])
                kwargs = utils.update_kwargs_param(kwargs, 'value', None)
            elif (widget_class == widgets.SelectMultiple):
                kwargs = utils.update_kwargs_param(kwargs, 'options', [])
                # kwargs = utils.update_kwargs_param(kwargs, 'value', [])
            elif (widget_class == widgets.Text or
                widget_class == widgets.Textarea or
                widget_class == widgets.Password):
                kwargs = utils.update_kwargs_param(kwargs, 'placeholder', 'Type here')
            elif (widget_class == widgets.Combobox):
                kwargs = utils.update_kwargs_param(kwargs, 'placeholder', 'Choose one')
            elif (widget_class == widgets.Checkbox):
                kwargs = utils.update_kwargs_param(kwargs, 'indent', False)

            # set rows automatically to the length of options, minimum 2
            if (widget_class == widgets.Select or
                widget_class == widgets.SelectMultiple
                ):
                kwargs = utils.update_kwargs_param(kwargs, 'rows', max(2, len(kwargs.get('options'))))
            # Post-method call - End

            # Call original methods
            obj = widget_class(*args, **kwargs)

            # Post-method call - Begin
            # Set callback function
            if widget_class == widgets.Output: # skip for Output widget
                pass
            elif widget_class == widgets.Button: # Set on_click callback for Button widget
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
