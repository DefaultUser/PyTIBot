# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017>  <Sebastian Schmidt>

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


class STDIOInterface(LineOnlyReceiver, object):
    delimiter = '\n'

    def __init__(self, bot):
        super(STDIOInterface, self).__init__()
        self.bot = bot

    def lineReceived(self, line):
        if not line:
            return
        # type(line) is bytes - convert to str for python3
        line = str(line)
        try:
            command, data = line.split(None, 1)
        except ValueError:
            command = line
            data = None
        method = getattr(self, "irc_{}".format(command), None)
        if method:
            try:
                method(data)
            except Exception as e:
                self.sendLine(formatting.ansi_colored("Error: {}".format(e),
                                                      fg="red"))
        else:
            self.sendLine(formatting.ansi_colored("Error: no such command "
                                                  "{}.".format(command),
                                                  fg="red"))

    def irc_help(self, command=None):
        """Show help
        Usage: help [command]"""
        if command:
            method = getattr(self, "irc_{}".format(command), None)
            if method:
                self.sendLine(formatting.ansi_colored(method.__doc__,
                              fg="cyan"))
            else:
                self.sendLine(formatting.ansi_colored(
                    "No such command {}".format(command), fg="yellow"))
        else:
            self.sendLine(formatting.ansi_colored("Available commands: ",
                                                  fg="blue") +
                          ", ".join([member[4:] for member in dir(self)
                                     if member.startswith("irc_")]))

    def irc_action(self, data):
        """Send an action to an IRC channel
        Usage: action <channel> <action>"""
        if not data:
            raise ValueError("No channel and action given")
        channel, action = data.split(None, 1)
        self.bot.describe(channel, action)

    def irc_msg(self, data):
        """Send a message to an IRC channel or user
        Usage: msg <channel> <message>"""
        if not data:
            raise ValueError("No channel and message given")
        channel, message = data.split(None, 1)
        self.bot.msg(channel, formatting.from_human_readable(message))

    def irc_notice(self, data):
        """Send a notice to an IRC channel or user
        Usage: notice <channel> <message>"""
        if not data:
            raise ValueError("No channel and message given")
        channel, message = data.split(None, 1)
        self.bot.notice(channel, formatting.from_human_readable(message))

    def irc_join(self, channels):
        """Try to join one or more IRC channels
        Usage: join <channels>"""
        for channel in channels.split():
            self.bot.join(channel)

    def irc_leave(self, channels):
        """Leave one or more IRC channels
        Usage: leave <channels>"""
        for channel in channels.split():
            self.bot.leave(channel)

    def irc_quit(self, message):
        """Quit the bot
        Usage: quit [message]"""
        self.bot.quit(message)
