# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2020>  <Sebastian Schmidt>

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

import logging
from logging.handlers import TimedRotatingFileHandler
import os
import yaml
import time

from util import decorators
from util import filesystem as fs


# additional logging levels for channel logs
TOPIC = 11
logging.addLevelName(TOPIC, "TOPIC")
NICK = 12
logging.addLevelName(NICK, "NICK")
JOIN = 13
logging.addLevelName(JOIN, "JOIN")
PART = 14
logging.addLevelName(PART, "PART")
QUIT = 15
logging.addLevelName(QUIT, "QUIT")
KICK = 16
logging.addLevelName(KICK, "KICK")
NOTICE = 17
logging.addLevelName(NOTICE, "NOTICE")
ACTION = 18
logging.addLevelName(ACTION, "ACTION")
MSG = 19
logging.addLevelName(MSG, "MSG")

msg_templates = {TOPIC: "%(user)s changed the topic to: %(topic)s",
                 NICK: "%(oldnick)s is now known as %(newnick)s",
                 JOIN: "%(user)s joined the channel",
                 PART: "%(user)s left the channel",
                 QUIT: "Quit: %(user)s (%(quitMessage)s)",
                 KICK: "%(kickee)s was kicked by %(kicker)s (%(message)s)",
                 NOTICE: "[%(user)20s %(message)s]",
                 ACTION: "*%(user)20s %(data)s",
                 MSG: "%(user)20s | %(message)s"}


@decorators.memoize
def get_channellog_dir(config):
    return config["Logging"].get("directory",
                                 os.path.join(fs.adirs.user_log_dir,
                                              "channellogs"))


class YAMLFormatter(object):
    logged_fields = ["levelname", "levelno", "msg", "name"]

    def format(self, record):
        timestruct = time.localtime(record.created)
        d = {}
        d["time"] = time.strftime('%Y-%m-%d_%H:%M:%S', timestruct)
        d["timezone"] = time.tzname[timestruct.tm_isdst]
        for field in YAMLFormatter.logged_fields:
            d[field] = record.__dict__[field]
        d.update(record.__dict__["args"])
        return yaml.dump(d, explicit_start=True, default_flow_style=False)


txt_formatter = logging.Formatter('%(asctime)s %(message)s')
# dateformat for the formatter
txt_formatter.datefmt = '%H:%M:%S'
yaml_formatter = YAMLFormatter()
logging.basicConfig(level=logging.INFO)


def txt_namer(name):
    """
    Remove the '.txt' in the middle and append it at the end
    """
    index = name.rfind(".txt")
    return name[:index] + name[index:].replace(".txt", "") + ".txt"


def yaml_namer(name):
    """
    Remove the '.yaml' in the middle and append it at the end
    """
    index = name.rfind(".yaml")
    return name[:index] + name[index:].replace(".yaml", "") + ".yaml"
