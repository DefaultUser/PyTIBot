# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015>  <Sebastian Schmidt>

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
from twisted.words.protocols import irc
from twisted.internet import defer
from ConfigParser import NoOptionError

# WHOIS reply for AUTH name (NONSTANDARD REPLY!)
irc.symbolic_to_numeric["RPL_WHOISAUTH"] = "330"
irc.numeric_to_symbolic["330"] = "RPL_WHOISAUTH"

from lib import commands
from lib.simpletrigger import simple_trigger
from lib import triggers


class PyTIBot(irc.IRCClient, object):
    """A simple IRC bot"""
    lineRate = 1
    _default_commands = {"quit": "shutdown",
                         "ignore": "ignore",
                         "join": "join",
                         "part": "part",
                         "nick": "change_nick",
                         "help": "bot_help",
                         "reload": "reload_config",
                         "about": "about"
                         }

    def __init__(self, config_manager):
        self.cm = config_manager
        if (self.cm.option_set("Connection", "username") and
                self.cm.option_set("Connection", "serverpassword")):
            self.username = self.cm.get("Connection", "username")
            self.password = self.cm.get("Connection", "serverpassword")
        self._usercallback = {}
        self._authcallback = {}
        self.commands = {}
        self.triggers = {}
        self.load_settings()

        self.simple_trigger = simple_trigger(self)
        next(self.simple_trigger)

    def load_settings(self):
        """Load settings with config manager"""
        self.cm.read()
        self.nickname = self.cm.get("Connection", "nickname")

        # clear the commands
        del self.commands
        self.commands = {}

        # load the commands
        if self.cm.has_section("Commands"):
            cmds = {key: value for key, value in self.cm.items("Commands")}
        else:
            cmds = {}
        cmds.update(self._default_commands)
        self.commands = {name: getattr(commands, func)(self)
                         for name, func in cmds.items()
                         if hasattr(commands, func)}
        for command in self.commands.values():
            next(command)

        # clear the triggers
        del self.triggers
        self.triggers = {}

        # load the triggers
        if self.cm.has_section("Triggers"):
            enabled = self.cm.getlist("Triggers", "enabled")
            self.triggers = {trigger: getattr(triggers, name)(self)
                             for trigger, name in triggers.__all__.items()
                             if name in enabled}
            for trigger in self.triggers.values():
                next(trigger)

    def signedOn(self):
        """Initial functions when signed on to server"""
        try:
            channels = self.cm.getlist("Connection", "channels")
        except NoOptionError:
            channels = []
        for channel in channels:
            self.join(channel)

    def joined(self, channel):
        """Triggered when joining a channel"""
        print("Joined channel: %s" % channel)

    def privmsg(self, user, channel, msg):
        """Triggered by messages"""
        # strip '!'
        print user
        user, temp = user.split('!', 1)
        userhost = temp.split("@")[-1]

        # try if the user should be ignored
        if self.cm.option_set("Connection", "ignore"):
            if any([re.search(re.compile(iu, re.IGNORECASE), user) for iu in
                    self.cm.getlist("Connection", "ignore")]):
                print("ignoring %s" % user)
                return

        print("%s - %s : %s" % (user, channel, msg))
        # strip the formatting
        try:
            msg = irc.stripFormatting(msg)
        except AttributeError:
            # twisted < 13.1
            pass
        msg = msg.strip()

        cmdmode = False
        # Commands
        pat = re.compile(ur"^" + self.nickname + ur"(:|,)?\s")
        if re.search(pat, msg):
            cmdmode = True
            index = 1

        # Private Chat
        if channel == self.nickname:
            if not cmdmode:
                cmdmode = True
                index = 0
            channel = user

        if cmdmode:
            command = msg.split()[index]
            args = msg.split(" ")[index+1:]
            if args:
                while args[0] == "":
                    args.pop(0)
            if command in self.commands:
                self.commands[command].send((args, user, userhost, channel))
            else:
                print("No such command: %s" % command)

        # Triggers
        matches = [(re.search(re.compile(regex.replace("$NICKNAME",
                                                       self.nickname)), msg),
                   gen) for regex, gen in self.triggers.iteritems()]

        # filter out empty matches
        matches = [gen for match, gen in matches if match]

        # send message to generator functions
        for gen in matches:
            gen.send((msg, user, userhost, channel))

        if self.cm.has_section("Simple Triggers"):
            triggers = self.cm.options("Simple Triggers")
            # options in ini are automatically converted to lower case
            # adjust $NICKNAME
            matches = [trigger for trigger in triggers if
                       re.search(re.compile(trigger.replace("$nickname",
                                                            self.nickname),
                                 re.IGNORECASE),
                                 msg)]
            for trigger in matches:
                self.simple_trigger.send((trigger, user, userhost, channel))

    def nickChanged(self, nick):
        """Triggered when own nick changes"""
        self.nickname = nick

    def userRenamed(self, oldname, newname):
        """Triggered when a user changes nick"""
        # expand the ignore list
        if oldname in self.cm.getlist("Connection", "ignore"):
            self.cm.add_to_list("Connection", "ignore", newname)

    def action(self, user, channel, msg):
        """Triggered by actions"""
        pass

    def noticed(self, user, channel, message):
        """Triggered by notice"""
        pass

    def userKicked(self, kickee, channel, kicker, message):
        """Triggered when a user gets kicked"""
        if self.cm.has_option("Actions", "userKicked"):
            msg = self.cm.get("Actions", "userKicked").replace("$KICKER",
                                                               kicker)
            msg = msg.replace("$KICKEE", kickee).replace("$CHANNEL",
                                                         channel)
            if msg:
                self.msg(channel, msg)

    def kickedFrom(self, channel, kicker, message):
        """Triggered when bot gets kicked"""
        if self.cm.getboolean("Connection", "rejoinKicked"):
            self.join(channel)
            if self.cm.has_option("Actions", "kickedFrom"):
                msg = self.cm.get("Actions", "kickedFrom").replace(
                    "$KICKER", kicker)
                msg = msg.replace("$CHANNEL", channel).replace("$MESSAGE",
                                                               message)
                if msg:
                    self.msg(channel, msg)

    def user_info(self, user):
        user = user.lower()
        d = defer.Deferred()
        if not user in self._usercallback:
            self._usercallback[user] = [[], []]

        self._usercallback[user][0].append(d)
        self.whois(user)
        return d

    def get_auth(self, user):
        user = user.lower()
        d = defer.Deferred()
        if not user in self._authcallback:
            self._authcallback[user] = [[], []]

        self._authcallback[user][0].append(d)
        self.whois(user)
        return d

    def irc_RPL_WHOISUSER(self, prefix, params):
        user = params[1].lower()
        if not user in self._usercallback:
            # Never asked for it
            return
        self._usercallback[user][1] += params[1:]

    def irc_RPL_ENDOFWHOIS(self, prefix, params):
        user = params[1].lower()
        if user in self._usercallback:
            callbacks, userinfo = self._usercallback[user]

            for cb in callbacks:
                cb.callback(userinfo)

            del self._usercallback[user]
        if user in self._authcallback:
            callbacks, userinfo = self._authcallback[user]

            for cb in callbacks:
                cb.callback(userinfo)

            del self._authcallback[user]

    def irc_RPL_WHOISAUTH(self, prefix, params):
        user = params[1].lower()
        if not user in self._authcallback:
            # Never asked for it
            return
        self._authcallback[user][1] += params[1:]

    def is_user_admin(self, user):
        """Check if an user is admin - returns a deferred!"""
        user = user.lower()
        d = defer.Deferred()

        def _cb_userinfo(userinfo):
            if not userinfo:
                d.callback(False)
            else:
                if userinfo[2] in self.cm.getlist("Connection", "admins"):
                    d.callback(True)
                else:
                    d.callback(False)

        def _cb_auth(authinfo):
            if not authinfo:
                d.callback(False)
            else:
                if authinfo[1] in self.cm.getlist("Connection", "admins"):
                    d.callback(True)
                else:
                    d.callback(False)

        if self.cm.has_option("Connection", "adminbyhost"):
            adminbyhost = self.cm.getboolean("Connection", "adminbyhost")
        else:
            adminbyhost = False
        if adminbyhost:
            self.user_info(user).addCallback(_cb_userinfo)
        else:
            self.get_auth(user).addCallback(_cb_auth)

        return d

    def quit(self, message=''):
        self.factory.autoreconnect = False
        super(PyTIBot, self).quit(message)
