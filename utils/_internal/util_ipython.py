import sys

try:
    from IPython.display import HTML, FileLink, clear_output, display
    from IPython import get_ipython
except ImportError:
    HTML = None
    FileLink = None
    clear_output = None
    display = None

    def get_ipython():
        return None


class UtilityIPythonMixin:
    HTML = HTML

    def in_ipython(self, print_warning=False):
        if 'ipykernel' in sys.modules:
            return True
        if print_warning:
            print('Not in IPython environment')
        return False

    def ipython_print_default_expr(self):
        if self.in_ipython(print_warning=True):
            from IPython.core.interactiveshell import InteractiveShell
            InteractiveShell.ast_node_interactivity = 'last_expr'

    def ipython_print_all_exprs(self):
        if self.in_ipython(print_warning=True):
            from IPython.core.interactiveshell import InteractiveShell
            InteractiveShell.ast_node_interactivity = 'all'

    def ipython_run_magic_command(self, magic_name, line):
        if self.in_ipython(print_warning=True):
            self.ipython.run_line_magic(magic_name, line)

    def ipython_auto_reload_modules(self, print_warning=True):
        if not self.in_ipython(print_warning=True):
            return None
        self.ipython_run_magic_command('reload_ext', 'autoreload')
        self.ipython_run_magic_command('autoreload', '2')
        if print_warning:
            print('Auto reload is enabled. Not recommended for production code. Be careful with side effects.')
        return True

    def ipython_reset_namespace(self):
        if not self.in_ipython(print_warning=True):
            return None
        self.ipython_run_magic_command('reset', '-f')
        print('IPython namespace is reset.')
        return True

    def exit_if_not_in_ipython(self):
        if not self.in_ipython():
            print('This script is intended to be run in IPython environment')
            sys.exit(1)

    def exit_silent(self, message=''):
        class StopExecution(Exception):
            def _render_traceback_(self):
                pass

        if self.in_ipython():
            if message:
                print(message)
            raise StopExecution
        else:
            sys.exit(message)

    def override_sys_exit_in_ipython(self):
        if self.in_ipython() and not type(self)._sys_exit_overridden:
            sys.exit = self.exit_silent
            print('sys.exit() is overridden to exit silently in IPython environment.')
            type(self)._sys_exit_overridden = True

    def display_filelink(self, link, prefix=''):
        if display is None or FileLink is None:
            raise ImportError('IPython is required for display_filelink()')
        display(FileLink(link, result_html_prefix=prefix))

    def clear_output(self):
        if self.in_ipython() and clear_output is not None:
            clear_output()

    def get_ipython_handle(self):
        return get_ipython()
