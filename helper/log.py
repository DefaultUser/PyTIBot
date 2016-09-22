# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2016>  <Sebastian Schmidt>

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
import logging.handlers
import os
import yaml
import time


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
                 QUIT: "%(user)s (%(quitMessage)s)",
                 KICK: "%(kickee)s was kicked by %(kicker)s (%(message)s)",
                 NOTICE: "[%(user)20s %(message)s]",
                 ACTION: "*%(user)20s %(data)s",
                 MSG: "%(user)20s | %(message)s"}


class ChannelLogger(logging.Logger):
    def topic(self, user, topic):
        self.log(TOPIC, msg_templates[TOPIC], {"user": user, "topic": topic})

    def nick(self, oldnick, newnick):
        self.log(NICK, msg_templates[NICK], {"oldnick": oldnick,
                                             "newnick": newnick})

    def join(self, user):
        self.log(JOIN, msg_templates[JOIN], {"user": user})

    def part(self, user):
        self.log(PART, msg_templates[PART], {"user": user})

    def quit(self, user, quitMessage):
        self.log(QUIT, msg_templates[QUIT], {"user": user,
                                             "quitMessage": quitMessage})

    def kick(self, kickee, kicker, message):
        self.log(KICK, msg_templates[KICK], {"kickee": kickee,
                                             "kicker": kicker,
                                             "message": message})

    def notice(self, user, message):
        self.log(NOTICE, msg_templates[NOTICE], {"user": user,
                                                 "message": message})

    def action(self, user, data):
        self.log(ACTION, msg_templates[ACTION], {"user": user, "data": data})

    def msg(self, user, message):
        self.log(MSG, msg_templates[MSG], {"user": user, "message": message})


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
yaml_formatter = YAMLFormatter()
logging.setLoggerClass(ChannelLogger)
logging.basicConfig(level=logging.INFO)


def setup_logger(channel, log_dir, log_level=NOTICE, log_when="W0",
                 yaml=False):
    name = channel.lstrip("#")
    if yaml:
        name += ".yaml"
    else:
        name += ".txt"
    logger = logging.getLogger(channel.lower())
    logger.setLevel(log_level)
    # don't propagate to parent loggers
    logger.propagate = False
    # dateformat for the formatter
    if log_when.upper().startswith("W"):
        txt_formatter.datefmt = '%Y-%m-%d_%H:%M:%S'
    else:
        txt_formatter.datefmt = '%H:%M:%S'
    # don't add multiple handlers for the same logger
    if not logger.handlers:
        # log to file
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        log_handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, name), when=log_when)
        if yaml:
            log_handler.setFormatter(yaml_formatter)
        else:
            log_handler.setFormatter(txt_formatter)
        logger.addHandler(log_handler)
