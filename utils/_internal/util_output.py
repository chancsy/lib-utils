import io
import sys


class TeeStringIO(io.StringIO):
    """A stdout-compatible buffer that writes to the real stdout live and captures to a string.

    Use with ``contextlib.redirect_stdout`` to get both progressive console
    output and a captured string for post-call inspection::

        import contextlib
        from utils import TeeStringIO

        tee = TeeStringIO()
        with contextlib.redirect_stdout(tee):
            some_function_that_prints()
        captured = tee.getvalue()
    """

    def __init__(self, real_stdout=None):
        super().__init__()
        self._real = real_stdout if real_stdout is not None else sys.stdout

    def write(self, s):
        self._real.write(s)
        return super().write(s)

    def flush(self):
        self._real.flush()
        super().flush()


class UtilityOutputMixin:
    def print_same_line(self, msg):
        if self.in_ipython():
            padding = ' ' * max(0, self._last_line_length - len(msg))
            self._last_line_length = len(msg)
            print('\r\033[2K'+msg+padding, end='')
        else:
            print('\r\033[2K'+msg, end='')
        self._progress_line_active = True

    def print_same_line_end(self):
        if self._progress_line_active:
            print()
            self._progress_line_active = False

    def print_progress(self, n, total):
        progress = (n+1)/total*100
        if progress >= 100:
            progress = 100
        self.print_same_line('Progress: ' + '{:.1f}'.format(progress) + ' %')
        if progress == 100:
            self.print_same_line_end()

    def print(self, *args, **kwargs):
        self.print_same_line_end()
        print(*args, **kwargs)

    def print_time_left(self, n, total):
        self.print_same_line(f'Waiting for {total}s... ({total-n}s)')
        if n >= total:
            print('\r')
