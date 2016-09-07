# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2016>  <Sebastian Schmidt>

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
import logging
from pytibot import PyTIBot


class PyTIBotFactory(protocol.ClientFactory):
    """A factory for PyTIBot"""
    autoreconnect = True
    bot = None

    def __init__(self, config_manager):
        self.cm = config_manager

    def buildProtocol(self, addr):
        bot = PyTIBot(self.cm)
        bot.factory = self
        self.bot = bot
        return bot

    def get_bot(self):
        return self.bot

    def clientConnectionLost(self, connector, reason):
        """Triggered on"""
        logging.error("connection lost (%s)" % reason)
        for channel in self.bot.log_channels:
            logger = logging.getLogger(channel.lower())
            logger.error("Connection lost")
        if self.autoreconnect:
            connector.connect()
        else:
            reactor.stop()

    def clientConnectionFailed(self, connector, reason):
        logging.error("connection failed (%s)" % reason)
        for channel in self.bot.log_channels:
            logger = logging.getLogger(channel.lower())
            logger.error("Connection failed")
        reactor.stop()

