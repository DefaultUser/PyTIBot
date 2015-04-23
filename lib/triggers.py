# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015>  <Sebastian Schmidt>

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

from twisted.web.client import getPage
import re
from lxml import etree

__all__ = {r"youtube.com/watch\?v=": "youtube"}


def youtube(bot):
    pat = re.compile(r"youtube.com/watch\?v=[A-Za-z0-9_-]+\b")

    def _send_title(body, channel):
        body = body.decode("utf-8")
        root = etree.HTML(body)
        title = root.findtext("head/title")
        if title.endswith(" - YouTube"):
            title = title[:-10]
        title = title.encode("utf-8")
        bot.msg(channel, "Youtube Video Title: %s" % title)
    while True:
        message, sender, senderhost, channel = yield
        match = re.search(pat, message)
        if match is not None:
            url = "https://www." + message[match.start():match.end()]
            getPage(url).addCallback(_send_title, channel)
