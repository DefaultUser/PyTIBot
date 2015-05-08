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

import random
import json
import re
import sys
from twisted.internet import defer
from twisted.web.client import getPage

morse_dict = {'A': '.-', 'B': '-...', 'C': '-.-.',
              'D': '-..', 'E': '.', 'F': '..-.',
              'G': '--.', 'H': '....', 'I': '..',
              'J': '.---', 'K': '-.-', 'L': '.-..',
              'M': '--', 'N': '-.', 'O': '---',
              'P': '.--.', 'Q': '--.-', 'R': '.-.',
              'S': '...', 'T': '-', 'U': '..-',
              'V': '...-', 'W': '.--', 'X': '-..-',
              'Y': '-.--', 'Z': '--..',
              '0': '-----', '1': '.----', '2': '..---',
              '3': '...--', '4': '....-', '5': '.....',
              '6': '-....', '7': '--...', '8': '---..',
              '9': '----.', ' ': ' '}


def shutdown(bot):
    """Shut down the bot (admin function)"""
    def _shutdown(is_admin, channel, args):
        if is_admin:
            print("Shutting DOWN")
            bot.quit(" ".join(args))
        else:
            bot.msg(channel, "I won't listen to you!")

    while True:
        args, sender, senderhost, channel = yield
        bot.is_user_admin(sender).addCallback(_shutdown, channel, args)


def bot_help(bot):
    """Guess what this function does"""
    thismodule = sys.modules[__name__]

    while True:
        args, sender, senderhost, channel = yield
        commands = {name: gen.__name__ for name, gen in bot.commands.items()}
        doc = []
        if args:
            for arg in args:
                try:
                    _gen = getattr(thismodule, commands[arg])
                    doc.append("\x034" + arg + ": \x032" +
                               _gen.__doc__)
                except (AttributeError, KeyError), e:
                    doc.append("\x034No command called \x033" + arg)
        else:
            doc = [", ".join(commands)]
        for d in doc:
            bot.msg(channel, d, length=510)


def ignore(bot):
    """Modify the ignore list - use '+' or 'add' to extend, '-' or 'remove' \
to remove from the list"""
    def _do_ignore(is_admin, sender, args):
        if is_admin:
            if len(args) < 2:
                bot.notice(sender, "Too few arguments")
            else:
                task = args[0]
                nicks = args[1:]

                if task.lower() in ("+", "add"):
                    for nick in nicks:
                        # don't add to short nicks
                        # may ignore everything otherwise(regex)
                        if len(nick) > 3:
                            bot.cm.add_to_list("Connection", "ignore", nick)
                            bot.notice(sender, "Added %s to the ignore list"
                                       % nick)
                        else:
                            bot.notice(sender, "Pattern %s too short, must "
                                       "have at least 3 chars" % nick)
                elif task.lower() in ("-", "remove"):
                    for nick in nicks:
                        if nick in bot.cm.getlist("Connection", "ignore"):
                            bot.cm.remove_from_list("Connection", "ignore",
                                                    nick)
                            bot.notice(sender, "Removed %s from the ignore "
                                       "ignore list" % nick)
                        else:
                            bot.notice(sender, "%s was not found in the "
                                       "ignore list" % nick)
                else:
                    bot.notice(sender, "\x034Invalid call - check the help")

    while True:
        args, sender, senderhost, channel = yield
        bot.is_user_admin(sender).addCallback(_do_ignore, sender, args)


def join(bot):
    """Join a channel"""
    def _join(is_admin, channels):
        if is_admin:
            for c in channels:
                bot.join(c)

    while True:
        args, sender, senderhost, channel = yield
        bot.is_user_admin(sender).addCallback(_join, args)


def part(bot):
    """Part channel(s)"""
    def _part(is_admin, channels):
        if is_admin:
            for c in channels:
                bot.leave(c)

    while True:
        args, sender, senderhost, channel = yield
        bot.is_user_admin(sender).addCallback(_part, args)


