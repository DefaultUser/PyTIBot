# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2023>  <Sebastian Schmidt>

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
from collections import namedtuple
from twisted.words.protocols import irc
from twisted.internet import defer, reactor
from twisted.internet import ssl
from twisted.web.server import Site
from twisted.web.template import Tag
from twisted.logger import Logger
import sys
from zope.interface import implementer

from backends import Backends
from backends.common import setup_channelwatchers
from backends.interfaces import IBot
from lib import commands
from lib import triggers
from lib import channelwatcher
from util import decorators
from util import formatting
from util.formatting.irc import parse_irc
from util.irc import UserInfo

# WHOIS reply for AUTH name (NONSTANDARD REPLY!)
irc.symbolic_to_numeric["RPL_WHOISAUTH"] = "330"
irc.numeric_to_symbolic["330"] = "RPL_WHOISAUTH"

Alias = namedtuple("Alias", "command arguments")


@implementer(IBot)
class IRCBot(irc.IRCClient, object):
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
    log = Logger()

    def __init__(self, config):
        self.config = config
        self.username = self.config["Connection"].get("username", None)
        self.password = self.config["Connection"].get("serverpassword", None)
        self._usercallback = {}
        self._authcallback = {}
        self.commands = {}
        self.aliases = {}
        self.triggers = {}
        self.userlist = {}
        self.load_settings()

    def reload(self):
        self.config.load()
        self.load_settings()

    def load_settings(self):
        """Load settings with config manager"""
        IRCBot.log.info("Loading settings from {path}", path=self.config._path)
        self.nickname = self.config["Connection"]["nickname"]
        self.channelwatchers = setup_channelwatchers(self, self.config.get("Channelmodules", {}),
                                                     Backends.IRC)

        # channel passwords
        self.channel_keys = self.config["Connection"].get("channelkeys", dict())

        # clear the commands
        del self.commands
        self.commands = {}

        # load the commands
        cmds = self.config.get("Commands", {})
        cmds.update(self._default_commands)
        for name, cmd in cmds.items():
            self.enable_command(cmd, name)

        # clear the aliases
        self.aliases = {}

        # load the aliases
        for name, body in self.config.get("Aliases", {}).items():
            self.enable_alias(body, name)

        # clear the triggers
        del self.triggers
        self.triggers = {}

        # load the triggers
        for trigger in self.config.get("Triggers", []):
            self.enable_trigger(trigger)

    def enable_command(self, cmd, name, add_to_config=False):
        """Enable a command - returns True at success"""
        # no such command
        if not hasattr(commands, cmd):
            self.log.warn("No such command: {cmd}", cmd=cmd)
            return False

        # allready present
        if cmd in self.commands:
            self.log.warn("Command {cmd} allready enabled", cmd=cmd)
            return True

        name = name if name else cmd
        self.commands[name] = getattr(commands, cmd)(self)
        next(self.commands[name])
        # add to config
        if add_to_config:
            self.config["Commands"][name] = cmd
            self.config.write()
            self.log.info("Added {name}={cmd} to config", name=name, cmd=cmd)
        return True

    def enable_alias(self, body, name, add_to_config=False):
        cmd, args = body.split(" ", 1)
        if not hasattr(commands, cmd):
            self.log.warn("No such command: {cmd}", cmd=cmd)
            return False

        # allready present
        if name in self.aliases:
            self.log.warn("Alias {name} allready enabled", name=name)
            return True

        self.aliases[name] = Alias(command=cmd, arguments=args.split(" "))
        # add to config
        if add_to_config:
            self.config["Aliases"][name] = body
            self.config.write()
            self.log.info("Added {name}={body} to config", name=name, body=body)
        return True

    def enable_trigger(self, trigger):
        """Enable a trigger - return True at success"""
        if isinstance(trigger, str):
            name = trigger
            config = {}
        else:
            name = list(trigger.keys())[0]
            config = trigger[name]
        __trigs_inv = dict([[v, k] for k, v in triggers.__trigs__.items()])
        # no such trigger
        if not hasattr(triggers, name):
            self.log.warn("No such trigger: {trigger}", trigger=name)
            return False

        # allready present
        # get the name of all generator functions in use
        enabled = []
        for gen in self.triggers.values():
            enabled.append(gen.__name__)
        if name in enabled:
            self.log.warn("Trigger {trigger} allready enabled", trigger=name)
            return True

        # add trigger
        regex = __trigs_inv[name]
        self.triggers[regex] = getattr(triggers, name)(self, config)
        next(self.triggers[regex])
        return True

    def auth(self):
        """Authenticate to the server (NickServ, Q, etc)"""
        service = self.config["Auth"].get("service", None)
        command = self.config["Auth"].get("command", None)
        name = self.config["Auth"].get("username", None)
        pw = self.config["Auth"].get("password", None)
        if not (service and command and name and pw):
            self.log.warn("Can't auth, not all options are set")
            return
        self.msg(service, "{} {} {}".format(command, name, pw))

    def set_own_modes(self):
        """Set user modes of the bot itself"""
        modes = self.config["Auth"].get("modes", "")
        pat = re.compile(r"(\+(?P<add>(\w+))|-(?P<rem>(\w+)))+")
        match = pat.search(modes)
        if match:
            if match.groupdict()["add"]:
                self.mode(self.nickname, True, match.groupdict()["add"])
            if match.groupdict()["rem"]:
                self.mode(self.nickname, False, match.groupdict()["rem"])

    def signedOn(self):
        """Initial functions when signed on to server"""
        if "Auth" in self.config:
            self.auth()
            self.set_own_modes()

        channels = self.config["Connection"].get("channels", [])
        if not isinstance(channels, list):
            channels = [channels]
        for channel in channels:
            self.join(channel, self.channel_keys.get(channel, None))

    def msg(self, target, message, length=None):
        """
        Send the message and log it to a channel log if neccessary
        """
        if target in self.channelwatchers:
            for watcher in self.channelwatchers[target]:
                watcher.msg(self.nickname, message)
        if isinstance(message, Tag):
            message = formatting.to_irc(message)
        super().msg(target, message, length)

    def notice(self, target, message):
        if target in self.channelwatchers:
            for watcher in self.channelwatchers[target]:
                watcher.msg(self.nickname, message)
        if isinstance(message, Tag):
            message = formatting.to_irc(message)
        # Workaround for https://twistedmatrix.com/trac/ticket/10285
        for msg in message.split("\n"):
            super().notice(target, msg)

    def ban(self, channel, user):
        """
        Attempt to ban a user from a channel
        """
        self.mode(channel, True, "b", user=user)

    def joined(self, channel):
        """Triggered when joining a channel"""
        self.log.info("Joined channel: {channel}", channel=channel)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.join(self.nickname)

    def left(self, channel):
        """Triggered when leaving a channel"""
        self.userlist.pop(channel)
        self.log.info("Left channel: {channel}", channel=channel)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.part(self.nickname)

    def privmsg(self, user, channel, msg):
        """Triggered by messages"""
        # strip '!'
        user, temp = user.split('!', 1)
        userhost = temp.split("@")[-1]

        msg = parse_irc(msg)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.msg(user, msg)

        # try if the user should be ignored
        if self.is_user_ignored(user):
            return

        msg = formatting.to_plaintext(msg)
        msg = msg.strip()
        self.log.info("{channel} | {user} : {msg}",
                      channel=channel, user=user, msg=msg)

        cmdmode = False
        # Commands
        pat = re.compile(r"^" + self.nickname + r"(:|,)?\s")
        if pat.search(msg):
            cmdmode = True
            index = 1

        # Private Chat
        if channel.lower() == self.nickname.lower():
            if not cmdmode:
                cmdmode = True
                index = 0
            channel = user

        if cmdmode:
            temp = msg.split(" ")[index:]
            while temp[0] == "":
                temp.pop(0)
            command = temp[0]
            args = temp[1:]
            if command in self.aliases:
                args = self.aliases[command].arguments.copy()
                while "$USER" in args:
                    index = args.index("$USER")
                    args[index] = user
                # replace $ARGS with arguments from command
                if "$ARGS" in args:
                    index = args.index("$ARGS")
                    args.remove("$ARGS")
                    for arg in temp[-1:0:-1]:
                        args.insert(index, arg)
                command = self.aliases[command].command
            if command in self.commands:
                self.commands[command].send((args, user, channel))
            else:
                self.log.debug("No such command: {cmd}", cmd=command)

        # Triggers
        matches = [(re.search(re.compile(regex.replace("$NICKNAME",
                                                       self.nickname)), msg),
                   gen) for regex, gen in self.triggers.items()]

        # filter out empty matches
        matches = [gen for match, gen in matches if match]

        # send message to generator functions
        for gen in matches:
            gen.send((msg, user, channel))

    def nickChanged(self, nick):
        """Triggered when own nick changes"""
        self.nickname = nick
        self.log.info("Changed own nick to {nick}", nick=nick)

    def get_ignorelist(self):
        ignorelist = self.config["Connection"].get("ignore", [])
        if not isinstance(ignorelist, list):
            ignorelist = [ignorelist]
        return ignorelist

    def add_to_ignorelist(self, user):
        if self.is_user_ignored(user):
            return
        ignorelist = self.get_ignorelist()
        ignorelist.append(user)
        self.config["Connection"]["ignore"] = ignorelist
        self.config.write()

    def remove_from_ignorelist(self, user):
        if not self.is_user_ignored(user):
            return
        ignorelist = self.get_ignorelist()
        ignorelist.remove(user)
        self.config["Connection"]["ignore"] = ignorelist
        self.config.write()

    def is_user_ignored(self, user):
        """Test whether to ignore the user"""
        for iu in self.get_ignorelist():
            try:
                if re.search(re.compile(iu, re.IGNORECASE), user):
                    self.log.info("ignoring {user}", user=user)
                    return True
            except re.error:
                if iu in user:
                    self.log.info("ignoring {user}", user=user)
                    return True
        return False

    def topicUpdated(self, user, channel, newTopic):
        nick = user.split("!")[0]
        newTopic = parse_irc(newTopic)
        self.log.info("{nick} changed the topic of {channel} to {topic}",
                      nick=nick, channel=channel,
                      topic=formatting.to_plaintext(newTopic))
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.topic(nick, newTopic)

    def userJoined(self, user, channel):
        """Triggered when a user joins a channel"""
        self.userlist[channel].append(user)
        self.log.info("{user} joined {channel}", user=user, channel=channel)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.join(user)

    def userRenamed(self, oldname, newname):
        """Triggered when a user changes nick"""
        self.log.info("{oldname} is now known as {newname}",
                      oldname=oldname, newname=newname)
        for channel in self.userlist.keys():
            if oldname in self.userlist[channel]:
                self.userlist[channel].remove(oldname)
                self.userlist[channel].append(newname)
                if channel in self.channelwatchers:
                    for watcher in self.channelwatchers[channel]:
                        watcher.nick(oldname, newname)
        # expand the ignore list
        if self.is_user_ignored(oldname):
            self.add_to_ignorelist(newname)

        self.remove_user_from_cache(oldname)

    def action(self, user, channel, data):
        """Triggered by actions"""
        nick = user.split("!")[0]
        self.log.info("{channel} | *{nick} {data}", channel=channel,
                      nick=nick, data=data)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.action(nick, data)

    def noticed(self, user, channel, message):
        """Triggered by notice"""
        nick = user.split("!")[0]
        message = parse_irc(message)
        self.log.info("{channel} | [{nick} {message}]", channel=channel,
                      nick=nick, message=formatting.to_plaintext(message))
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.notice(nick, message)

    def userKicked(self, kickee, channel, kicker, message):
        """Triggered when a user gets kicked"""
        # kick message
        if "Actions" in self.config:
            if msg := self.config["Actions"].get("userKicked", None):
                try:
                    msg = formatting.from_human_readable(msg)
                except Exception as e:
                    self.log.error("Couldn't format reply to userKicked event"
                                   " ({e})", e=e)
                else:
                    msg.fillSlots(kicker=kicker, kickee=kickee, channel=channel)
                    self.msg(channel, msg)

        self.log.info("{kickee} was kicked from {channel} by {kicker} "
                      "({reason})", kickee=kickee, channel=channel,
                      kicker=kicker, reason=message)
        self.remove_user_from_cache(kickee)
        self.userlist[channel].remove(kickee)

        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.kick(kickee, kicker, message)

    def userLeft(self, user, channel):
        self.remove_user_from_cache(user)
        self.userlist[channel].remove(user)
        self.log.info("{user} left {channel}", user=user, channel=channel)

        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.part(user)

    def userQuit(self, user, quitMessage):
        self.remove_user_from_cache(user)
        self.log.info("{user} quit({message})", user=user, message=quitMessage)

        for channel in self.userlist.keys():
            if user in self.userlist[channel]:
                self.userlist[channel].remove(user)
                if channel in self.channelwatchers:
                    for watcher in self.channelwatchers[channel]:
                        watcher.quit(user, quitMessage)

    def kickedFrom(self, channel, kicker, message):
        """Triggered when bot gets kicked"""
        self.log.warn("Kicked from {channel} by {kicker} ({reason})",
                      channel=channel, kicker=kicker, reason=message)
        if self.config["Connection"].get("rejoinKicked", False):
            self.join(channel, self.channel_keys.get(channel, None))
            if self.config["Actions"]:
                if msg := self.config["Actions"].get("kickedFrom", None):
                    try:
                        msg = formatting.from_human_readable(msg)
                    except Exception as e:
                        self.log.error("Couldn't format reply to userKicked event"
                                       " ({e})", e=e)
                    else:
                        msg.fillSlots(kicker=kicker, channel=channel)
                        self.msg(channel, msg)

        self.userlist.pop(channel)
        if channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.kick(self.nickname, kicker, message)

    def get_adminlist(self):
        admins = self.config["Connection"]["admins"]
        if not isinstance(admins, list):
            admins = [admins]
        return admins

    @decorators.memoize_deferred
    def user_info(self, user):
        user = user.lower()
        d = defer.Deferred()
        if user not in self._usercallback:
            self._usercallback[user] = {"defers": [], "userinfo": None}

        self._usercallback[user]["defers"].append(d)
        self.whois(user)
        return d

    @decorators.memoize_deferred
    def get_auth(self, user):
        user = user.lower()
        d = defer.Deferred()
        if user not in self._authcallback:
            self._authcallback[user] = {"defers": [], "userinfo": None}

        self._authcallback[user]["defers"].append(d)
        self.whois(user)
        return d

    def get_displayname(self, user: str, channel: str) -> str:
        return user

    def remove_user_from_cache(self, user):
        """Remove the info about user from get_auth and user_info cache"""
        key = "({}, {})|{}".format(str(self), str(user.lower()), {})
        if key in self.user_info.cache:
            del self.user_info.cache[key]
        if key in self.get_auth.cache:
            del self.get_auth.cache[key]

    def irc_RPL_WHOISUSER(self, prefix, params):
        _, nick, user, host, _, realname = params
        if nick.lower() not in self._usercallback:
            # Never asked for it
            return
        self._usercallback[nick.lower()]["userinfo"] = UserInfo(nick=nick, user=user,
                                                         host=host,
                                                         realname=realname)

    def irc_RPL_ENDOFWHOIS(self, prefix, params):
        user = params[1].lower()
        if user in self._usercallback:
            callbacks = self._usercallback[user]["defers"]
            userinfo = self._usercallback[user]["userinfo"]

            if userinfo is None:
                for cb in callbacks:
                    cb.errback(KeyError("No such nick {}".format(user)))
            else:
                for cb in callbacks:
                    cb.callback(userinfo)

            del self._usercallback[user]
        if user in self._authcallback:
            callbacks = self._authcallback[user]["defers"]
            userinfo = self._authcallback[user]["userinfo"]

            for cb in callbacks:
                cb.callback(userinfo)

            del self._authcallback[user]

    def irc_RPL_WHOISAUTH(self, prefix, params):
        user = params[1].lower()
        if user not in self._authcallback:
            # Never asked for it
            return
        self._authcallback[user]["userinfo"] = params[2]

    def is_user_admin(self, user):
        """Check if an user is admin - returns a deferred!"""
        user = user.lower()
        d = defer.Deferred()

        def _cb_userinfo(userinfo):
            if not userinfo:
                d.callback(False)
            else:
                if userinfo.host in self.get_adminlist():
                    d.callback(True)
                else:
                    d.callback(False)

        def _cb_auth(authinfo):
            if not authinfo:
                d.callback(False)
            else:
                if authinfo in self.get_adminlist():
                    d.callback(True)
                else:
                    d.callback(False)

        if self.config["Connection"].get("adminbyhost", False):
            maybe_def = defer.maybeDeferred(self.user_info, user)
            maybe_def.addCallback(_cb_userinfo)
        else:
            maybe_def = defer.maybeDeferred(self.get_auth, user)
            maybe_def.addCallback(_cb_auth)

        return d

    def get_user_info(self, user):
        """Returns the whois info for a user"""
        return defer.maybeDeferred(self.user_info, user.lower())

    def irc_RPL_NAMREPLY(self, prefix, params):
        """
        Reply for the NAMES command. Will automatically be issued when joining
        a channel.
        """
        channel = params[2]
        users = params[3].split()
        nicks = [user.lstrip("@+") for user in users]
        if channel not in self.userlist:
            self.userlist[channel] = nicks
        else:
            self.userlist[channel].extend(nicks)

    def quit(self, message=''):
        self.factory.autoreconnect = False
        self.log.info("Shutting down")
        for channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.quit(self.nickname, message)
                watcher.stop()
        super().quit(message)

    def connectionLost(self, reason):
        for channel in self.channelwatchers:
            for watcher in self.channelwatchers[channel]:
                watcher.connectionLost(reason)
        super().connectionLost(reason)
