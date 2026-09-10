import os
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

    def runpy_run_path(self, py_path, run_name='__main__', argv=None, into_namespace=False, in_thread=False):
        """Run a .py file the way ``python <path>`` / IPython's ``%run`` would, but as a
        plain function call. The file runs in a throwaway module namespace with
        ``__name__ == run_name`` ('__main__' by default), so ``if __name__ == '__main__':``
        blocks fire; the resulting globals dict is returned.

        argv           - sys.argv for the run, restored afterwards. None fakes a bare
                         ``python <script>.py`` (basename only) - needed because a Jupyter
                         kernel's real sys.argv holds its own connection-file args, which
                         break scripts that call argparse. Pass a full list (incl. a dummy
                         argv[0]) to run with specific CLI flags.
        into_namespace - after the run, merge the script's top-level names into the caller's
                         namespace (the IPython user namespace in a kernel), like %run does.
        in_thread      - run in a worker thread. A Jupyter kernel executes cell code inside a
                         live asyncio loop, which some libraries reject (e.g. Playwright's
                         sync API: "Sync API inside the asyncio loop"); a worker thread has
                         no running loop. True always threads; 'auto' threads only when a
                         running loop is detected. Caveat: a threaded run can't be stopped
                         with Ctrl-C, and input()/signal.signal() from the script may
                         misbehave - leave it off for interactive scripts.
        """
        import runpy

        orig_argv = sys.argv
        # caller-supplied argv as-is, else fake a bare "python <script>.py" (basename only)
        sys.argv = argv if argv is not None else [os.path.basename(py_path)]

        # Prepend the script's own directory to sys.path so its sibling-module imports
        # resolve - runpy.run_path doesn't do this for a plain .py file, unlike
        # "python <script>.py" and %run. Add only if absent; remove only if we added it.
        script_dir = os.path.dirname(os.path.abspath(py_path))
        added_script_dir = script_dir not in sys.path
        if added_script_dir:
            sys.path.insert(0, script_dir)

        if in_thread == 'auto':
            import asyncio
            try:
                asyncio.get_running_loop()
                in_thread = True
            except RuntimeError:
                in_thread = False

        def _run():
            # In a worker thread on Windows the fresh loop Playwright creates inherits the
            # kernel's Selector-loop policy (tornado sets it), which can't spawn subprocesses
            # - Playwright's driver launch then dies with NotImplementedError. Swap to the
            # Proactor policy for the duration; the kernel's already-running loop is
            # unaffected (policy only governs loops created afterwards).
            restore_policy = None
            if in_thread and sys.platform == 'win32':
                import asyncio
                if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
                    restore_policy = asyncio.get_event_loop_policy()
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            try:
                return runpy.run_path(py_path, run_name=run_name)
            finally:
                if restore_policy is not None:
                    asyncio.set_event_loop_policy(restore_policy)

        ns = {}
        try:
            if in_thread:
                import concurrent.futures
                ex = concurrent.futures.ThreadPoolExecutor(1)
                try:
                    ns = ex.submit(_run).result()  # re-raises the worker's exception (incl. SystemExit)
                finally:
                    ex.shutdown(wait=False)  # don't block if the caller interrupted mid-run
            else:
                ns = _run()
        except SystemExit as e:
            print(f'{py_path} exited with code {e.code}')
        finally:
            sys.argv = orig_argv
            if added_script_dir:
                try:
                    sys.path.remove(script_dir)
                except ValueError as e:
                    print(f'Could not remove {script_dir} from sys.path: {e}')

        if into_namespace:
            # Emulate %run: merge the script's top-level names into the caller's namespace.
            # Skip the module-machinery dunders - especially __builtins__, which would
            # corrupt the target environment.
            _skip = {'__name__', '__doc__', '__file__', '__cached__', '__loader__',
                     '__spec__', '__package__', '__builtins__'}
            target = self.get_ipython_handle().user_ns if self.in_ipython() else sys._getframe(1).f_globals
            target.update({k: v for k, v in ns.items() if k not in _skip})
        return ns

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

    def clear_output(self, wait=True):
        if self.in_ipython() and clear_output is not None:
            clear_output(wait=wait)

    def display(self, obj):
        if self.in_ipython() and display is not None:
            display(obj)

    def get_ipython_handle(self):
        return get_ipython()
