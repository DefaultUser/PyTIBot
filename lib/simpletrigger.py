# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2021>  <Sebastian Schmidt>

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
from util import formatting


def simple_trigger(bot):
    """Send a user defined reply to IRC when the corresponding trigger is mentioned
    """
    while True:
        command, sender, channel = yield
        answer = command["answer"]
        if isinstance(answer, list):
            answer = random.choice(answer)
        msg = answer.replace("$USER", sender).replace("$CHANNEL", channel)

        # Replace colors
        msg = formatting.from_human_readable(msg)
        bot.msg(channel, msg)
