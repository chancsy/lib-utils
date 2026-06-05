# Coerce a single raw user value (from CLI or widget) according to an inp-dict spec.
# Returns the typed value, or None if the input is empty and allow_empty is set.
def resolve_demo_input(inp: dict, raw):
    options = inp.get('options')
    if options:
        # raw is already the chosen option value at this point (CLI resolves it before calling).
        return raw
    allow_empty = inp.get('allow_empty', inp.get('default') is not None)
    if allow_empty:
        stripped = str(raw).strip() if raw is not None else ''
        if not stripped:
            return None
        input_type = inp.get('type', str)
        try:
            return input_type(stripped)
        except (ValueError, TypeError):
            return None
    return raw


# Dispatch a lib_demo_params function call using pre-built kwargs.
# Handles both string method names and callables (lambdas).
def call_demo_function(instance, entry: dict, kwargs: dict):
    function_ref = entry['function']
    if callable(function_ref):
        return function_ref(instance, **kwargs) if kwargs else function_ref(instance)
    func = getattr(instance, function_ref)
    return func(**kwargs) if kwargs else func()


class UtilityDemoMixin:
    def show_demo_menu(self, menu_dict, max_columns=8, max_width=80):
        number_len = 4
        col_widths = []
        columns = []
        col_start = 0

        for i in range(max_columns):
            col_end = col_start + len(menu_dict) // max_columns + (1 if i < len(menu_dict) % max_columns else 0)
            col = menu_dict[col_start:col_end]
            col_width = max(len(entry['name']) for entry in col) + number_len if col else 0
            col_widths.append(col_width)
            columns.append(col)
            col_start = col_end

        total_width = sum(col_widths) + 2 * (max_columns - 1)

        while total_width > max_width and max_columns > 1:
            max_columns -= 1
            col_widths = []
            columns = []
            col_start = 0

            for i in range(max_columns):
                col_end = col_start + len(menu_dict) // max_columns + (1 if i < len(menu_dict) % max_columns else 0)
                col = menu_dict[col_start:col_end]
                col_width = max(len(entry['name']) for entry in col) + number_len if col else 0
                col_widths.append(col_width)
                columns.append(col)
                col_start = col_end

            total_width = sum(col_widths) + 2 * (max_columns - 1)

        max_rows = max(len(col) for col in columns)
        for row_idx in range(max_rows):
            row_entries = []
            for col_idx, col in enumerate(columns):
                if row_idx < len(col):
                    entry = col[row_idx]
                    row_entries.append(f"{entry['key']}. {entry['name']}".ljust(col_widths[col_idx]))
                else:
                    row_entries.append(''.ljust(col_widths[col_idx]))
            print('  '.join(row_entries).rstrip())
        print()

    def get_demo_desc(self, menu_dict, key):
        return next((entry['name'] for entry in menu_dict if entry['key'] == key), 'Unknown demo')

    def _run_lib_demo_params_entry(self, instance, entry: dict):
        """Prompt for each input defined in a lib_demo_params entry and call the function."""
        kwargs = {}
        for inp in entry.get('inputs', []):
            label   = inp.get('label', inp.get('name', inp['name']))
            name    = inp['name']
            default = inp.get('default')
            options = inp.get('options')
            if options:
                # Show numbered options list and let user pick by number or value.
                print(f'  {label}:')
                for i, opt in enumerate(options):
                    marker = ' *' if opt == default else ''
                    print(f'    {i+1}. {opt}{marker}')
                raw = input(f'  Choice (1-{len(options)}, default={default}): ').strip()
                if not raw and default is not None:
                    raw = default
                elif raw.isdigit() and 1 <= int(raw) <= len(options):
                    raw = options[int(raw) - 1]
                else:
                    raw = raw or default
            else:
                input_type = inp.get('type', str)
                allow_empty = inp.get('allow_empty', default is not None)
                raw = self.get_user_input(label, input_type, default, allow_empty=allow_empty)
                if raw is None and not inp.get('allow_empty'):
                    print('  Input cancelled.')
                    return None
            kwargs[name] = resolve_demo_input(inp, raw)

        return call_demo_function(instance, entry, kwargs)

    def demo(self, _class):
        instr_has_lib_demo_params = hasattr(_class, 'lib_demo_params')
        instr_has_lib_demo_dict   = hasattr(_class, 'lib_demo_dict')
        instr_has_lib_demo        = hasattr(_class, 'lib_demo')

        # lib_demo_params takes precedence — auto-driven CLI (no lib_demo() needed).
        if instr_has_lib_demo_params:
            menu = [{'key': e['key'], 'name': e['name']} for e in _class.lib_demo_params]
            last_result = None
            while True:
                self.show_demo_menu(menu)
                key = input('Enter demo number (q to quit): ').strip().lower()
                if key in ('q', 'quit', 'exit'):
                    return last_result
                entry = next((e for e in _class.lib_demo_params if e['key'] == key), None)
                if entry is None:
                    print('Unknown demo number entered.')
                    continue
                last_result = self._run_lib_demo_params_entry(_class, entry)
                if last_result is not None:
                    print(last_result)

        # Legacy path: lib_demo_dict + lib_demo().
        if not instr_has_lib_demo_dict and not instr_has_lib_demo:
            print('This lib has no demo functions.')
            return None

        if not instr_has_lib_demo_dict and instr_has_lib_demo:
            result = _class.lib_demo()
            return result

        if instr_has_lib_demo_dict and instr_has_lib_demo:
            self.show_demo_menu(_class.lib_demo_dict)

        demo_num = input('Enter demo number: ')

        demo_num = demo_num.lower()
        demo_desc = self.get_demo_desc(_class.lib_demo_dict, demo_num)
        if demo_desc == 'Unknown demo':
            print('Unknown demo number entered.')
            return None
        try:
            result = _class.lib_demo(demo_desc)
            return result
        finally:
            pass
