# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018>  <Sebastian Schmidt>

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

from twisted.internet import defer
from twisted.logger import Logger
import treq


log = Logger()


@defer.inlineCallbacks
def shorten_github_url(url):
    """
    Shorten a github url using git.io - if it fails, return the original url
    """
    try:
        response = yield treq.post("https://git.io", data={"url": url},
                                   timeout=5)
    except Exception as e:
        log.warn("Error shortening github url({url}): {error}",
                 url=url, error=e)
        defer.returnValue(url)
    defer.returnValue(response.headers.getRawHeaders("Location", [url])[0])
