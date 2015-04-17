#!/usr/bin/env python
# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015>  <Sebastian Schmidt>

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

from pytibotfactory import PyTIBotFactory
from twisted.internet import reactor
from configmanager import ConfigManager
import sys

mandatory_settings = [("Connection", "server"), ("Connection", "port"),
                      ("Connection", "nickname"), ("Connection", "admins")]

if __name__ == "__main__":
    configfile = sys.argv[1] if len(sys.argv) > 1 else "pytibot.ini"
    # create Config Manager
    cm = ConfigManager(configfile, delimiters=("="))
    if all([cm.option_set(sec, opt) for sec, opt in mandatory_settings]):
        # connect factory to host and port
        server = cm.get("Connection", "server")
        port = cm.getint("Connection", "port")
        reactor.connectTCP(server, port, PyTIBotFactory(cm))
        reactor.run()
    else:
        print("Reading config file failed, mandatory fields not set!")
        print("Please reconfigure")
