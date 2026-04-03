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

    def demo(self, _class):
        instr_has_lib_demo_dict = hasattr(_class, 'lib_demo_dict')
        instr_has_lib_demo = hasattr(_class, 'lib_demo')

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
