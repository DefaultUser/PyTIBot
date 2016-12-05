# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2016>  <Sebastian Schmidt>

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

from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.web.static import File
from twisted.internet import threads

import yaml
import logging
import os
import re
from collections import defaultdict

from util import log, formatting
from util import filesystem as fs


LEVEL_ALL = 10
LEVEL_MOST = 11
LEVEL_IMPORTANT = 16

date_regex = re.compile(r"^(19|20)\d\d[- /.](0[1-9]|1[012])[- /.](0[1-9]|"
                        r"[12][0-9]|3[01])$")

line_templates = defaultdict(str, {
    "MSG": '<tr><td class="time">{time}</td><td class="user">'
           '{user}</td><td>{message}</td></tr>',
    "ACTION": '<tr><td class="time">{time}</td><td class="user"><i>'
              '*{user}</i></td><td><i>{data}</i></td></tr>',
    "NOTICE": '<tr><td class="time">{time}</td><td class="user">'
              '[{user}</td><td>{message}]</td></tr>',
    "KICK": '<tr><td class="time">{time}</td><td class="user">&lt;'
            '--</td><td>{kickee} was kicked by {kicker}({message})</td></tr>',
    "QUIT": '<tr><td class="time">{time}</td><td class="user">&lt;'
            '--</td><td>QUIT: {user}({quitMessage})</td></tr>',
    "PART": '<tr><td class="time">{time}</td><td class="user">&lt;'
            '--</td><td>{user} left the channel</td></tr>',
    "JOIN": '<tr><td class="time">{time}</td><td class="user">--&gt;'
            '</td><td>{user} joined the channel</td></tr>',
    "NICK": '<tr><td class="time">{time}</td><td class="user"></td>'
            '<td>{oldnick} is now known as {newnick}</td></tr>',
    "TOPIC": '<tr><td class="time">{time}</td><td class="user"></td>'
             '<td>{user} changed the topic to: {topic}</td></tr>',
    "ERROR": '<tr><td class="time">{time}</td><td class="user"><span'
             ' style="color:#FF0000">ERROR</span></td><td>{msg}</td></tr>'})


base_page_template = fs.get_contents("resources/base_page_template.html")
log_page_template = fs.get_contents("resources/log_page_template.html")
header = fs.get_contents("resources/header.inc")
footer = fs.get_contents("resources/footer.inc")


def _onError(failure, request):
    logging.error(failure.getTraceback())
    request.setResponseCode(404)
    request.write("An error occured, please contact the administrator")
    request.finish()


class BasePage(Resource, object):
    def __init__(self, cm):
        super(BasePage, self).__init__()
        if cm.option_set("HTTPLogServer", "title"):
            self.title = cm.get("HTTPLogServer", "title")
        else:
            self.title = "PyTIBot Log Server"
        # add channel logs
        self.channels = cm.getlist("HTTPLogServer", "channels")
        for channel in self.channels:
            name = channel.lstrip("#")
            self.putChild(name, LogPage(name, log.get_log_dir(cm),
                                        "#{} - {}".format(name, self.title)))
        # add resources
        for f in fs.listdir("resources"):
            relpath = "/".join(["resources", f])
            if fs.isfile(relpath) and not (f.endswith(".html") or
                                           f.endswith(".inc")):
                self.putChild(f, File(fs.get_abs_path(relpath)))

    def getChild(self, name, request):
        if name == '':
            return self
        return super(BasePage, self).getChild(name, request)

    def render_GET(self, request):
        data = ""
        for channel in self.channels:
            data += "<a href='{0}'>{0}</a>".format(channel.lstrip("#"))
        return base_page_template.format(title=self.title, data=data,
                                         header=header, footer=footer)


class LogPage(Resource, object):
    def __init__(self, channel, log_dir, title):
        super(LogPage, self).__init__()
        self.channel = channel
        self.log_dir = log_dir
        self.title = title
        self.putChild("search", SearchPage(channel, log_dir, title))

    def _show_log(self, request):
        log_data = "Log not found"
        MIN_LEVEL = LEVEL_IMPORTANT
        if "level" in request.args:
            MIN_LEVEL = int(request.args["level"][0])
        filename = None
        if "date" in request.args:
            date = request.args["date"][0]
            if date_regex.match(date):
                filename = "{}.{}.yaml".format(self.channel, date)
            elif date == "current":
                filename = "{}.yaml".format(self.channel)
        if filename and os.path.isfile(os.path.join(self.log_dir, filename)):
            with open(os.path.join(self.log_dir, filename)) as logfile:
                log_data = '<table style="width:100%">'
                for data in yaml.load_all(logfile):
                    if data["levelno"] > MIN_LEVEL:
                        data["time"] = data["time"][11:]
                        if "message" in data:
                            data["message"] = formatting.to_html(
                                data["message"])
                        log_data += line_templates[data["levelname"]].format(
                            **data)
                log_data += '</table>'
        request.write(log_page_template.format(log_data=log_data,
                                               title=self.title,
                                               header=header, footer=footer,
                                               channel=self.channel))
        request.finish()

    def render_GET(self, request):
        if not request.args:
            return log_page_template.format(log_data="", title=self.title,
                                            header=header, footer=footer,
                                            channel=self.channel)
        d = threads.deferToThread(self._show_log, request)
        d.addErrback(_onError, request)
        return NOT_DONE_YET


class SearchPage(Resource, object):
    def __init__(self, channel, log_dir, title):
        super(SearchPage, self).__init__()
        self.channel = channel
        self.log_dir = log_dir
        self.title = title

    def render_GET(self, request):
        return "Not implemented yet"
