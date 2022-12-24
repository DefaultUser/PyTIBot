# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018-2022>  <Sebastian Schmidt>

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

import os
from twisted.logger import Logger

from . import abstract
from backends import Backends
from util import filesystem as fs
# FIXME: replace IRC formatting with internal formatting
from util.formatting import irc as formatting
from util.irc import match_userinfo


class Greeter(abstract.ChannelWatcher):
    log = Logger()
    supported_backends = [Backends.IRC]

    def __init__(self, bot, channel, config):
        super(Greeter, self).__init__(bot, channel, config)
        # pattern so only certain new users get greeted
        # useful to only greet webchat user
        self.patterns = config.get("patterns", ["*"])
        if isinstance(self.patterns, str):
            self.log.warn("'patterns' should be a list, not a single string")
            self.patterns = [self.patterns]
        # nicks that many users are likely to use
        self.standard_nicks = set(map(lambda x: x.lower(),
                                      config.get("standard_nicks", [])))
        self.message = formatting.from_human_readable(
            config.get("message", "Welcome, $USER"))
        # read list of previously greeted users from disk
        self.already_greeted = self.load_greeted_file()

    def load_greeted_file(self):
        greeted_file = self.get_greeted_file()
        if not os.path.isfile(greeted_file):
            return set()
        with open(greeted_file, "r") as f:
            return set(line.strip() for line in f)

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
                    self.bot.notice(user, self.message.replace("$USER", user))
                    if user_low not in self.standard_nicks:
                        self.log.debug("Adding {user} to 'already_greeted'",
                                       user=user)
                        self.already_greeted.add(user_low)
                    return

        def _eb(fail):
            self.log.error("An error occured while retrieving 'whois' "
                           "information about user {user}: {error}",
                           user=user, error=fail)

        if user_low in self.already_greeted:
            return
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

    def get_greeted_file(self):
        greeted_path = os.path.join(fs.adirs.user_cache_dir, "greeter")
        if not os.path.isdir(greeted_path):
            os.makedirs(greeted_path)
        return os.path.join(greeted_path, self.channel.lstrip("#"))

    def connectionLost(self, reason):
        self.stop()

    def stop(self):
        with open(self.get_greeted_file(), "w") as f:
            f.write("\n".join(self.already_greeted))
