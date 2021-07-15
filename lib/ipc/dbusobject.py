# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2021>  <Sebastian Schmidt>

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

from twisted.internet import reactor, defer
from twisted.logger import Logger

from txdbus           import client, objects, error
from txdbus.interface import DBusInterface, Method

from util import formatting


log = Logger()


class PytibotDBusObject(objects.DBusObject):
    dbusInterfaces = [DBusInterface("org.PyTIBot.PyTIBotInterface",
                                    Method("action", arguments="ss"),
                                    Method("message", arguments="ss"),
                                    Method("notice", arguments="ss"),
                                    Method("kick", arguments="ss"),
                                    Method("ban", arguments="ss"),
                                    Method("join", arguments="as"),
                                    Method("leave", arguments="as"),
                                    Method("quit"))]


    def __init__(self, objectPath, botprovider):
        super().__init__(objectPath)
        self.botprovider = botprovider

    def dbus_action(self, channel, action):
        """Send an action to a channel
        Usage: string:'<channel>' string:'<action>'"""
        if self.botprovider.bot:
            self.botprovider.bot.describe(channel, action)

    def dbus_message(self, channel, message):
        """Send a message to a channel
        Usage: string:'<channel>' string:'<message>'"""
        if self.botprovider.bot:
            self.botprovider.bot.msg(channel, formatting.from_human_readable(message))

    def dbus_notice(self, channel, message):
        """Send a notice to a channel
        Usage: string:'<channel>' string:'<message>'"""
        if self.botprovider.bot:
            self.botprovider.bot.notice(channel, formatting.from_human_readable(message))

    def dbus_kick(self, channel, user):
        """Attempt to kick an user from a channel
        Usage: string:'<channel>' string:'<user>'"""
        if self.botprovider.bot:
            self.botprovider.bot.kick(channel, user)

    def dbus_ban(self, channel, user):
        """Attempt to ban an user from a channel
        Usage: string:'<channel>' string:'<user>'"""
        if self.botprovider.bot:
            self.botprovider.bot.kick(channel, user)

    def dbus_join(self, channels):
        """Join the given channels"""
        if self.botprovider.bot:
            for channel in channels:
                self.botprovider.bot.join(channel)

    def dbus_leave(self, channels):
        """Leave the given channels"""
        if self.botprovider.bot:
            for channel in channels:
                self.botprovider.bot.leave(channel)

    def dbus_quit(self):
        """Quit the bot"""
        if self.botprovider.bot:
            self.botprovider.bot.quit()

@defer.inlineCallbacks
def create_and_export(botprovider):
    try:
        connection = yield client.connect(reactor)
        connection.exportObject(PytibotDBusObject("/PyTIBot", botprovider))
        yield connection.requestBusName("org.PyTIBot")
        return connection
    except error.DBusException as e:
        log.error("Couldn't export DBus object: {e}", e=e)

