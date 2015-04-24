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

import re
from twisted.internet import threads
from gdata.youtube import service as yt

__all__ = {r"youtube.com/watch\?v=": "youtube"}


def youtube(bot):
    pat = re.compile(r"youtube.com/watch\?v=([A-Za-z0-9_-]+)"
                     r"(&feature=youtu.be)?\b")
    yt_service = yt.YouTubeService()

    def _send_title(entry, channel):
        title = entry.media.title.text
        duration = int(entry.media.duration.seconds)
        time = "%d:%02d" % (duration // 60, duration % 60)
        bot.msg(channel, "Youtube Video title: %s (%s)" % (title, time),
                length=510)
    while True:
        message, sender, senderhost, channel = yield
        match = re.search(pat, message)
        if match is not None:
            # get the video id
            video_id = match.group(1)
            # Don't block the main thread
            d = threads.deferToThread(yt_service.GetYouTubeVideoEntry,
                                      video_id=video_id)
            d.addCallback(_send_title, channel)
