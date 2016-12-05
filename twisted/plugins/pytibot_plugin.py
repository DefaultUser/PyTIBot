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

from zope.interface import implementer

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker, MultiService
from twisted.application import internet
from twisted.internet import ssl
from twisted.web.server import Site
import os

from configmanager import ConfigManager

from pytibotfactory import PyTIBotFactory
from twisted.conch import manhole_tap
from lib.httplog import BasePage
from util import filesystem as fs


mandatory_settings = [("Connection", "server"), ("Connection", "port"),
                      ("Connection", "nickname"), ("Connection", "admins")]


class Options(usage.Options):
    optParameters = [["config", "c", "pytibot.ini", "The config file to use"]]


@implementer(IServiceMaker, IPlugin)
class PyTIBotServiceMaker(object):
    tapname = "PyTIBot"
    description = "IRC Bot"
    options = Options

    def makeService(self, options):
        """
        Create an instance of PyTIBot
        """
        cm = ConfigManager(fs.config_file(options["config"]), delimiters=("="))
        if not all([cm.option_set(sec, opt) for sec, opt in
                    mandatory_settings]):
            raise EnvironmentError("Reading config file failed, mandatory"
                                   " fields not set!\nPlease reconfigure")

        mService = MultiService()

        # irc client
        ircserver = cm.get("Connection", "server")
        ircport = cm.getint("Connection", "port")
        ircbotfactory = PyTIBotFactory(cm)
        irc_cl = internet.TCPClient(ircserver, ircport, ircbotfactory)
        irc_cl.setServiceParent(mService)

        # manhole for debugging
        open_manhole = False
        if cm.option_set("Connection", "open_manhole"):
            open_manhole = cm.getboolean("Connection", "open_manhole")

        if open_manhole:
            if cm.option_set("Manhole", "telnetPort"):
                telnetPort = cm.get("Manhole", "telnetPort")
            else:
                telnetPort = None
            if cm.option_set("Manhole", "sshPort"):
                sshPort = cm.get("Manhole", "sshPort")
            else:
                sshPort = None
            options = {'namespace': {'get_bot': ircbotfactory.get_bot},
                       'passwd': os.path.join(fs.adirs.user_config_dir,
                                              'manhole_cred'),
                       'sshPort': sshPort,
                       'telnetPort': telnetPort}
            tn_sv = manhole_tap.makeService(options)
            tn_sv.setServiceParent(mService)

        if (cm.option_set("HTTPLogServer", "port") or
                cm.option_set("HTTPLogServer", "sslport")):
            root = BasePage(cm)
            httpfactory = Site(root)
            if cm.option_set("HTTPLogServer", "port"):
                http_sv = internet.TCPServer(cm.getint("HTTPLogServer",
                                                       "port"),
                                             httpfactory)
                http_sv.setServiceParent(mService)

            if cm.option_set("HTTPLogServer", "sslport"):
                sslContext = ssl.DefaultOpenSSLContextFactory(
                    cm.get("HTTPLogServer", "privkey"),
                    cm.get("HTTPLogServer", "certificate"))
                https_sv = internet.SSLServer(cm.getint("HTTPLogServer",
                                                        "sslport"),
                                              httpfactory,
                                              sslContext)
                https_sv.setServiceParent(mService)

        return mService


serviceMaker = PyTIBotServiceMaker()
