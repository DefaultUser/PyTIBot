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

import sys

from util import formatting

from lib.commands.administration import *
from lib.commands.education import *
from lib.commands.fun import *
from lib.commands.irc import *


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
                    doc.append(formatting.colored(arg + ": ", "red") +
                               formatting.colored(_gen.__doc__, "dark_blue"))
                except (AttributeError, KeyError):
                    doc.append(formatting.colored("No command called ", "red") +
                               formatting.colored(arg, "dark_green"))
        else:
            doc = [", ".join(commands)]
        for d in doc:
            bot.msg(channel, d, length=510)
