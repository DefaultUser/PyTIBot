# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018-2020>  <Sebastian Schmidt>

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
from twisted.web.resource import Resource
from twisted.web.template import flatten
from twisted.web.server import NOT_DONE_YET
import treq

from abc import abstractmethod

from util.misc import bytes_to_str


log = Logger()


@defer.inlineCallbacks
def shorten_github_url(url):
    """
    Shorten a github url using git.io - if it fails, return the original url
    """
    try:
        response = yield treq.post("https://git.io", data={"url": url},
                                   timeout=5)
        defer.returnValue(response.headers.getRawHeaders("Location", [url])[0])
    except Exception as e:
        log.warn("Error shortening github url({url}): {error}",
                 url=url, error=e)
        defer.returnValue(url)

def webpage_error_handler(failure, request, logger):
    logger.error("Error when answering a request: {e}", e=failure)
    if not request.finished:
        request.setResponseCode(500)
        request.write(b"An error occured, please contact the administrator")
        request.finish()


class BaseResource(Resource, object):
    def getChild(self, name, request):
        if name == b'':
            return self
        return super(BaseResource, self).getChild(name, request)

    @abstractmethod
    def element(self):
        pass

    def render_GET(self, request):
        request.write(b'<!DOCTYPE html>\n')
        d = flatten(request, self.element(),
                    request.write)
        def done(ignored):
            request.finish()
            return ignored
        d.addBoth(done)
        return NOT_DONE_YET

