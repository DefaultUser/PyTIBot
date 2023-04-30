# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2020-2023>  <Sebastian Schmidt>

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
from twisted.web.template import XMLFile, renderer, tags
from twisted.python.filepath import FilePath

from lib.http.common import PageElement, BaseResource
from util import filesystem as fs


logger = Logger()


class OverviewPageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/overview_page_template.html")))

    @renderer
    def child_link(self, request, tag):
        for child, child_res in self.page.children.items():
            if not isinstance(child_res, BaseResource):
                continue
            yield tag.clone()(tags.a(child, href=child+b"/"))


class OverviewPage(BaseResource):
    def __init__(self, crumb, config):
        super(OverviewPage, self).__init__(crumb)
        self.title = config.get("title", "Overview")

    def element(self):
        return OverviewPageElement(self)
