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

from collections import defaultdict
from twisted.logger import Logger

from backends import Backends

from lib import channelwatcher


log = Logger()


def setup_channelwatchers(bot, config, backend):
    if not isinstance(backend, Backends):
        log.error("Invalid backend specified {backend}", backend=backend)
        return
    watcher_dict = defaultdict(list)
    for channel, watchers in config.items():
        for watcher in watchers:
            if isinstance(watcher, dict):
                name = list(watcher.keys())[0]
                watcher_config = watcher[name]
            else:
                name = watcher
                watcher_config = {}
            if not hasattr(channelwatcher, name):
                log.warn("No channelwatcher called {name}, "
                              "ignoring", name=name)
                continue
            type_ = getattr(channelwatcher, name)
            if not backend in type_.supported_backends:
                log.warn("Channelwatcher {name} doesn't support {backend}",
                         name=name, backend=backend)
                continue
            instance = getattr(channelwatcher, name)(bot, channel,
                                                     watcher_config)
            watcher_dict[channel].append(instance)
    return watcher_dict

