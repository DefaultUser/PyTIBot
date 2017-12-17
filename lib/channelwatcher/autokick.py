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
from collections import deque, defaultdict
from twisted.words.protocols import irc

from . import abstract


class Autokick(abstract.ChannelWatcher):
    def __init__(self, bot, channel, config):
        super(Autokick, self).__init__(bot, channel, config)
        self.user_blacklist = config["user_blacklist"]
        self.msg_blacklist = config["msg_blacklist"]
        buffer_len = config.get("buffer_length", 5)
        # number of repeating messages until a user is kicked
        self.repeat_count = config.get("repeat_count", 3)
        self.msg_buffer = defaultdict(lambda: deque([], buffer_len))
        # maximum number of highlights in one message
        self.max_highlights = config.get("max_highlights", 5)

    def remove_user_from_msgbuffer(self, user):
        self.msg_buffer.pop(user, None)

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
        self.remove_user_from_msgbuffer(user)

    def quit(self, user, quitMessage):
        self.remove_user_from_msgbuffer(user)

    def kick(self, kickee, kicker, message):
        self.remove_user_from_msgbuffer(kickee)

    def check_msg(self, user, message):
        if user == self.bot.nickname:
            return False
        message = irc.stripFormatting(message)
        return (self.check_msg_content(message) or
                self.check_spam(user, message) or
                self.check_mass_highlight(message))

    def check_msg_content(self, message):
        """Check if a message contains blacklisted words"""
        for bl_msg in self.msg_blacklist:
            try:
                if re.search(re.compile(bl_msg, re.IGNORECASE), message):
                    return True
            except re.error:
                if bl_msg.lower() in message.lower():
                    return True
        return False

    def check_spam(self, user, message):
        """Check if message is just repeated spam"""
        msg = message.lower()
        # TODO: fuzzy string comparison
        self.msg_buffer[user].append(msg)
        if self.msg_buffer[user].count(msg) == self.repeat_count:
            return True
        return False

    def check_mass_highlight(self, message):
        """Check if a message highlights too many users"""
        if self.max_highlights <= 1:
            return False
        message = message.lower()
        count = 0
        for user in self.bot.userlist[self.channel]:
            if user.lower() in message:
                count += 1
            if count > self.max_highlights:
                return True
        return False

    def notice(self, user, message):
        if self.check_msg(user, message):
            self.bot.kick(self.channel, user)

    def action(self, user, data):
        pass

    def msg(self, user, message):
        if self.check_msg(user, message):
            self.bot.kick(self.channel, user)

    def error(self, message):
        pass
