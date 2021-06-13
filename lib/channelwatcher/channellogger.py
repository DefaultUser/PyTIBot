# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2021>  <Sebastian Schmidt>

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
import os

from . import abstract
from backends import Backends
from util import log


class ChannelLogger(abstract.ChannelWatcher):
    supported_backends = [Backends.IRC]

    def __init__(self, bot, channel, config):
        super(ChannelLogger, self).__init__(bot, channel, config)
        name = channel.lstrip("#")
        use_yaml = bot.config["Logging"].get("yaml", True)
        if use_yaml:
            name += ".yaml"
        else:
            name += ".txt"
        self.logger = logging.getLogger(channel.lower())
        if bot.config["Logging"].get("log_minor", False):
            log_level = log.TOPIC
        else:
            log_level = log.NOTICE
        self.logger.setLevel(log_level)
        # don't propagate to parent loggers
        self.logger.propagate = False
        # don't add multiple handlers for the same logger
        if not self.logger.handlers:
            # log to file
            log_dir = log.get_channellog_dir()
            if not os.path.isdir(log_dir):
                os.makedirs(log_dir)
            log_handler = log.TimedRotatingFileHandler(os.path.join(
                log_dir, name), when="midnight")
            if use_yaml:
                log_handler.setFormatter(log.yaml_formatter)
                log_handler.namer = log.yaml_namer
            else:
                log_handler.setFormatter(log.txt_formatter)
                log_handler.namer = log.txt_namer
            self.logger.addHandler(log_handler)

    def topic(self, user, topic):
        self.logger.log(log.TOPIC, log.msg_templates[log.TOPIC],
                        {"user": user, "topic": topic})

    def nick(self, oldnick, newnick):
        self.logger.log(log.NICK, log.msg_templates[log.NICK],
                        {"oldnick": oldnick, "newnick": newnick})

    def join(self, user):
        self.logger.log(log.JOIN, log.msg_templates[log.JOIN], {"user": user})

    def part(self, user):
        self.logger.log(log.PART, log.msg_templates[log.PART], {"user": user})

    def quit(self, user, quitMessage):
        self.logger.log(log.QUIT, log.msg_templates[log.QUIT],
                        {"user": user, "quitMessage": quitMessage})

    def kick(self, kickee, kicker, message):
        self.logger.log(log.KICK, log.msg_templates[log.KICK],
                        {"kickee": kickee, "kicker": kicker,
                         "message": message})

    def notice(self, user, message):
        self.logger.log(log.NOTICE, log.msg_templates[log.NOTICE],
                        {"user": user, "message": message})

    def action(self, user, data):
        self.logger.log(log.ACTION, log.msg_templates[log.ACTION],
                        {"user": user, "data": data})

    def msg(self, user, message):
        self.logger.log(log.MSG, log.msg_templates[log.MSG],
                        {"user": user, "message": message})

    def connectionLost(self, reason):
        self.logger.error("Connection Lost")
