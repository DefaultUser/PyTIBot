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
from twisted.internet.defer import Deferred, ensureDeferred
from twisted.internet import reactor
from twisted.words.protocols import irc
from nio import AsyncClient
from zope.interface import implementer

from backends.interfaces import IBot

from util.aio_compat import deferred_to_future, future_to_deferred
from util import formatting


@implementer(IBot)
class MatrixBot:
    def __init__(self, config):
        self.config = config
        self.client = AsyncClient(config["Connection"]["server"],
                                  config["Connection"]["username"],
                                  device_id=config["Connection"].get("deviceID", None))

    def reload(self):
        self.config.load()
        # TODO: setup aliases, triggers, channelwatchers

    async def start(self):
        await future_to_deferred(self.client.login(self.config["Connection"]["password"]))
        await future_to_deferred(self.client.sync_forever(timeout=30000))
        return Deferred()

    def quit(self, ignored=None):
        self.stop()
        reactor.stop()

    def stop(self):
        future_to_deferred(self.client.close())

    @staticmethod
    def formatted_message_content(message):
        # FIXME: for now, convert IRC formatting to html
        # formatting is currently designed with only IRC in mind
        unformatted = irc.stripFormatting(message)
        if unformatted == message:
            return {"body": message}
        return {"body": unformatted, "format": "org.matrix.custom.html",
                "formatted_body": formatting.to_matrix(message).replace("\n", "<br/>")}

    def msg(self, target, message, length=None):
        content = {"msgtype": "m.text", **MatrixBot.formatted_message_content(message)}
        future_to_deferred(self.client.room_send(room_id=target,
                                             message_type="m.room.message",
                                             content=content))

    def notice(self, target, message, length=None):
        content = {"msgtype": "m.notice", **MatrixBot.formatted_message_content(message)}
        self.client.room_send(room_id=target,
                              message_type="m.room.message",
                              content=content)

    def join(self, channel):
        self.client.join(channel)

    def leave(self, channel):
        self.client.room_leave(channel)

    def kick(self, channel, user, reason=""):
        self.client.room_kick(channel, user, reason)

    def ban(self, channel, user, reason=""):
        self.client.room_ban(channel, user, reason)

