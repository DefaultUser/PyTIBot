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

import re
import logging

from . import abstract


class Autokick(abstract.ChannelWatcher):
    def __init__(self, bot, channel, config):
        super(Autokick, self).__init__(bot, channel, config)
        self.user_blacklist = config["user_blacklist"]
        self.msg_blacklist = config["msg_blacklist"]

    def topic(self, user, topic):
        pass

    def check_nick(self, nick):
        for bl_nick in self.user_blacklist:
            try:
                if re.search(re.compile(bl_nick, re.IGNORECASE), nick):
                    return True
            except re.error:
                if bl_nick.lower() == nick.lower():
                    return True
        return False

    def nick(self, oldnick, newnick):
        if self.check_nick(newnick):
            self.bot.kick(self.channel, newnick)

    def join(self, user):
        if self.check_nick(user):
            self.bot.kick(self.channel, user)

    def part(self, user):
        pass

    def quit(self, user, quitMessage):
        pass

    def kick(self, kickee, kicker, message):
        pass

    def check_msg(self, message):
        for bl_msg in self.msg_blacklist:
            try:
                if re.search(re.compile(bl_msg, re.IGNORECASE), message):
                    return True
            except re.error:
                if bl_msg.lower() in message.lower():
                    return True
        return False

    def notice(self, user, message):
        if self.check_msg(message):
            self.bot.kick(self.channel, user)

    def action(self, user, data):
        pass

    def msg(self, user, message):
        if self.check_msg(message):
            self.bot.kick(self.channel, user)

    def error(self, message):
        pass
