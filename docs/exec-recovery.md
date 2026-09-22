# Command submission evidence

`CommandResult` and `TmuxStartResult` include an optional provider `code` and
`command_dispatched` evidence. `False` is used only for explicit rejection before
the user command was dispatched; `True` denotes provider acceptance; `None`
denotes uncertainty. A timeout while submitting does not prove rejection. A lost
output response retains the accepted request identity and is not permission to
resubmit a command.

Both synchronous and asynchronous exec paths preserve this distinction. Normal
exec sends the command in its API request, so a missing output URI follows
acceptance. Interactive exec has not sent the user command until the stdin step;
a missing interactive URI therefore proves no user-command dispatch. Exceptions
after acceptance are conservative unknown/accepted evidence. Command API calls
disable SDK automatic retries and use the remaining configured timeout for
subsequent output observation.

Long tmux command scripts are not removed following an uncertain start reply.
The original command owns its completion cleanup; immediate cleanup is allowed
only after an explicit non-dispatch refusal. Failed tmux startup forwards the
underlying evidence to the caller, which owns retry policy and durable session
recovery.

`tests/test_exec_evidence.py` covers both transports and sync/async clients with
injected pre-acceptance errors, post-acceptance reply loss, missing URIs, deadline
consumption and long-script retention. No live cloud request is needed.
