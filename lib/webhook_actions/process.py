# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018-2024>  <Sebastian Schmidt>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from collections import defaultdict, deque
import json
import os
import re

from twisted.logger import Logger
from twisted.internet import defer
from twisted.python.failure import Failure

from util import async_process


log = Logger()

running_processes = {}
process_queue = defaultdict(deque)
_data_accessor_pattern = re.compile(r"\${data(?:\((\w+(?:\.\w+)*)\))?}")


def _run_process(action_id, action, payloaddata):
    """
    Actually run the process
    """
    def replacer(match):
        accessor = match.group(1)
        if accessor is None:
            return json.dumps(payloaddata)
        temp = payloaddata
        for frag in accessor.split("."):
            if isinstance(temp, list) and frag.isnumeric():
                frag = int(frag)
            try:
                temp = temp[frag]
            except KeyError:
                raise KeyError(f"Webhook payload doesn't contain {accessor}")
        return json.dumps(temp)

    cmd = action.get("command", None)
    if not cmd:
        raise ValueError("No command for action {} given".format(action_id))
    path = action.get("path", None)
    args = action.get("args", []).copy() # Copy to avoid replacing "${data}"
    # make sure args are strings and replace "${data}" and
    # and "${data(<accessor path>)}" with payload data
    for i, arg in enumerate(args):
        if not isinstance(arg, str):
            args[i] = str(arg)
        else:
            args[i] = _data_accessor_pattern.sub(replacer, arg)
    return async_process.start_subprocess(cmd, args, path, log_name=action_id)


def _on_process_finished(success, rungroup, d):
    """
    Starts Call-/Errback(s) and tries to run the next process
    """
    running_processes.pop(rungroup)
    if isinstance(success, Failure):
        d.errback(success)
    else:
        d.callback(True)
    _maybe_run_next_process(rungroup)


def _maybe_run_next_process(rungroup):
    """
    Runs the next queued process for the given rungroup if no process of
    that group is already running
    """
    if rungroup in running_processes:
        return
    if len(process_queue[rungroup]) == 0:
        return
    action_id, action, payloaddata, d = process_queue[rungroup].pop()
    try:
        process = _run_process(action_id, action, payloaddata)
    except Exception as e:
        log.warn("Error starting process {action_id}: {error}",
                 action_id=action_id, error=e)
        d.errback(e)
        _maybe_run_next_process(rungroup)
    else:
        running_processes[rungroup] = process
        process.proto.finished.addBoth(_on_process_finished, rungroup, d)


def _queue_process(action_id, action, payloaddata, runsettings):
    """
    Add a new process to the process queue
    """
    d = defer.Deferred()
    rungroup = action.get("rungroup", "default")
    if runsettings.get("clear_previous", False) and rungroup in process_queue:
        log.debug("Clearing process_buffer for rungroup {group}",
                  group=rungroup)
        process_queue[rungroup].clear()
    if runsettings.get("stop_running", False) and rungroup in running_processes:
        if os.name == "posix":
            log.debug("Sending KILL signal to current process "
                      "of rungroup {group}", group=rungroup)
            running_processes[rungroup].signalProcess("KILL")
        else:
            log.warn("Stopping processes is only supported on posix OSs, "
                     "Not sending KILL signal")
    process_queue[rungroup].append((action_id, action, payloaddata, d))
    _maybe_run_next_process(rungroup)
    return d


def process(action_id, data, action, runsettings):
    """
    Run a process action.
    Only one process per rungroup at a time (queues additional processes)
    """
    return _queue_process(action_id, action, data, runsettings)
