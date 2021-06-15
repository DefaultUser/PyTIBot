# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2021>  <Sebastian Schmidt>

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
from twisted.application.service import Service
from twisted.internet.defer import ensureDeferred
from zope.interface import implementer

from backends.interfaces import IBotProvider
from backends.matrix_bot import MatrixBot


@implementer(IBotProvider)
class MatrixService(Service):
    def __init__(self, config):
        self.bot = MatrixBot(config)

    def get_bot(self):
        return self.bot

    def startService(self):
        ensureDeferred(self.bot.start())
        super().startService()

    def stopService(self):
        super().stopService()
        self.bot.stop()
