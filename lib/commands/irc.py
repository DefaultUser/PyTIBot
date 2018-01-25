# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2018>  <Sebastian Schmidt>

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


def whois(bot):
    """Return the WHOISUSER reply as notice"""
    def _reply(params, sender):
        bot.notice(sender, ", ".join(params))

    while True:
        args, sender, senderhost, channel = yield
        bot.get_user_info(args[0]).addCallback(_reply, sender)


def hello(bot):
    """Just a hello function"""
    while True:
        args, sender, senderhost, channel = yield
        bot.msg(channel, "hello {}".format(sender))


def tell(bot):
    """Send a message to a user or channel"""
    while True:
        args, sender, senderhost, channel = yield
        if len(args):
            targetnick = args[0]
            body = " ".join(args[1:])
            bot.msg(targetnick, "<" + sender + "> " + body, length=510)


def say(bot):
    """Make the bot say something"""
    while True:
        args, sender, senderhost, channel = yield
        message = " ".join(args)
        if message.lower() == "something":
            message = "To be or not to be - that's the question."
        elif ("{}: say".format(bot.nickname)) in message:
            message = "Don't chain this command with another bot!"
        if message:
            bot.msg(channel, message, length=510)
