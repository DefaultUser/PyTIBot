# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2019-2021>  <Sebastian Schmidt>

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

from twisted.logger import Logger

from . import abstract
from backends import Backends
from util.irc import match_userinfo


class Autovoice(abstract.ChannelWatcher):
    log = Logger()
    supported_backends = [Backends.IRC]

    def __init__(self, bot, channel, config):
        super(Autovoice, self).__init__(bot, channel, config)
        # pattern so only certain new users get voiced
        self.patterns = config.get("patterns", ["*"])
        if isinstance(self.patterns, str):
            self.log.warn("'patterns' should be a list, not a single string")
            self.patterns = [self.patterns]

    def topic(self, user, topic):
        pass

    def nick(self, oldnick, newnick):
        pass

    def join(self, user):
        user_low = user.lower()
        if user_low == self.bot.nickname.lower():
            return

        def _cb(userinfo):
            for pattern in self.patterns:
                if match_userinfo(userinfo, pattern):
                    self.log.debug("Pattern found for user {user}", user=user)
                    self.bot.mode(self.channel, True, "v", user=user)
                    return

        def _eb(fail):
            self.log.error("An error occured while retrieving 'whois' "
                           "information about user {user}: {error}",
                           user=user, error=fail)

        self.bot.get_user_info(user).addCallbacks(_cb, _eb)

    def part(self, user):
        pass

    def quit(self, user, quitMessage):
        pass

    def kick(self, kickee, kicker, message):
        pass

    def notice(self, user, message):
        pass

    def action(self, user, data):
        pass

    def msg(self, user, message):
        pass

    def connectionLost(self, reason):
        pass
