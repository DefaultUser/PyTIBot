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

INFO_MINOR = logging.INFO - 5
logging.addLevelName(INFO_MINOR, "INFO_MINOR")
log_formatter = logging.Formatter('%(asctime)s %(message)s')


class ExtendedLogger(logging.Logger):
    def info_minor(self, msg, *args, **kwargs):
        self.log(INFO_MINOR, msg, *args, **kwargs)


logging.setLoggerClass(ExtendedLogger)
logging.basicConfig(level=logging.INFO)


def setup_logger(channel, log_dir, log_level=logging.INFO, log_when="W0"):
    name = channel.lstrip("#")
    logger = logging.getLogger(channel.lower())
    logger.setLevel(log_level)
    # don't propagate to parent loggers
    logger.propagate = False
    # dateformat for the formatter
    if log_when.upper().startswith("W"):
        log_formatter.datefmt = '%Y-%m-%d_%H:%M:%S'
    else:
        log_formatter.datefmt = '%H:%M:%S'
    # don't add multiple handlers for the same logger
    if not logger.handlers:
        # log to file
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        log_handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, name), when=log_when)
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)
