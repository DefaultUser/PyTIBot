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

from yamlcfg import YamlConfig

from pytibotfactory import PyTIBotFactory
from twisted.conch import manhole_tap
from lib.httplog import BasePage, LogPage
from util import filesystem as fs
from util import log


mandatory_settings = ["server", "port", "nickname", "admins"]


class Options(usage.Options):
    optParameters = [["config", "c", "pytibot.yaml", "The config file to use"]]


@implementer(IServiceMaker, IPlugin)
class PyTIBotServiceMaker(object):
    tapname = "PyTIBot"
    description = "IRC Bot"
    options = Options

    def makeService(self, options):
        """
        Create an instance of PyTIBot
        """
        config = YamlConfig(path=fs.config_file(options["config"]))
        if not (config["Connection"] and all([config["Connection"].get(option,
                                                                       False)
                                              for option in
                                              mandatory_settings])):
            raise EnvironmentError("Reading config file failed, mandatory"
                                   " fields not set!\nPlease reconfigure")

        mService = MultiService()

        # irc client
        ircserver = config["Connection"]["server"]
        ircport = config["Connection"]["port"]
        ircbotfactory = PyTIBotFactory(config)
        irc_cl = internet.TCPClient(ircserver, ircport, ircbotfactory)
        irc_cl.setServiceParent(mService)

        # manhole for debugging
        if config["Manhole"]:
            telnetPort = config.Manhole.get("telnetport", None)
            if telnetPort:
                telnetPort = str(telnetPort)
            sshPort = config.Manhole.get("sshport", None)
            if sshPort:
                sshPort = str(sshPort)
            print(telnetPort, sshPort)
            options = {'namespace': {'get_bot': ircbotfactory.get_bot},
                       'passwd': os.path.join(fs.adirs.user_config_dir,
                                              'manhole_cred'),
                       'sshPort': sshPort,
                       'telnetPort': telnetPort}
            tn_sv = manhole_tap.makeService(options)
            tn_sv.setServiceParent(mService)

        if (config["HTTPLogServer"] and ("port" in config["HTTPLogServer"] or
                                         "sshport" in config["HTTPLogServer"])):
            channels = config["HTTPLogServer"]["channels"]
            if not isinstance(channels, list):
                channels = [channels]
            if len(channels) == 1:
                title = config["HTTPLogServer"].get("title",
                                                    "PyTIBot Log Server")
                root = LogPage(channels[0], log.get_log_dir(config), title,
                               singlechannel=True)
            else:
                root = BasePage(config)
            httpfactory = Site(root)
            port = config["HTTPLogServer"].get("port", None)
            if port:
                http_sv = internet.TCPServer(port, httpfactory)
                http_sv.setServiceParent(mService)

            sslport = config["HTTPLogServer"].get("sslport", None)
            privkey = config["HTTPLogServer"].get("privkey", None)
            cert = config["HTTPLogServer"].get("certificate", None)
            if sslport and privkey and cert:
                sslContext = ssl.DefaultOpenSSLContextFactory(
                    privkey, cert)
                https_sv = internet.SSLServer(sslport,
                                              httpfactory,
                                              sslContext)
                https_sv.setServiceParent(mService)

        return mService


serviceMaker = PyTIBotServiceMaker()
