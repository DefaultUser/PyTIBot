# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2016-2026>  <Sebastian Schmidt>

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
from twisted.application import internet, strports
from twisted.internet import ssl
from twisted.web.server import Site
from twisted.logger import Logger
import os
from typing import Optional

from backends import Backends
from backends.irc_factory import IRCFactory
from backends.matrix_service import MatrixService
from twisted.conch import manhole_tap
from lib import http
from lib.git_webhook import GitWebhookServer
from lib.ipc import stdioreceiver
from util.config import Config
from util import filesystem as fs
from util import log


logger = Logger()

try:
    from lib.ipc import dbusobject
    supports_dbus = True
except ImportError:
    logger.debug("Could not import DBus interface")
    supports_dbus = False


mandatory_settings = ["server", "nickname", "admins"]


class Options(usage.Options):
    optParameters = [["config", "c", "pytibot.yaml", "The config file to use"]]


def make_http_service(factory: Site,
                      port: int,
                      interface: Optional[str] = None):
    port_definition = f"tcp6:{port}"
    if interface:
        port_definition += f":interface={interface.replace(':', '\\:')}"
    return strports.service(port_definition, factory)


def make_https_service(factory: Site,
                       port: int,
                       privateKey: str,
                       certKey: Optional[str] = None,
                       interface: Optional[str] = None):
    port_definition = f"ssl:{port}:privateKey={privateKey}"
    if certKey:
        port_definition += f":certKey={certKey}"
    if interface:
        port_definition += f":interface={interface.replace(':', '\\:')}"
    return strports.service(port_definition, factory)


@implementer(IServiceMaker, IPlugin)
class PyTIBotServiceMaker(object):
    tapname = "PyTIBot"
    description = "IRC Bot"
    options = Options

    def makeService(self, options):
        """
        Create an instance of PyTIBot
        """
        config = Config(path=fs.config_file(options["config"]))
        log.channellog_dir_from_config(config)
        if not ("Connection" in config and all([config["Connection"].get(option,
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
            ircbotfactory = IRCFactory(config)
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
        if "Manhole" in config:
            telnetPort = config.Manhole.get("telnetport", None)
            # TODO: allow unix sockets for telnet?
            if telnetPort:
                telnetPort = "tcp:{}".format(telnetPort)
                if telnetInterface := config.Manhole.get("telnetInterface", None):
                    telnetPort += f":interface={telnetInterface.replace(':', '\\:')}"
            sshPort = config.Manhole.get("sshport", None)
            sshKeyDir = config.Manhole.get("sshKeyDir", "<USER DATA DIR>")
            sshKeyName = config.Manhole.get("sshKeyName", "server.key")
            sshKeySize = config.Manhole.get("sshKeySize", 4096)
            if sshPort:
                sshPort = "ssl:{}".format(sshPort)
                if sshInterface := config.Manhole.get("sshInterface", None):
                    sshPort += f":interface={sshInterface.replace(':', '\\:')}"
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

        # TODO: create a generic IPC setup
        stdio_receiver = stdioreceiver.setup(bot_provider)

        if supports_dbus:
            dbus_connection = dbusobject.setup(bot_provider)

        if ("GitWebhook" in config and ("port" in config["GitWebhook"] or
                                        "sshport" in config["GitWebhook"])):
            webhook_server = GitWebhookServer(bot_provider, config)
            factory = Site(webhook_server)
            # https
            webhook_sslport = config["GitWebhook"].get("sslport", None)
            privkey = config["GitWebhook"].get("privkey", None)
            cert = config["GitWebhook"].get("certificate", None)
            webhook_ssl_interface = config["GitWebhook"].get("https_interface", None)
            if webhook_sslport and privkey:
                webhook_https_sv = make_https_service(factory,
                                                      webhook_sslport,
                                                      privkey,
                                                      cert,
                                                      webhook_ssl_interface)
                webhook_https_sv.setServiceParent(mService)
            # http
            webhook_port = config["GitWebhook"].get("port", None)
            webhook_interface = config["GitWebhook"].get("interface", None)
            if webhook_port:
                webhook_http_sv = make_http_service(factory,
                                                    webhook_port,
                                                    webhook_interface)
                webhook_http_sv.setServiceParent(mService)

        if ("HTTPServer" in config and ("port" in config["HTTPServer"] or
                                        "sshport" in config["HTTPServer"])):
            root = http.setup_http_root(config["HTTPServer"]["root"])
            http_factory = Site(root)
            http_port = config["HTTPServer"].get("port", None)
            http_interface = config["HTTPServer"].get("http_interface", None)
            if http_port:
                http_sv = make_http_service(http_factory,
                                            http_port,
                                            http_interface)
                http_sv.setServiceParent(mService)

            http_sslport = config["HTTPServer"].get("sslport", None)
            privkey = config["HTTPServer"].get("privkey", None)
            cert = config["HTTPServer"].get("certificate", None)
            https_interface = config["HTTPServer"].get("https_interface", None)
            if http_sslport and privkey:
                https_sv = make_https_service(http_factory,
                                              http_sslport,
                                              privkey,
                                              cert,
                                              https_interface)
                https_sv.setServiceParent(mService)

        return mService


serviceMaker = PyTIBotServiceMaker()
