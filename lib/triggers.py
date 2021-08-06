# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2021>  <Sebastian Schmidt>

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
import sys
import random

from util import formatting


trigger_module = sys.modules[__name__]

__trigs__ = {r"youtube.com/watch\?v=": "youtube",
             r"^import this$": "import_this",
             r"^from $NICKNAME\.(commands|triggers) import"
             " (\w+)( as (\w+))?$": "enable_command",
             ".": "simple_trigger"}


def youtube(bot, config):
    """Send title and duration of a youtube video to IRC"""
    pat = re.compile(r"youtube.com/watch\?v=([A-Za-z0-9_-]+)"
                     r"(&feature=youtu.be)?\b")
    duration_pattern = re.compile(r"PT(?P<hours>[0-9]{1,2}H)?(?P<minutes>"
                                  "[0-9]{1,2}M)?(?P<seconds>[0-9]{1,2}S)")
    yt_service = None
    YOUTUBE_API_KEY = config.get("youtube_api_key", None)
    if YOUTUBE_API_KEY:
        from apiclient.discovery import build

        YOUTUBE_API_SERVICE_NAME = "youtube"
        YOUTUBE_API_VERSION = "v3"
        yt_service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                           developerKey=YOUTUBE_API_KEY)
        yt_videos = yt_service.videos()

    def _send_title(response, channel):
        title = response["items"][0]["snippet"]["title"].encode("utf-8")
        duration_str = response["items"][0]["contentDetails"]["duration"]
        time_match = duration_pattern.search(duration_str)
        gd = time_match.groupdict()
        duration = ""
        if gd["hours"]:
            duration = "{:d}:{:02d}:{:02d}".format(int(gd["hours"][:-1]),
                                                   int(gd["minutes"][:-1]),
                                                   int(gd["seconds"][:-1]))
        elif gd["minutes"]:
            duration = "{:d}:{:02d}".format(int(gd["minutes"][:-1]),
                                            int(gd["seconds"][:-1]))
        else:
            duration = "0:{:02d}".format(int(gd["seconds"][:-1]))
        bot.msg(channel, "Youtube Video title: {} ({})".format(title,
                                                               duration),
                length=510)

    while True:
        message, sender, channel = yield
        if not yt_service:
            print("No youtube API key set, can't fetch youtube video titles")
            continue
        match = pat.search(message)
        if match is not None:
            # get the video id
            video_id = match.group(1)
            # Don't block the main thread
            request = yt_videos.list(id=video_id, part="snippet,"
                                     "contentDetails", maxResults="1")
            d = threads.deferToThread(request.execute)
            d.addCallback(_send_title, channel)


def import_this(bot, config):
    """Send the python zen to IRC"""
    import this
    zen = "".join([this.d.get(char, char) for char in this.s])
    zen = zen.lstrip("The Zen of Python, by Tim Peters\n\n")
    while True:
        message, sender, channel = yield
        bot.msg(channel, zen)


def enable_command(bot, config):
    """Enable command or trigger with python-like syntax"""
    def _enable(is_admin, channel, _type, cmd, name):
        if not is_admin:
            return

        if _type == "commands":
            success = bot.enable_command(cmd, name, add_to_config=True)
        elif _type == "triggers":
            success = bot.enable_trigger(cmd)
        else:
            raise RuntimeError("Something went horribly wrong")

        if not success:
            bot.msg(channel, "ImportError: No module named {}".format(cmd))

    while True:
        message, sender, channel = yield
        pat = re.compile(r"^from {}\.(?P<type>commands|triggers) import"
                         " (?P<cmd>\w+)( as (?P<name>\w+))?$".format(
                             bot.nickname))

        match = pat.search(message)
        _type = match.groupdict()["type"]
        cmd = match.groupdict()["cmd"]
        name = match.groupdict()["name"]

        bot.is_user_admin(sender).addCallback(_enable, channel, _type,
                                              cmd, name)


def simple_trigger(bot, config):
    """Send a user defined reply to IRC when the corresponding trigger is mentioned
    """
    while True:
        msg, sender, channel = yield
        matches = [trigger for trigger in config if
                   re.search(re.compile(trigger["trigger"].replace(
                       "$nickname", bot.nickname), re.IGNORECASE), msg)]
        for trigger in matches:
            answer = trigger["answer"]
            if isinstance(answer, list):
                answer = random.choice(answer)
            msg = answer.replace("$USER", sender).replace("$CHANNEL", channel)

            # Replace colors
            msg = formatting.from_human_readable(msg)
            bot.msg(channel, msg)
