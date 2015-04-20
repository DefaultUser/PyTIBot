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

import urllib2
import contextlib
import re
from lxml import etree

__all__ = {r"youtube.com/watch\?v=": "youtube"}


def youtube(bot):
    pat = re.compile(r"youtube.com/watch\?v=[A-Za-z0-9_-]+\b")
    while True:
        message, sender, senderhost, target = yield
        match = re.search(pat, message)
        if match is not None:
            url = "https://www." + message[match.start():match.end()]
            with contextlib.closing(urllib2.urlopen(url)) as res:
                body = res.read().decode("utf-8")
                root = etree.HTML(body)
                title = root.findtext("head/title")
                if title.endswith(" - YouTube"):
                    title = title[:-10]
                title = title.encode("utf-8")
                bot.msg(target, "Youtube Video Title: %s" % title)
