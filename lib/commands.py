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
import urllib2
import json
import re
import sys
from twisted.internet import defer

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
    _channel = ""

    def _shutdown(is_admin):
        if is_admin:
            bot.factory.autoreconnect = False
            print("Shutting DOWN")
            bot.quit()
        else:
            bot.msg(_channel, "I won't listen to you!")
    while True:
        args, sender, senderhost, channel = yield
        _channel = channel
        bot.is_user_admin(sender).addCallback(_shutdown)


def bot_help(bot):
    """Guess what this function does"""
    commands = {name: gen.__name__ for name, gen in bot.commands.items()}
    thismodule = sys.modules[__name__]
    while True:
        args, sender, senderhost, channel = yield
        #print getattr(thismodule, args[0], "NOTFOUND")
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
    """Add a nick to the ignore list"""
    _nicks = []

    def _add_ignore(is_admin):
        if is_admin:
            for nick in _nicks:
                bot.cm.add_to_list("Connection", "ignore", nick)
    while True:
        args, sender, senderhost, channel = yield
        _nicks = args
        bot.is_user_admin(sender).addCallback(_add_ignore)


def join(bot):
    """Join a channel"""
    _channels = []

    def _join(is_admin):
        if is_admin:
            for c in _channels:
                bot.join(c)
    while True:
        args, sender, senderhost, channel = yield
        _channels = args
        bot.is_user_admin(sender).addCallback(_join)


def part(bot):
    """Part channel(s)"""
    _channels = []

    def _part(is_admin):
        if is_admin:
            for c in _channels:
                bot.leave(c)
    while True:
        args, sender, senderhost, channel = yield
        _channels = args
        bot.is_user_admin(sender).addCallback(_part)


def change_nick(bot):
    """Change the nick"""
    _newnick = ""

    def _change_nick(is_admin):
        if is_admin:
            bot.setNick(_newnick)
    while True:
        args, sender, senderhost, channel = yield
        _newnick = args[0]
        bot.is_user_admin(sender).addCallback(_change_nick)


def about(bot):
    """Information about this bot"""
    info = "PyTIBot - sources and info can be found at " +\
        "https://github.com/DefaultUser/PyTIBot"
    while True:
        args, sender, senderhost, channel = yield
        bot.msg(channel, info)


def whois(bot):
    """Return the WHOISUSER reply as notice"""
    _sender = ""

    def _reply(params):
        bot.msg(_sender, ", ".join(params))
    while True:
        args, sender, senderhost, channel = yield
        _sender = sender
        bot.user_info(args[0]).addCallback(_reply)


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
    while True:
        args, sender, senderhost, channel = yield
        res = urllib2.urlopen("http://api.icndb.com/jokes/random/1")
        body = res.read().decode()
        cnjoke = json.loads(body)['value'][0]['joke']
        cnjoke = cnjoke.replace("&quot;", "\"")
        if args:
            name = " ".join(args)
            cnjoke = cnjoke.replace("Chuck Norris", name)
        bot.msg(channel, str(cnjoke), length=510)


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
    _line = ""

    def _raw(is_admin):
        if is_admin:
            bot.sendLine(_line)
    while True:
        args, sender, senderhost, channel = yield
        _line = " ".join(args)
        bot.is_user_admin(sender).addCallback(_raw)
