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
import sys


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


if sys.version_info.major < 3:
    # TODO: drop python2 support once twisted is fully ported to python3
    class TimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
        """
        This class is a backport of the
        python3 version of TimedRotatingFileHandler

        Copyright 2001-2016 by Vinay Sajip. All Rights Reserved.

        Permission to use, copy, modify, and distribute this software and its
        documentation for any purpose and without fee is hereby granted,
        provided that the above copyright notice appear in all copies and that
        both that copyright notice and this permission notice appear in
        supporting documentation, and that the name of Vinay Sajip
        not be used in advertising or publicity pertaining to distribution
        of the software without specific, written prior permission.
        VINAY SAJIP DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE, INCLUDING
        ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
        VINAY SAJIP BE LIABLE FOR ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR
        ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER
        IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT
        OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
        """
        def __init__(self, filename, when='h', interval=1, backupCount=0,
                     encoding=None, delay=False, utc=False):
            super(TimedRotatingFileHandler, self).__init__(filename, when,
                                                           interval,
                                                           backupCount,
                                                           encoding, delay,
                                                           utc)
            self.namer = None
            self.rotator = None

        def rotation_filename(self, default_name):
            if not callable(self.namer):
                result = default_name
            else:
                result = self.namer(default_name)
            return result

        def rotate(self, source, dest):
            if not callable(self.rotator):
                # Issue 18940: A file may not have been created if delay is True.
                if os.path.exists(source):
                    os.rename(source, dest)
            else:
                self.rotator(source, dest)

        def doRollover(self):
            if self.stream:
                self.stream.close()
                self.stream = None

            # get the time that this sequence started at and make it a TimeTuple
            currentTime = int(time.time())
            dstNow = time.localtime(currentTime)[-1]
            t = self.rolloverAt - self.interval

            if self.utc:
                timeTuple = time.gmtime(t)
            else:
                timeTuple = time.localtime(t)
                dstThen = timeTuple[-1]
                if dstNow != dstThen:
                    if dstNow:
                        addend = 3600
                    else:
                        addend = -3600
                    timeTuple = time.localtime(t + addend)

            dfn = self.rotation_filename(self.baseFilename + "." +
                                         time.strftime(self.suffix, timeTuple))

            if os.path.exists(dfn):
                os.remove(dfn)
            self.rotate(self.baseFilename, dfn)

            if self.backupCount > 0:
                for s in self.getFilesToDelete():
                    os.remove(s)

            if not self.delay:
                self.stream = self._open()

            newRolloverAt = self.computeRollover(currentTime)
            while newRolloverAt <= currentTime:
                newRolloverAt = newRolloverAt + self.interval
            # If DST changes and midnight or weekly rollover, adjust for this.
            if (self.when == 'MIDNIGHT' or self.when.startswith('W')) and not self.utc:
                dstAtRollover = time.localtime(newRolloverAt)[-1]
                if dstNow != dstAtRollover:
                    # DST kicks in before next rollover, so we need to deduct an hour
                    if not dstNow:
                        addend = -3600
                    # DST bows out before next rollover, so we need to add an hour
                    else:
                        addend = 3600
                    newRolloverAt += addend
            self.rolloverAt = newRolloverAt

else:
    TimedRotatingFileHandler = logging.handlers.TimedRotatingFileHandler


txt_formatter = logging.Formatter('%(asctime)s %(message)s')
yaml_formatter = YAMLFormatter()
logging.setLoggerClass(ChannelLogger)
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
        log_handler = TimedRotatingFileHandler(os.path.join(log_dir, name),
                                               when=log_when)
        if yaml:
            log_handler.setFormatter(yaml_formatter)
            log_handler.namer = yaml_namer
        else:
            log_handler.setFormatter(txt_formatter)
            log_handler.namer = txt_namer
        logger.addHandler(log_handler)
