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
import this
from twisted.internet import threads
from apiclient.discovery import build
from . import commands
import sys

trigger_module = sys.modules[__name__]

__trigs__ = {r"youtube.com/watch\?v=": "youtube",
             r"^import this$": "import_this",
             r"^from $NICKNAME\.(commands|triggers) import"
             " (\w+)( as (\w+))?$": "enable_command"}


def youtube(bot):
    pat = re.compile(r"youtube.com/watch\?v=([A-Za-z0-9_-]+)"
                     r"(&feature=youtu.be)?\b")
    duration_pattern = re.compile(r"PT(?P<hours>[0-9]{1,2}H)?(?P<minutes>"
                                  "[0-9]{1,2}M)(?P<seconds>[0-9]{1,2}S)")
    yt_service = None
    if bot.cm.option_set("Triggers", "youtube_api_key"):
        YOUTUBE_API_SERVICE_NAME = "youtube"
        YOUTUBE_API_VERSION = "v3"
        YOUTUBE_API_KEY = bot.cm.get("Triggers", "youtube_api_key")
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
            duration = "%d:%02d:%02d" % (int(gd["hours"][:-1]),
                                         int(gd["minutes"][:-1]),
                                         int(gd["seconds"][:-1]))
        else:
            duration = "%d:%02d" % (int(gd["minutes"][:-1]),
                                    int(gd["seconds"][:-1]))
        bot.msg(channel, "Youtube Video title: %s (%s)" % (title, duration),
                length=510)

    while True:
        message, sender, senderhost, channel = yield
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


def import_this(bot):
    """Return the python zen"""
    zen = "".join([this.d.get(char, char) for char in this.s])
    zen = zen.lstrip("The Zen of Python, by Tim Peters\n\n")
    while True:
        message, sender, senderhost, channel = yield
        bot.msg(channel, zen)


def enable_command(bot):
    """Enable command or trigger with python-like syntax"""
    __trigs_inv = dict([[v, k] for k, v in __trigs__.items()])

    def _enable_command(is_admin, channel, cmd, name):
        if not is_admin:
            return

        # no such command
        if not hasattr(commands, cmd):
            bot.msg(channel, "ImportError: No module named %s" % cmd)
            return
        # allready present
        if cmd in bot.commands:
            print("Command %s allready enabled" % cmd)
            return

        # add command
        name = name if name else cmd
        bot.commands[name] = getattr(commands, cmd)(bot)
        next(bot.commands[name])
        # add to config
        bot.cm.set("Commands", name, cmd)
        print("Added %s=%s to config" % (name, cmd))

    def _enable_trigger(is_admin, channel, trigger, name):
        if not is_admin:
            return

        # no such trigger
        if not hasattr(trigger_module, trigger):
            bot.msg(channel, "ImportError: No module named %s" % trigger)
            return

        # allready present
        if trigger in bot.triggers.values():
            print("Trigger %s allready enabled" % trigger)
            return

        #add trigger
        regex = __trigs_inv[trigger]
        bot.triggers[regex] = getattr(trigger_module, trigger)(bot)
        next(bot.triggers[regex])
        # add to config
        bot.cm.add_to_list("Triggers", "enabled", trigger)
        print("Added %s to config" % trigger)

    while True:
        message, sender, senderhost, channel = yield
        pat = re.compile(r"^from %s\.(?P<type>commands|triggers) import"
                         " (?P<cmd>\w+)( as (?P<name>\w+))?$"
                         % bot.nickname)

        match = pat.search(message)
        _type = match.groupdict()["type"]
        if _type == "commands":
            _enable = _enable_command
        else:
            _enable = _enable_trigger
        cmd = match.groupdict()["cmd"]
        name = match.groupdict()["name"]

        bot.is_user_admin(sender).addCallback(_enable, channel, cmd, name)
