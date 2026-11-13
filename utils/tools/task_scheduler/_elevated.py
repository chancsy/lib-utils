"""task_scheduler calls in an elevated helper process (utils.standalone.elevate_utils): a UAC prompt on demand, so
Jupyter / Python itself never needs to run as administrator. One prompt covers a batch of calls.

The helper's command line is a plain description (shown under the UAC prompt's "Show more details", e.g.
"Disable \\Tests\\a, \\Tests\\b"), this module's name and the request as readable JSON; it never holds a password:
for logon 'password' the helper asks for it in its own Windows password dialog. Only the calls in OPS are accepted,
and they run with elevate=False.
"""
from __future__ import annotations

OPS = ('register_task', 'set_enabled', 'run_task', 'stop_task', 'delete_task', 'delete_folder')
TIMEOUT_S = 600            # the user may take a while with the UAC prompt and the password dialog


def run_op(op: str, kwargs: dict) -> None:
    """One call, in the elevated helper."""
    from . import _winsched as ws
    if op == 'register_task':
        kwargs['triggers'] = [ws._trigger_from_dict(d) for d in kwargs.get('triggers', [])]
    getattr(ws, op)(**kwargs, elevate=False)


def call(requests: list[tuple[str, dict]], description: str, timeout_s: float = TIMEOUT_S, _verb: str = 'runas') -> None:
    """Run [(op, kwargs), ...] (task_scheduler.<op>(**kwargs)) in one elevated helper; TaskSchedulerError if the UAC
    prompt is declined or a call fails. _verb='open' runs the helper without elevation (tests of the plumbing only)."""
    from ...standalone import elevate_utils as _elevate
    from ._winsched import _HINTS, TaskSchedulerError, _message
    try:
        _elevate.call(__name__, requests, description, timeout_s, _verb)
    except _elevate.ElevationError as e:
        if e.code in (_elevate.CANCELLED, _elevate.UNEXPECTED, _elevate.TIMEOUT) or e.code is None:
            raise TaskSchedulerError(str(e).replace(' - check later', ' - Reload later to see'),
                                     None if e.code == _elevate.TIMEOUT else e.code) from None
        code = e.code
        text = _HINTS.get(code) or _message(code) or 'failed'
        more = ' (the ones before it were done)' if len(requests) > 1 else ''
        raise TaskSchedulerError(f'{description} (elevated): {text} (0x{code:08X}){more}', code) from None
