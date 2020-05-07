# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2020>  <Sebastian Schmidt>

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

from collections import namedtuple
from fnmatch import fnmatch

from util.misc import filter_dict


UserInfo = namedtuple("UserInfo", "nick user host realname")


def match_userinfo(userinfo, pattern):
    if "=" in pattern:
        return filter_dict(userinfo._asdict(), pattern)
    else:
        # fallback to legacy pattern matching: nick!user@host
        userstring = "{0.nick}!{0.user}@{0.host}".format(userinfo)
        if fnmatch(userstring, pattern):
            return True

