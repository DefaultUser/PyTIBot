# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2018>  <Sebastian Schmidt>

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
from pytibot import PyTIBot


class PyTIBotFactory(protocol.ClientFactory):
    """A factory for PyTIBot"""
    MAX_ATTEMPTS = 5
    RECONNECT_DELAY = 60
    log = Logger()

    def __init__(self, config):
        self.config = config
        self.autoreconnect = True
        self.bot = None
        self.connection_attempts = 0

    def buildProtocol(self, addr):
        bot = PyTIBot(self.config)
        bot.factory = self
        self.bot = bot
        self.connection_attempts = 0
        return bot

    def get_bot(self):
        return self.bot

    def clientConnectionLost(self, connector, reason):
        """Triggered on"""
        self.log.error("connection lost ({reason})", reason=reason)
        if self.bot:
            self.bot.stop_webhook_server()
        if self.autoreconnect:
            connector.connect()
        else:
            reactor.stop()

    def clientConnectionFailed(self, connector, reason):
        self.log.error("connection failed ({reason})", reason=reason)
        if self.bot:
            self.bot.stop_webhook_server()
        if self.connection_attempts < PyTIBotFactory.MAX_ATTEMPTS:
            reactor.callLater(PyTIBotFactory.RECONNECT_DELAY,
                              connector.connect)
            self.connection_attempts += 1
        else:
            self.log.critical("Connection can't be established - Shutting down")
            reactor.stop()
