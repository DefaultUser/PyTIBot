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

from twisted.web.template import Element, XMLFile, renderer
from twisted.web.resource import Resource
from twisted.web.template import flatten
from twisted.web.server import NOT_DONE_YET
from twisted.python.filepath import FilePath

from abc import abstractmethod

from util import filesystem as fs


def webpage_error_handler(failure, request, logger):
    logger.error("Error when answering a request: {e}", e=failure)
    if not request.finished:
        request.setResponseCode(500)
        request.write(b"An error occured, please contact the administrator")
        request.finish()


class BaseResource(Resource, object):
    def __init__(self, crumb):
        super().__init__()
        self.crumb = crumb

    def getChild(self, name, request):
        if name == b'':
            return self
        return super().getChild(name, request)

    @abstractmethod
    def element(self):
        pass

    def render_GET(self, request):
        # redirect if path ends with "/"
        if request.path != b"/" and request.path.endswith(b"/"):
            temp = request.uri.split(b"?", 1)
            args = b"" if len(temp)==1 else b"?"+temp[1]
            uri = request.path[:-1] + args
            request.redirect(uri)
            request.finish()
            return NOT_DONE_YET
        request.write(b'<!DOCTYPE html>\n')
        d = flatten(request, self.element(),
                    request.write)
        def done(ignored):
            request.finish()
            return ignored
        d.addBoth(done)
        return NOT_DONE_YET


class HeaderElement(Element):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/header.inc")))

    def __init__(self, page):
        super().__init__()
        self.page = page

    @renderer
    def title(self, request, tag):
        return tag(self.page.title)


class FooterElement(Element):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/footer.inc")))


class PageElement(Element):
    def __init__(self, page, *args, **kwargs):
        self.page = page
        super().__init__(*args, **kwargs)

    @renderer
    def title(self, request, tag):
        return tag(self.page.title)

    @renderer
    def header(self, request, tag):
        yield HeaderElement(self.page)

    @renderer
    def footer(self, request, tag):
        yield FooterElement()

