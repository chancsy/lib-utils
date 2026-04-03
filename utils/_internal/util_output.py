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
