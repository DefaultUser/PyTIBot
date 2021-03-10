# -*- coding: utf-8 -*-

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

import re
from collections import deque, defaultdict
from string import Template
from twisted.logger import Logger
from twisted.words.protocols import irc
from twisted.internet import defer

from . import abstract


class Autokick(abstract.ChannelWatcher):
    logger = Logger()

    def __init__(self, bot, channel, config):
        super(Autokick, self).__init__(bot, channel, config)
        self.user_blacklist = config.get("user_blacklist", [])
        self.user_whitelist = [user.lower() for user in
                               config.get("user_whitelist", [])]
        self.msg_blacklist = config.get("msg_blacklist", [])
        self.msg_whitelist = []
        for pattern in config.get("msg_whitelist", []):
            try:
                self.msg_whitelist.append(re.compile(pattern, re.IGNORECASE))
            except Exception as e:
                Autokick.logger.warn("Can't add pattern '{pattern}' to "
                                     "Autokick message whitelist: {error}",
                                     pattern=pattern, error=e)
        buffer_len = config.get("buffer_length", 5)
        # number of repeating messages until a user is kicked
        self.repeat_count = config.get("repeat_count", 3)
        self.msg_buffer = defaultdict(lambda: deque([], buffer_len))
        # maximum number of highlights in one message
        self.max_highlights = config.get("max_highlights", 5)

        # ban
        self.ban = config.get("ban", False)
        self.ban_service = config.get("ban_service", None)
        self.ban_command = Template(config.get("ban_command", ""))

    def remove_user_from_msgbuffer(self, user):
        self.msg_buffer.pop(user.lower(), None)

    @defer.inlineCallbacks
    def kick_or_ban(self, user):
        if self.ban and self.ban_service and self.ban_command.template:
            userinfo = yield self.bot.user_info(user)
            try:
                bancmd = self.ban_command.substitute(NICK=userinfo.nick,
                                                     USER=userinfo.user,
                                                     HOST=userinfo.host,
                                                     CHANNEL=self.channel)
                self.bot.msg(self.ban_service, bancmd)
            except Exception as e:
                Autokick.logger.warn("Invalid ban command, kicking instead")
                self.bot.kick(self.channel, user)
        else:
            self.bot.kick(self.channel, user)

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
            self.kick_or_ban(newnick)

    def join(self, user):
        if self.check_nick(user):
            self.kick_or_ban(user)

    def part(self, user):
        self.remove_user_from_msgbuffer(user)

    def quit(self, user, quitMessage):
        self.remove_user_from_msgbuffer(user)

    def kick(self, kickee, kicker, message):
        self.remove_user_from_msgbuffer(kickee)

    def check_msg(self, user, message):
        user = user.lower()
        if user == self.bot.nickname.lower() or user in self.user_whitelist:
            return False
        message = irc.stripFormatting(message)
        temp = re.sub(self.bot.nickname, "BOTNAME", message,
                      flags=re.IGNORECASE)
        if any(pattern.search(temp) for pattern in self.msg_whitelist):
            return False
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
        # replace nicks to prevent spam that only changes mentioned users
        for nick in self.bot.userlist[self.channel.lower()]:
            msg = msg.replace(nick.lower(), "<user>")
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
        for user in self.bot.userlist[self.channel.lower()]:
            if user.lower() in message:
                count += 1
            if count > self.max_highlights:
                return True
        return False

    def notice(self, user, message):
        if self.check_msg(user, message):
            self.kick_or_ban(user)

    def action(self, user, data):
        pass

    def msg(self, user, message):
        if self.check_msg(user, message):
            self.kick_or_ban(user)

    def connectionLost(self, reason):
        pass
