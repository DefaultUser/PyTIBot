# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2018>  <Sebastian Schmidt>

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

from abc import ABCMeta, abstractmethod


class ChannelWatcher(object):
    """
    Abstract base class for watching activity on a channel
    """
    __metaclass__ = ABCMeta

    def __init__(self, bot, channel, config):
        self.bot = bot
        self.channel = channel

    @abstractmethod
    def topic(self, user, topic):
        pass

    @abstractmethod
    def nick(self, oldnick, newnick):
        pass

    @abstractmethod
    def join(self, user):
        pass

    @abstractmethod
    def part(self, user):
        pass

    @abstractmethod
    def quit(self, user, quitMessage):
        pass

    @abstractmethod
    def kick(self, kickee, kicker, message):
        pass

    @abstractmethod
    def notice(self, user, message):
        pass

    @abstractmethod
    def action(self, user, data):
        pass

    @abstractmethod
    def msg(self, user, message):
        pass

    @abstractmethod
    def connectionLost(self, reason):
        pass
