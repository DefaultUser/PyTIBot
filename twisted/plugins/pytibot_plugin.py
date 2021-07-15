# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2016-2021>  <Sebastian Schmidt>

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
from twisted.logger import Logger
import os

from yamlcfg import YamlConfig

from backends import Backends
from pytibotfactory import PyTIBotFactory
from backends.matrix_service import MatrixService
from twisted.conch import manhole_tap
from lib import http
from lib.git_webhook import GitWebhookServer
from util import filesystem as fs
from util import log


logger = Logger()

try:
    from lib.ipc.dbusobject import create_and_export
    supports_dbus = True
except ImportError as e:
    logger.debug("Could not import DBus interface")
    supports_dbus = False


mandatory_settings = ["server", "nickname", "admins"]


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
        log.channellog_dir_from_config(config)
        if not (config["Connection"] and all([config["Connection"].get(option,
                                                                       False)
                                              for option in
                                              mandatory_settings])):
            raise EnvironmentError("Reading config file failed, mandatory"
                                   " fields not set!\nPlease reconfigure")

        mService = MultiService()

        try:
            mode = Backends[config["Connection"].get("mode", "IRC").upper()]
        except ValueError:
            raise EnvironmentError("No valid backend selected")
        if mode == Backends.IRC:
            # irc client
            ircserver = config["Connection"]["server"]
            ircsslport = config["Connection"].get("sslport", None)
            ircport = config["Connection"].get("port", None)
            ircbotfactory = PyTIBotFactory(config)
            bot_provider = ircbotfactory
            if ircsslport:
                irc_cl = internet.SSLClient(ircserver, ircsslport, ircbotfactory,
                                            ssl.ClientContextFactory())
            elif ircport:
                irc_cl = internet.TCPClient(ircserver, ircport, ircbotfactory)
            else:
                raise EnvironmentError("Neither sslport nor port are given for "
                                       "the irc connection!\nPlease reconfigure")
            irc_cl.setServiceParent(mService)
        elif mode == Backends.MATRIX:
            matrix_service = MatrixService(config)
            bot_provider = matrix_service
            matrix_service.setServiceParent(mService)

        # manhole for debugging
        if config["Manhole"]:
            telnetPort = config.Manhole.get("telnetport", None)
            if telnetPort:
                telnetPort = "tcp:{}".format(telnetPort)
            sshPort = config.Manhole.get("sshport", None)
            sshKeyDir = config.Manhole.get("sshKeyDir", "<USER DATA DIR>")
            sshKeyName = config.Manhole.get("sshKeyName", "server.key")
            sshKeySize = config.Manhole.get("sshKeySize", 4096)
            if sshPort:
                sshPort = "ssl:{}".format(sshPort)
            options = {'namespace': {'get_bot': bot_provider.get_bot},
                       'passwd': os.path.join(fs.adirs.user_config_dir,
                                              'manhole_cred'),
                       'sshPort': sshPort,
                       'sshKeyDir': sshKeyDir,
                       'sshKeyName': sshKeyName,
                       'sshKeySize': sshKeySize,
                       'telnetPort': telnetPort}
            tn_sv = manhole_tap.makeService(options)
            tn_sv.setServiceParent(mService)

        if supports_dbus:
            dbus_connection = create_and_export(bot_provider)

        if (config["GitWebhook"] and ("port" in config["GitWebhook"] or
                                      "sshport" in config["GitWebhook"])):
            webhook_server = GitWebhookServer(bot_provider, config)
            factory = Site(webhook_server)
            # https
            sslport = config["GitWebhook"].get("sslport", None)
            privkey = config["GitWebhook"].get("privkey", None)
            cert = config["GitWebhook"].get("certificate", None)
            if sslport and privkey and cert:
                sslContext = ssl.DefaultOpenSSLContextFactory(
                    privkey, cert)
                webhook_https_sv = internet.SSLServer(sslport, factory,
                                                      sslContext)
                webhook_https_sv.setServiceParent(mService)
            # http
            port = config["GitWebhook"].get("port", None)
            if port:
                webhook_http_sv = internet.TCPServer(port, factory)
                webhook_http_sv.setServiceParent(mService)

        if (config["HTTPServer"] and ("port" in config["HTTPServer"] or
                                      "sshport" in config["HTTPServer"])):
            root = http.setup_http_root(config["HTTPServer"]["root"])
            httpfactory = Site(root)
            port = config["HTTPServer"].get("port", None)
            if port:
                http_sv = internet.TCPServer(port, httpfactory)
                http_sv.setServiceParent(mService)

            sslport = config["HTTPServer"].get("sslport", None)
            privkey = config["HTTPServer"].get("privkey", None)
            cert = config["HTTPServer"].get("certificate", None)
            if sslport and privkey and cert:
                sslContext = ssl.DefaultOpenSSLContextFactory(
                    privkey, cert)
                https_sv = internet.SSLServer(sslport,
                                              httpfactory,
                                              sslContext)
                https_sv.setServiceParent(mService)

        return mService


serviceMaker = PyTIBotServiceMaker()
