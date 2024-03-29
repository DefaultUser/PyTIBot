# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2021>  <Sebastian Schmidt>

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

from twisted.internet import protocol, reactor
from twisted.logger import Logger
from zope.interface import implementer


from backends.interfaces import IBotProvider
from backends.irc_bot import IRCBot


@implementer(IBotProvider)
class IRCFactory(protocol.ClientFactory):
    """A factory for the IRCBot"""
    MAX_ATTEMPTS = 5
    RECONNECT_DELAY = 60
    log = Logger()

    def __init__(self, config):
        self.config = config
        self.autoreconnect = True
        self._bot = None
        self.connection_attempts = 0

    def buildProtocol(self, addr):
        bot = IRCBot(self.config)
        bot.factory = self
        self._bot = bot
        self.connection_attempts = 0
        return bot

    @property
    def bot(self):
        return self._bot

    def get_bot(self):
        return self.bot

    def clientConnectionLost(self, connector, reason):
        """Triggered on"""
        self.log.error("connection lost ({reason})", reason=reason)
        if self.autoreconnect:
            connector.connect()
        else:
            reactor.stop()

    def clientConnectionFailed(self, connector, reason):
        self.log.error("connection failed ({reason})", reason=reason)
        if self.connection_attempts < IRCFactory.MAX_ATTEMPTS:
            reactor.callLater(IRCFactory.RECONNECT_DELAY,
                              connector.connect)
            self.connection_attempts += 1
        else:
            self.log.critical("Connection can't be established - Shutting down")
            reactor.stop()
