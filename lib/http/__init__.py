# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2020-2021>  <Sebastian Schmidt>

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

from twisted.logger import Logger
from twisted.web.static import File

import sys
import os

from util import filesystem as fs
from util.misc import str_to_bytes

from lib.http.overview import OverviewPage
from lib.http.logpage import LogPage
from lib.http.votepage import VotePage


log = Logger()


def _string_to_class(s):
    if s == "OverviewPage":
        return OverviewPage
    if s == "LogPage":
        return LogPage
    if s == "VotePage":
        return VotePage
    raise NotImplementedError(f"No such Resource {s}")


def setup_http_root(config):
    res = setup_http_resource(b"", config)
    if not res:
        raise EnvironmentError("Couldn't construct HTTPServer root resource")
    res.putChild(b"assets", File(fs.get_abs_path("resources/assets"),
                                 defaultType="text/plain"))
    return res


def setup_http_resource(crumb, config):
    type_ = config["type"]
    try:
        if type_ == "Static":
            res = File(fs.get_abs_path(os.path.join("resources", config["path"])))
        else:
            res = _string_to_class(type_)(crumb, config)
    except Exception as e:
        log.warn("Error setting up HTTP Resource: {}".format(e))
        return None
    for child_crumb, child_config in config.get("children", dict()).items():
        b_child_crumb = str_to_bytes(child_crumb)
        child = setup_http_resource(b_child_crumb, child_config)
        if child:
            res.putChild(b_child_crumb, child)
    return res

