import calendar
import re
import threading
import time
from datetime import datetime, timedelta


class UtilityTimeMixin:
    def get_current_time(self):
        return time.time()

    def get_current_datetime(self):
        return datetime.now()

    def is_TimePassed(self, start_time, duration):
        return time.time() - start_time >= duration

    def wait_TimePassed(self, start_time, duration, tick_s=0.01):
        while not self.is_TimePassed(start_time, duration):
            time.sleep(0.01)

    def sleep(self, duration_s=1):
        t_start = time.time()
        self.wait_TimePassed(t_start, duration_s)

    def sleep_progress(self, duration):
        t_start = time.time()
        for n in range(duration):
            self.wait_TimePassed(t_start, n+1)
            self.print_time_left(n+1, duration)

    def get_last_day_of_month(self, year):
        return [datetime(year, month, calendar.monthrange(year, month)[1]) for month in range(1, 13)]

    def get_date(self, time_now, date_delim=''):
        return time_now.strftime(f'%Y{date_delim}%m{date_delim}%d')

    def get_timestamp(self, time_now=None, style=None, time_delim='', show_ms=False, ms_delim='', ms_digits=3):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: (time_delim, show_ms, ms_delim),
            0: (':', False, '.'),
            1: (':', True, '.'),
        }
        time_delim, show_ms, ms_delim = style_map.get(style, (time_delim, show_ms, ms_delim))
        if show_ms:
            milliseconds = round(time_now.microsecond / 1000)
            if milliseconds == 1000:
                time_now = time_now.replace(microsecond=0)
                milliseconds = 0
                time_now += timedelta(seconds=1)
            milliseconds_str = str(milliseconds).zfill(ms_digits)
            return time_now.strftime(f'%H{time_delim}%M{time_delim}%S{ms_delim}{milliseconds_str}')
        return time_now.strftime(f'%H{time_delim}%M{time_delim}%S')

    def get_datestamp(self, time_now=None, style=None, date_delim=''):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: date_delim,
            0: '-',
        }
        date_delim = style_map.get(style, date_delim)
        return self.get_date(time_now, date_delim)

    def get_datetimestamp(self, time_now=None, style=None, date_delim='', date_time_delim='', time_delim='', show_ms=False, ms_delim='', ms_digits=3):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: (date_delim, date_time_delim, time_delim, show_ms, ms_delim),
            0: ('-', ' ', ':', False, '.'),
            1: ('-', ' ', ':', True, '.'),
            2: ('-', ' ', '-', False, '.'),
        }
        date_delim, date_time_delim, time_delim, show_ms, ms_delim = style_map.get(style, (date_delim, date_time_delim, time_delim, show_ms, ms_delim))

        date_part = self.get_datestamp(time_now=time_now, style=style, date_delim=date_delim)
        time_part = self.get_timestamp(time_now=time_now, style=style, show_ms=show_ms, time_delim=time_delim, ms_delim=ms_delim, ms_digits=ms_digits)
        return f'{date_part}{date_time_delim}{time_part}'

    def extract_date_from_string(self, string):
        pattern = r'\D((?:19|20)\d{2})(\d{2})(\d{2})?\D|\D((?:19|20)\d{2})H([12])\D?'
        match = re.search(pattern, string)
        if match:
            if match.group(4) and match.group(5):
                year = match.group(4)
                half = match.group(5)
                month = '01' if half == '1' else '07'
                day = '01'
            else:
                year, month, day = match.groups()[:3]
                if day is None:
                    day = '01'
            try:
                date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                return date_obj
            except ValueError:
                return None
        return None

    def get_datetime_difference(self, start_time, end_time, output_format='seconds'):
        if isinstance(start_time, datetime) and isinstance(end_time, datetime):
            diff = end_time - start_time
            if diff.total_seconds() < 0:
                return None
            if output_format == 'seconds':
                return diff.total_seconds()
            elif output_format == 'minutes':
                return diff.total_seconds() / 60
            elif output_format == 'hours':
                return diff.total_seconds() / 3600
            elif output_format == 'days':
                return diff.total_seconds() / (24 * 3600)
        return None

    class IntervalTimer:
        def __init__(self, interval_sec, eco_mode=True):
            self.interval_sec = interval_sec
            self.eco_mode = eco_mode
            self.time_start = time.time()
            self.idx = 0

        def wait(self):
            self.idx += 1
            target_time = self.time_start + (self.idx * self.interval_sec)
            while time.time() < target_time:
                if self.eco_mode:
                    sleep_time = target_time - time.time()
                    if sleep_time > 0.01:
                        time.sleep(min(sleep_time * 0.9, 0.01))
                else:
                    pass

        def reset(self):
            self.time_start = time.time()
            self.idx = 0

    class ThreadedTimer(threading.Thread):
        def __init__(self, timeout_sec, repeat=False, callback=None, auto_start=True, auto_clear_expired=True):
            super().__init__(daemon=True)
            self.timeout_sec = timeout_sec
            self.repeat = repeat
            self.callback = callback
            self._expired = threading.Event()
            self._stop_event = threading.Event()
            self._reset_event = threading.Event()
            self._running = False
            self._fire_count = 0
            if auto_start:
                self.start()
            self._auto_clear_expired = auto_clear_expired

        def run(self):
            self._running = True
            while not self._stop_event.is_set():
                if self._stop_event.wait(self.timeout_sec):
                    break

                if self._reset_event.is_set():
                    self._reset_event.clear()
                    continue

                if not self._stop_event.is_set():
                    self._fire_count += 1
                    self._expired.set()

                    if self.callback:
                        try:
                            self.callback()
                        except Exception as e:
                            print(f"Timer callback error: {e}")

                    if not self.repeat:
                        break

            self._running = False

        def start(self):
            if not self._running and not self.is_alive():
                super().start()

        def stop(self):
            self._stop_event.set()
            if self.is_alive():
                self.join(timeout=1.0)

        def reset(self):
            self._expired.clear()
            self._reset_event.set()
            self._fire_count = 0

        def is_expired(self):
            expired = self._expired.is_set()
            if expired and self._auto_clear_expired:
                self._expired.clear()
            return expired

        def clear_expired(self):
            self._expired.clear()

        def is_running(self):
            return self._running

        def fire_count(self):
            return self._fire_count

        def time_remaining(self):
            if not self._running or self.is_expired():
                return 0
            return max(0, self.timeout_sec)

    def seconds_to_time(self, seconds):
        hr = seconds // 3600
        min = (seconds % 3600) // 60
        sec = seconds % 60
        return hr, min, sec
