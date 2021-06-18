# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2020>  <Sebastian Schmidt>

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

import sys

from util import formatting

from lib.commands.administration import *
from lib.commands.basic import *
from lib.commands.education import *
from lib.commands.fun import *


def bot_help(bot):
    """Guess what this function does"""
    thismodule = sys.modules[__name__]

    while True:
        args, sender, senderhost, channel = yield
        commands = {name: gen.__name__ for name, gen in bot.commands.items()}
        aliases = []
        for name, alias in bot.aliases.items():
            aliases.append("{name} ({body})".format(
                name=name, body=" ".join([alias.command] + alias.arguments)))
        doc = []
        if args:
            for arg in args:
                if arg:
                    try:
                        _gen = getattr(thismodule, commands[arg])
                        doc.append(formatting.colored(arg + ": ", formatting.IRCColorCodes.red) +
                                   formatting.colored(_gen.__doc__ or "No help available",
                                                      formatting.IRCColorCodes.dark_blue))
                    except (AttributeError, KeyError):
                        doc.append(formatting.colored("No command called ",
                                                      formatting.IRCColorCodes.red) +
                                   formatting.colored(arg, formatting.IRCColorCodes.dark_green))
        else:
            doc = [formatting.colored("Commands: ", formatting.IRCColorCodes.dark_yellow) +
                   ", ".join(commands)]
            if aliases:
                doc.append(formatting.colored("Aliases: ", formatting.IRCColorCodes.dark_green) +
                           ", ".join(aliases))
        for d in doc:
            bot.msg(channel, d, length=510)
