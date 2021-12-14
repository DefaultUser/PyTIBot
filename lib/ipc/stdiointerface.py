# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2021>  <Sebastian Schmidt>

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

from twisted.protocols.basic import LineOnlyReceiver

from util import formatting
from util.formatting import ANSIColors
from util.misc import str_to_bytes, bytes_to_str


class STDIOInterface(LineOnlyReceiver, object):
    delimiter = b'\n'

    def __init__(self, bot):
        super(STDIOInterface, self).__init__()
        self.bot = bot

    def sendLine(self, line):
        # Python3 compatibility: ensure that line is a bytes string
        super(STDIOInterface, self).sendLine(str_to_bytes(line))

    def lineReceived(self, line):
        if not line:
            return
        # type(line) is bytes -> convert to str for python3
        line = bytes_to_str(line)
        try:
            command, data = line.split(None, 1)
        except ValueError:
            command = line
            data = None
        method = getattr(self, "cmd_{}".format(command), None)
        if method:
            try:
                method(data)
            except Exception as e:
                self.sendLine(formatting.ansi_colored("Error: {}".format(e),
                                                      fg=ANSIColors.red))
        else:
            self.sendLine(formatting.ansi_colored("Error: no such command "
                                                  "{}.".format(command),
                                                  fg=ANSIColors.red))

    def cmd_help(self, command=None):
        """Show help
        Usage: help [command]"""
        if command:
            method = getattr(self, "cmd_{}".format(command), None)
            if method:
                self.sendLine(formatting.ansi_colored(method.__doc__,
                                                      fg=ANSIColors.cyan))
            else:
                self.sendLine(formatting.ansi_colored(
                    "No such command {}".format(command),
                    fg=ANSIColors.yellow))
        else:
            self.sendLine(formatting.ansi_colored("Available commands: ",
                                                  fg=ANSIColors.blue) +
                          ", ".join([member[4:] for member in dir(self)
                                     if member.startswith("cmd_")]))

    def cmd_action(self, data):
        """Send an action to a channel
        Usage: action <channel> <action>"""
        if not data:
            raise ValueError("No channel and action given")
        channel, action = data.split(None, 1)
        self.bot.describe(channel, action)

    def cmd_msg(self, data):
        """Send a message to a channel or user
        Usage: msg <channel> <message>"""
        if not data:
            raise ValueError("No channel and message given")
        channel, message = data.split(None, 1)
        self.bot.msg(channel, formatting.from_human_readable(message))

    def cmd_notice(self, data):
        """Send a notice to a channel or user
        Usage: notice <channel> <message>"""
        if not data:
            raise ValueError("No channel and message given")
        channel, message = data.split(None, 1)
        self.bot.notice(channel, formatting.from_human_readable(message))

    def cmd_join(self, channels):
        """Try to join one or more channels
        Usage: join <channels>"""
        for channel in channels.split():
            self.bot.join(channel)

    def cmd_leave(self, channels):
        """Leave one or more channels
        Usage: leave <channels>"""
        for channel in channels.split():
            self.bot.leave(channel)

    def cmd_quit(self, message):
        """Quit the bot
        Usage: quit [message]"""
        self.bot.quit(message)

    def cmd_kick(self, data):
        """Attempt to kick a user from a channel
        Usage: kick <channel> <user>
        """
        channel, user = data.split(None, 1)
        self.bot.kick(channel, user)

    def cmd_ban(self, data):
        """Attempt to ban a user from a channel
        Usage: ban <channel> <user>
        """
        channel, user = data.split(None, 1)
        self.bot.ban(channel, user)
