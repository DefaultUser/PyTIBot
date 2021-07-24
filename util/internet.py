# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2018-2021>  <Sebastian Schmidt>

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
import zope.interface
from dataclasses import dataclass
from functools import partial


log = Logger()


class _UrlShortenerPayloadAccessorInterface(zope.interface.Interface):
    def __call__(response):
        """Extract the url from the response"""


@zope.interface.implementer(_UrlShortenerPayloadAccessorInterface)
class DirectAccessor:
    @defer.inlineCallbacks
    def __call__(self, response):
        content = yield response.text()
        return content.strip()


@zope.interface.implementer(_UrlShortenerPayloadAccessorInterface)
@dataclass
class JsonAccessor:
    path: list[str]

    @defer.inlineCallbacks
    def __call__(self, response):
        content = yield response.json()
        temp = content
        for frag in self.path:
            temp = temp[frag]
        return temp.strip()


@zope.interface.implementer(_UrlShortenerPayloadAccessorInterface)
@dataclass
class HeaderAccessor:
    key: str
    def __call__(self, response):
        return response.headers.getRawHeaders(self.key, [None])[0]


@defer.inlineCallbacks
def shorten_url(url, service_url, method, headers=None, post_data=None,
                request_params=None, payload_accessor=DirectAccessor()):
    try:
        service_url = service_url.replace("$URL", url)
        # copy dicts in order to not override $URL
        if headers:
            headers = headers.copy()
        if post_data:
            post_data = post_data.copy()
        if request_params:
            request_params = request_params.copy()
        for d in (headers, post_data, request_params):
            if d:
                for key, value in d.items():
                    if value == "$URL":
                        d[key] = url
        # possible TODO: detect "Content-Type: application/json" header and switch
        # post_data to json
        # treq will set the "Content-Type" header based on content
        response = yield treq.request(method, service_url, headers=headers,
                                      data=post_data, params=request_params,
                                      timeout=5)
        shorturl = yield defer.maybeDeferred(payload_accessor, response)
        return shorturl or url
    except Exception as e:
        log.warn("Error shortening url {url} using service {service}: {error}",
                 url=url, service=service_url, error=e)
        return url

shorten_github_url = partial(shorten_url, service_url="https://git.io",
                             method="POST", post_data={"url": "$URL"},
                             payload_accessor=HeaderAccessor("Location"))

