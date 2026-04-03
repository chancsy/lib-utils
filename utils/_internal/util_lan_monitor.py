import socket
import threading
import time


class LanMonitorClient:
    DEFAULT_PORT = 47777
    _MSG_PING = 'LMON_PING'
    _MSG_PONG = 'LMON_PONG'
    _MSG_HB = 'LMON_HB'

    def __init__(self, port=None, heartbeat_interval=0, status_callback=None):
        self.port = port or self.DEFAULT_PORT
        self.heartbeat_interval = heartbeat_interval
        self.status_callback = status_callback
        self.hostname = socket.gethostname()
        self._stop = threading.Event()
        self._threads = []

    def _get_status(self):
        if callable(self.status_callback):
            try:
                return str(self.status_callback())
            except Exception:
                return 'error'
        return 'online'

    def _listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(('', self.port))
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = data.decode(errors='replace').strip()
                    if msg.startswith(self._MSG_PING):
                        reply = f'{self._MSG_PONG}:{self.hostname}:{self._get_status()}'.encode()
                        sock.sendto(reply, ('<broadcast>', self.port))
                except socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            sock.close()

    def _heartbeat_loop(self):
        if not self.heartbeat_interval:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while not self._stop.is_set():
                try:
                    msg = f'{self._MSG_HB}:{self.hostname}:{self._get_status()}'.encode()
                    sock.sendto(msg, ('<broadcast>', self.port))
                except OSError:
                    break
                self._stop.wait(self.heartbeat_interval)
        finally:
            sock.close()

    def start(self):
        self._stop.clear()
        self._threads.clear()
        for target in (self._listen_loop, self._heartbeat_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        print(f'[LanMonitorClient] {self.hostname} listening on UDP port {self.port}')

    def stop(self):
        self._stop.set()
        print(f'[LanMonitorClient] {self.hostname} stopped.')


class LanMonitorServer:
    DEFAULT_PORT = 47777
    _MSG_PING = 'LMON_PING'
    _MSG_PONG = 'LMON_PONG'
    _MSG_HB = 'LMON_HB'

    def __init__(self, port=None, ping_interval=10, offline_timeout=60, watch=None):
        self.port = port or self.DEFAULT_PORT
        self.ping_interval = ping_interval
        self.offline_timeout = offline_timeout
        self.watch = {h.upper() for h in watch} if watch else None
        self.hostname = socket.gethostname()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._clients = {}
        self._threads = []

    def _listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(('', self.port))
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = data.decode(errors='replace').strip()
                    parts = msg.split(':', 2)
                    if len(parts) >= 2 and parts[0] in (self._MSG_PONG, self._MSG_HB):
                        hostname = parts[1]
                        status = parts[2] if len(parts) > 2 else 'online'
                        if hostname == self.hostname:
                            continue
                        if self.watch and hostname.upper() not in self.watch:
                            continue
                        with self._lock:
                            self._clients[hostname] = {
                                'status': status,
                                'last_seen': time.time(),
                                'ip': addr[0],
                            }
                except socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            sock.close()

    def _ping_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while not self._stop.is_set():
                try:
                    msg = f'{self._MSG_PING}:{self.hostname}'.encode()
                    sock.sendto(msg, ('<broadcast>', self.port))
                except OSError:
                    break
                self._stop.wait(self.ping_interval)
        finally:
            sock.close()

    def start(self):
        self._stop.clear()
        self._threads.clear()
        for target in (self._listen_loop, self._ping_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        print(f'[LanMonitorServer] {self.hostname} pinging every {self.ping_interval}s on UDP port {self.port}')

    def stop(self):
        self._stop.set()
        print('[LanMonitorServer] stopped.')

    def get_status(self):
        now = time.time()
        with self._lock:
            result = {}
            if self.watch:
                for h in self.watch:
                    result[h] = {'status': 'offline', 'last_seen': None,
                                 'ip': None, 'is_online': False, 'seconds_since_seen': None}
            for hostname, info in self._clients.items():
                age = now - info['last_seen']
                is_online = age < self.offline_timeout
                result[hostname] = {
                    'status': info['status'] if is_online else 'offline',
                    'last_seen': info['last_seen'],
                    'ip': info['ip'],
                    'is_online': is_online,
                    'seconds_since_seen': round(age, 1),
                }
        return result

    def print_status(self):
        if not self._threads or not any(t.is_alive() for t in self._threads):
            print('[LanMonitorServer] WARNING: server is not running. Call start() first.')
        status = self.get_status()
        if not status:
            print('No clients discovered yet.')
            return
        print(f"  {'Hostname':<20} {'Status':<12} {'IP':<16} {'Seen (s ago)'}")
        print('  ' + '-' * 62)
        for hostname, info in sorted(status.items()):
            mark = '+' if info['is_online'] else '-'
            ip_str = info['ip'] or '-'
            age_str = f"{info['seconds_since_seen']:.1f}s" if info['seconds_since_seen'] is not None else 'never'
            print(f"  [{mark}] {hostname:<17} {info['status']:<12} {ip_str:<16} {age_str}")
