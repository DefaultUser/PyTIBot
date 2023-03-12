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

import random

from util.formatting import ColorCodes
from util import formatting


def rand(bot):
    """Randomizer, opt args: 'range int1 int2', 'frange float1 float2' or \
list of choices"""
    while True:
        args, sender, channel = yield
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
            result = formatting.colored("Invalid call - check the help",
                                        ColorCodes.red)
        bot.msg(channel, result)