def change_nick(bot):
    """Change the nick"""
    def _change_nick(is_admin, newnick):
        if is_admin:
            bot.setNick(newnick)

    while True:
        args, sender, senderhost, channel = yield
        if args:
            bot.is_user_admin(sender).addCallback(_change_nick, args[0])


def about(bot):
    """Information about this bot"""
    info = ("PyTIBot - sources and info can be found at "
            "https://github.com/DefaultUser/PyTIBot")
    while True:
        args, sender, senderhost, channel = yield
        bot.msg(channel, info)


def whois(bot):
    """Return the WHOISUSER reply as notice"""
    def _reply(params, sender):
        bot.notice(sender, ", ".join(params))

    while True:
        args, sender, senderhost, channel = yield
        bot.user_info(args[0]).addCallback(_reply, sender)


def reload_config(bot):
    """Reload the config"""
    def _reload(is_admin):
        if is_admin:
            bot.load_settings()

    while True:
        args, sender, senderhost, channel = yield
        bot.is_user_admin(sender).addCallback(_reload)


def hello(bot):
    """Just a hello function"""
    while True:
        args, sender, senderhost, channel = yield
        bot.msg(channel, "hello %s" % sender)


def tell(bot):
    """Send a message to a user or channel"""
    while True:
        args, sender, senderhost, channel = yield
        if len(args):
            targetnick = args[0]
            body = " ".join(args[1:])
            bot.msg(targetnick, "<" + sender + "> " + body, length=510)


def morse(bot):
    """Translate to morse code"""
    while True:
        args, sender, senderhost, channel = yield
        message = " ".join(args)
        morsecode = []
        for char in message:
            morsecode.append(morse_dict.get(char.upper(), char))
        morsecode = " ".join(morsecode)
        bot.msg(channel, morsecode, length=510)


def unmorse(bot):
    """Translate from morse code"""
    inv_morse_dict = dict([[v, k] for k, v in morse_dict.items()])
    inv_morse_dict[""] = " "
    while True:
        args, sender, senderhost, channel = yield
        newstring = ""
        for char in args:
            newstring += inv_morse_dict.get(char, char)
        bot.msg(channel, newstring.lower(), length=510)


def joke(bot):
    """Chuck Norris jokes from http://icndb.com"""
    url = "http://api.icndb.com/jokes/random/1"

    def _tell_joke(body, channel, name=None):
        cnjoke = json.loads(body)['value'][0]['joke']
        cnjoke = cnjoke.replace("&quot;", "\"")
        if name:
            cnjoke = cnjoke.replace("Chuck Norris", name)
        bot.msg(channel, str(cnjoke), length=510)

    while True:
        args, sender, senderhost, channel = yield
        getPage(url).addCallback(_tell_joke, channel, " ".join(args))


def say(bot):
    """Make the bot say something"""
    while True:
        args, sender, senderhost, channel = yield
        message = " ".join(args)
        if message.lower() == "something":
            message = "To be or not to be - that's the question."
        elif ("%s: say" % bot.nickname) in message:
            message = "Don't chain this command with another bot!"
        if message:
            bot.msg(channel, message, length=510)


def rand(bot):
    """Randomizer, opt args: 'range int1 int2', 'frange float1 float2' or \
list of choices"""
    while True:
        args, sender, senderhost, channel = yield
        try:
            if not args:
                result = random.choice(["Heads", "Tails"])
            elif args[0].lower() == "range":
                result = str(random.randint(int(args[1]), int(args[2])))
            elif args[0].lower() == "frange":
                result = str(random.uniform(float(args[1]), float(args[2])))
            else:
                result = random.choice(args)
        except (IndexError, ValueError):
            result = "\x034Invalid call - check the help"
        bot.msg(channel, result)


def raw(bot):
    """Send a raw IRC line to the server"""
    def _raw(is_admin, line):
        if is_admin:
            bot.sendLine(line)

    while True:
        args, sender, senderhost, channel = yield
        line = " ".join(args)
        bot.is_user_admin(sender).addCallback(_raw, line)
