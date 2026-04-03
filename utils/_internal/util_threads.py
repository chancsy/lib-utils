import threading


class UtilityThreadMixin:
    class StoppableThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._stop_event = threading.Event()

        def stop(self):
            self._stop_event.set()

        def stop_flag(self):
            return self._stop_event.is_set()
