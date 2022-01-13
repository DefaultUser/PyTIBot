# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018-2022>  <Sebastian Schmidt>

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

import os
import io
import shutil

from twisted.internet import defer, reactor
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone
from twisted.logger import Logger, textFileLogObserver

from util import filesystem as fs
from util.misc import bytes_to_str


def _backup_logs(log_name, maxbackups):
    """
    Rotate logs
    """
    for i in range(maxbackups - 1, 0, -1):
        if os.path.isfile(log_name + str(i)):
            shutil.move(log_name + str(i), log_name + str(i + 1))
    if os.path.isfile(log_name):
        shutil.move(log_name, log_name + "1")


class LoggingProcessProtocol(ProcessProtocol, object):
    """
    A ProcessProtocol that logs all output to a file
    """
    def __init__(self, commandname, maxbackups=3):
        log_name = commandname + ".log"
        log_dir = os.path.join(fs.adirs.user_log_dir, "processes")
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        log_name = os.path.join(log_dir, log_name)
        _backup_logs(log_name, maxbackups)
        self.log = Logger(observer=textFileLogObserver(io.open(log_name, "w")),
                          namespace="")
        super(LoggingProcessProtocol, self).__init__()

    def connectionMade(self):
        self.finished = defer.Deferred()

    def outReceived(self, data):
        self.log.info("{data}", data=bytes_to_str(data.strip()))

    def errReceived(self, data):
        self.log.error("{data}", data=bytes_to_str(data.strip()))

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            self.finished.callback(True)
            self.log.info("Process finished without error")
        else:
            self.finished.errback(reason)
            self.log.error("Process ended with error: {reason!r}",
                           reason=reason)


def start_subprocess(cmd, args=(), path=None, env=None, usePTY=True, log_name=None):
    """
    Start a subprocess and log its output to a file in the log directory
    """
    args = list(args)
    args.insert(0, cmd)
    if log_name is None:
        log_name = os.path.basename(cmd)
    proto = LoggingProcessProtocol(log_name)
    return reactor.spawnProcess(proto, cmd, args=args, env=env, path=path,
                                usePTY=usePTY)
