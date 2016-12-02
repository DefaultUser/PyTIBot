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

import re
from twisted.words.protocols import irc
from twisted.internet import defer
import logging
import sys

from lib import commands
from lib.simpletrigger import simple_trigger
from lib import triggers
from util import decorators, log

# WHOIS reply for AUTH name (NONSTANDARD REPLY!)
irc.symbolic_to_numeric["RPL_WHOISAUTH"] = "330"
irc.numeric_to_symbolic["330"] = "RPL_WHOISAUTH"


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
    _default_triggers = ["enable_command"]

    def __init__(self, config_manager):
        self.cm = config_manager
        if (self.cm.option_set("Connection", "username") and
                self.cm.option_set("Connection", "serverpassword")):
            self.username = self.cm.get("Connection", "username")
            self.password = self.cm.get("Connection", "serverpassword")
        self._usercallback = {}
        self._authcallback = {}
        self.log_channels = []
        self.commands = {}
        self.triggers = {}
        self.userlist = {}
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
        for name, cmd in cmds.iteritems():
            self.enable_command(cmd, name)

        # clear the triggers
        del self.triggers
        self.triggers = {}

        # load the triggers
        trgs = self._default_triggers
        if self.cm.has_section("Triggers"):
            enabled = self.cm.getlist("Triggers", "enabled")
            trgs.extend(enabled)
        for trigger in trgs:
            self.enable_trigger(trigger)

        # logging
        self.setup_logging()

    def setup_logging(self):
        if self.cm.has_section("Logging"):
            if self.cm.has_option("Logging", "channels"):
                self.log_channels = self.cm.getlist("Logging", "channels")
            else:
                self.log_channels = []
                return
            if (self.cm.has_option("Logging", "log_minor") and
                    self.cm.getboolean("Logging", "log_minor")):
                log_level = log.TOPIC
            else:
                log_level = log.NOTICE
            if self.cm.option_set("Logging", "yaml"):
                yaml = self.cm.getboolean("Logging", "yaml")
            else:
                yaml = False
            for n, channel in enumerate(self.log_channels):
                if not channel.startswith("#"):
                    channel = "#" + channel
                # make all channels lowercase
                self.log_channels[n] = channel.lower()
                log.setup_logger(channel.lower(), self.cm,
                                 log_level=log_level, yaml=yaml)
        else:
            self.log_channels = []

    def enable_command(self, cmd, name, add_to_config=False):
        """Enable a command - returns True at success"""
        # no such command
        if not hasattr(commands, cmd):
            logging.warning("No such command: %s" % cmd)
            return False

        # allready present
        if cmd in self.commands:
            logging.warning("Command %s allready enabled" % cmd)
            return True

        name = name if name else cmd
        self.commands[name] = getattr(commands, cmd)(self)
        next(self.commands[name])
        # add to config
        if add_to_config:
            self.cm.set("Commands", name, cmd)
            logging.info("Added %s=%s to config" % (name, cmd))
        return True

    def enable_trigger(self, trigger, add_to_config=False):
        """Enable a trigger - return True at success"""
        __trigs_inv = dict([[v, k] for k, v in triggers.__trigs__.items()])
        # no such trigger
        if not hasattr(triggers, trigger):
            logging.warning("No such trigger: %s" % trigger)
            return False

        # allready present
        # get the name of all generator functions in use
        enabled = []
        for gen in self.triggers.values():
            enabled.append(gen.__name__)
        if trigger in enabled:
            logging.warning("Trigger %s allready enabled" % trigger)
            return True

        # add trigger
        regex = __trigs_inv[trigger]
        self.triggers[regex] = getattr(triggers, trigger)(self)
        next(self.triggers[regex])
        # add to config
        if add_to_config:
            self.cm.add_to_list("Triggers", "enabled", trigger)
            logging.info("Added %s to config" % trigger)
        return True

    def auth(self):
        """Authenticate to the server (NickServ, Q, etc)"""
        options_set = True
        for option in ["service", "command", "username", "password"]:
            options_set = options_set and self.cm.option_set("Auth", option)
        if not options_set:
            logging.warning("Can't auth, not all options are set")
            return

        service = self.cm.get("Auth", "service")
        command = self.cm.get("Auth", "command")
        name = self.cm.get("Auth", "username")
        pw = self.cm.get("Auth", "password")
        self.msg(service, "%s %s %s" % (command, name, pw))

    def set_own_modes(self):
        """Set user modes of the bot itself"""
        modes = self.cm.get("Auth", "modes")
        pat = re.compile(r"(\+(?P<add>(\w+))|-(?P<rem>(\w+)))+")
        match = pat.search(modes)
        if match:
            if match.groupdict()["add"]:
                self.mode(self.nickname, True, match.groupdict()["add"])
            if match.groupdict()["rem"]:
                self.mode(self.nickname, False, match.groupdict()["rem"])

    def signedOn(self):
        """Initial functions when signed on to server"""
        if self.cm.has_section("Auth"):
            self.auth()

        if self.cm.option_set("Auth", "modes"):
            self.set_own_modes()

        if self.cm.has_option("Connection", "channels"):
            channels = self.cm.getlist("Connection", "channels")
        else:
            channels = []
        for channel in channels:
            self.join(channel)

    def msg(self, user, message, length=None):
        """
        Send the message and log it to a channel log if neccessary
        """
        super(PyTIBot, self).msg(user, message, length)
        # user can also be a channel
        user = user.lower()
        if user in self.log_channels:
            logger = logging.getLogger(user)
            logger.msg(self.nickname, message)

    def joined(self, channel):
        """Triggered when joining a channel"""
        logging.info("Joined channel: %s" % channel)
        channel = channel.lower()
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.join(self.nickname)

    def left(self, channel):
        """Triggered when leaving a channel"""
        channel = channel.lower()
        self.userlist.pop(channel)
        logging.info("Left channel: %s" % channel)
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.part(self.nickname)

    def privmsg(self, user, channel, msg):
        """Triggered by messages"""
        # strip '!'
        user, temp = user.split('!', 1)
        userhost = temp.split("@")[-1]

        channel = channel.lower()
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.msg(user, msg)

        # try if the user should be ignored
        if self.ignore_user(user):
            return

        # strip the formatting
        try:
            msg = irc.stripFormatting(msg)
        except AttributeError:
            # twisted < 13.1
            pass
        msg = msg.strip()
        logging.info("%s - %s : %s" % (user, channel, msg))

        cmdmode = False
        # Commands
        pat = re.compile(r"^" + self.nickname + r"(:|,)?\s")
        if pat.search(msg):
            cmdmode = True
            index = 1

        # Private Chat
        if channel == self.nickname.lower():
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
                logging.debug("No such command: %s" % command)

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
        logging.info("Changed own nick to " + nick)

    def ignore_user(self, user):
        """Test whether to ignore the user"""
        if self.cm.option_set("Connection", "ignore"):
            for iu in self.cm.getlist("Connection", "ignore"):
                try:
                    if re.search(re.compile(iu, re.IGNORECASE), user):
                        logging.info("ignoring %s" % user)
                        return True
                except re.error:
                    if iu in user:
                        logging.info("ignoring %s" % user)
                        return True
        return False

    def topicUpdated(self, user, channel, newTopic):
        nick = user.split("!")[0]
        logging.info("{} changed the topic of {} to {}".format(nick, channel,
                                                               newTopic))
        channel = channel.lower()
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.topic(nick, newTopic)

    def userJoined(self, user, channel):
        """Triggered when a user changes nick"""
        channel = channel.lower()
        self.userlist[channel].append(user)
        logging.info("{} joined {}".format(user, channel))
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.join(user)

    def userRenamed(self, oldname, newname):
        """Triggered when a user changes nick"""
        logging.info("{} is now known as {}".format(oldname, newname))
        for channel in self.userlist.keys():
            channel = channel.lower()
            if oldname in self.userlist[channel]:
                self.userlist[channel].remove(oldname)
                self.userlist[channel].append(newname)
                if channel in self.log_channels:
                    logger = logging.getLogger(channel)
                    logger.nick(oldname, newname)
        # expand the ignore list
        if self.ignore_user(oldname):
            self.cm.add_to_list("Connection", "ignore", newname)

        self.remove_user_from_cache(oldname)

    def action(self, user, channel, data):
        """Triggered by actions"""
        nick = user.split("!")[0]
        logging.info("{} | {} {}".format(channel, nick, data))
        channel = channel.lower()
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.action(nick, data)

    def noticed(self, user, channel, message):
        """Triggered by notice"""
        nick = user.split("!")[0]
        logging.info("{} | {} {}".format(channel, nick, message))
        channel = channel.lower()
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.notice(nick, message)

    def userKicked(self, kickee, channel, kicker, message):
        """Triggered when a user gets kicked"""
        # kick message
        if self.cm.has_option("Actions", "userKicked"):
            msg = self.cm.get("Actions", "userKicked").replace("$KICKER",
                                                               kicker)
            msg = msg.replace("$KICKEE", kickee).replace("$CHANNEL",
                                                         channel)
            if msg:
                self.msg(channel, msg)

        logging.info("{} was kicked from {} by {} ({})".format(kickee, channel,
                                                               kicker,
                                                               message))
        channel = channel.lower()
        self.remove_user_from_cache(kickee)
        self.userlist[channel].remove(kickee)

        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.kick(kickee, kicker, message)

    def userLeft(self, user, channel):
        channel = channel.lower()
        self.remove_user_from_cache(user)
        self.userlist[channel].remove(user)

        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.part(user)

    def userQuit(self, user, quitMessage):
        self.remove_user_from_cache(user)

        for channel in self.userlist.keys():
            channel = channel.lower()
            if user in self.userlist[channel]:
                self.userlist[channel].remove(user)
                if channel in self.log_channels:
                    logger = logging.getLogger(channel)
                    logger.quit(user, quitMessage)

    def kickedFrom(self, channel, kicker, message):
        """Triggered when bot gets kicked"""
        channel = channel.lower()
        logging.warning("Kicked from {} by {} ({})".format(channel, kicker,
                                                           message))
        if self.cm.getboolean("Connection", "rejoinKicked"):
            self.join(channel)
            if self.cm.has_option("Actions", "kickedFrom"):
                msg = self.cm.get("Actions", "kickedFrom").replace(
                    "$KICKER", kicker)
                msg = msg.replace("$CHANNEL", channel).replace("$MESSAGE",
                                                               message)
                if msg:
                    self.msg(channel, msg)

        self.userlist.pop(channel)
        if channel in self.log_channels:
            logger = logging.getLogger(channel)
            logger.kick(kicker, message)

    @decorators.memoize_deferred
    def user_info(self, user):
        user = user.lower()
        d = defer.Deferred()
        if user not in self._usercallback:
            self._usercallback[user] = [[], []]

        self._usercallback[user][0].append(d)
        self.whois(user)
        return d

    @decorators.memoize_deferred
    def get_auth(self, user):
        user = user.lower()
        d = defer.Deferred()
        if user not in self._authcallback:
            self._authcallback[user] = [[], []]

        self._authcallback[user][0].append(d)
        self.whois(user)
        return d

    def remove_user_from_cache(self, user):
        """Remove the info about user from get_auth and user_info cache"""
        key = "(%s, %s)|{}" % (str(self), str(user))
        if key in self.user_info.cache:
            del self.user_info.cache[key]
        if key in self.get_auth.cache:
            del self.get_auth.cache[key]

    def irc_RPL_WHOISUSER(self, prefix, params):
        user = params[1].lower()
        if user not in self._usercallback:
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
        if user not in self._authcallback:
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
            maybe_def = defer.maybeDeferred(self.user_info, user)
            maybe_def.addCallback(_cb_userinfo)
        else:
            maybe_def = defer.maybeDeferred(self.get_auth, user)
            maybe_def.addCallback(_cb_auth)

        return d

    def irc_RPL_NAMREPLY(self, prefix, params):
        """
        Reply for the NAMES command. Will automatically be issued when joining
        a channel.
        """
        channel = params[2].lower()
        users = params[3].split()
        nicks = [user.lstrip("@+") for user in users]
        if channel not in self.userlist:
            self.userlist[channel] = nicks
        else:
            self.userlist[channel].extend(nicks)

    def quit(self, message=''):
        self.factory.autoreconnect = False
        logging.info("Shutting down")
        super(PyTIBot, self).quit(message)
