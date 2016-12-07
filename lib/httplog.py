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
from twisted.words.protocols import irc
from twisted.internet import threads
from twisted.internet.task import LoopingCall

from whoosh.index import create_in
from whoosh import fields
from whoosh.qparser import QueryParser

import yaml
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
try:
    from html import escape as htmlescape
except ImportError:
    # python2
    from cgi import escape as htmlescape

from util import log, formatting
from util import filesystem as fs


LEVEL_ALL = 10
LEVEL_MOST = 11
LEVEL_IMPORTANT = 16

date_regex = re.compile(r"^(19|20)\d\d[- /.](0[1-9]|1[012])[- /.](0[1-9]|"
                        r"[12][0-9]|3[01])$")
url_pat = re.compile(r"(https?:\/\/([\da-z\.-]+)\.([a-z\.]{2,6})"
                     r"([\/\w\.-]*)*)")

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
search_page_template = fs.get_contents("resources/search_page_template.html")
header = fs.get_contents("resources/header.inc")
footer = fs.get_contents("resources/footer.inc")


def _onError(failure, request):
    logging.error(failure.getTraceback())
    request.setResponseCode(500)
    request.write("An error occured, please contact the administrator")
    request.finish()


def _prepare_yaml_element(element):
    """Prepare a yaml element for display in html"""
    element["time"] = element["time"][11:]
    for key, val in element.items():
        if type(element[key]) == str:
            element[key] = htmlescape(val)
    if "message" in element:
        element["message"] = formatting.to_html(element["message"])
        element["message"] = url_pat.sub(r"<a href='\1'>\1</a>",
                                         element["message"])


class BaseResource(Resource, object):
    def getChild(self, name, request):
        if name == '':
            return self
        return super(BaseResource, self).getChild(name, request)


class BasePage(BaseResource):
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

    def render_GET(self, request):
        data = ""
        for channel in self.channels:
            data += "<a href='{0}'>{0}</a>".format(channel.lstrip("#"))
        return base_page_template.format(title=self.title, data=data,
                                         header=header, footer=footer)


class LogPage(BaseResource):
    def __init__(self, channel, log_dir, title):
        super(LogPage, self).__init__()
        self.channel = channel
        self.log_dir = log_dir
        self.title = title
        self.putChild("search", SearchPage(channel, log_dir, title))

    def _show_log(self, request):
        log_data = "Log not found"
        MIN_LEVEL = LEVEL_IMPORTANT
        try:
            MIN_LEVEL = int(request.args["level"][0])
        except (KeyError, ValueError):
            pass
        filename = None
        if "date" in request.args:
            date = request.args["date"][0]
            if date_regex.match(date):
                filename = "{}.{}.yaml".format(self.channel, date)
            elif date == "current":
                filename = "{}.yaml".format(self.channel)
        if filename and os.path.isfile(os.path.join(self.log_dir, filename)):
            with open(os.path.join(self.log_dir, filename)) as logfile:
                log_data = '<table>'
                for data in yaml.load_all(logfile):
                    if data["levelno"] > MIN_LEVEL:
                        _prepare_yaml_element(data)
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
            request.args["date"] = ["current"]
        d = threads.deferToThread(self._show_log, request)
        d.addErrback(_onError, request)
        return NOT_DONE_YET


class SearchPage(BaseResource):
    PAGELEN = 10

    def __init__(self, channel, log_dir, title):
        super(SearchPage, self).__init__()
        self.channel = channel
        self.log_dir = log_dir
        self.title = title
        self.last_index_update = 0
        d = threads.deferToThread(self._setup_index)

    def _fields_from_yaml(self, name):
        path = os.path.join(self.log_dir, name)
        with open(path) as f:
            content = []
            for element in yaml.load_all(f.read()):
                if element["levelname"] == "MSG":
                    msg = irc.stripFormatting(element["message"])
                    content.append(msg.decode("utf-8"))
            datestr = name.lstrip(self.channel+".").rstrip(".yaml")
            try:
                date = datetime.strptime(datestr, "%Y-%m-%d")
            except ValueError:
                # default to today
                date = datetime.now()
            c = u" ... ".join(content)
        return c, date

    def _setup_index(self):
        schema = fields.Schema(path=fields.ID(stored=True),
                               content=fields.TEXT(stored=True),
                               date=fields.DATETIME(stored=True,
                                                    sortable=True))
        indexpath = os.path.join(fs.adirs.user_cache_dir, "index",
                                 self.channel)
        if not os.path.exists(indexpath):
            os.makedirs(indexpath)
        self.ix = create_in(indexpath, schema)
        writer = self.ix.writer()
        for name in os.listdir(self.log_dir):
            if name.startswith(self.channel+".") and name.endswith(".yaml"):
                c, date = self._fields_from_yaml(name)
                writer.add_document(path=unicode(name), content=c, date=date)
        writer.commit()
        self.last_index_update = time.time()
        lc = LoopingCall(self.update_index)
        lc.start(300, now=False)

    def _update_index(self):
        with self.ix.searcher() as searcher:
            writer = self.ix.writer()
            indexed_paths = set()
            for field in searcher.all_stored_fields():
                indexed_paths.add(field["path"])
        for name in os.listdir(self.log_dir):
            if name.startswith(self.channel+".") and name.endswith(".yaml"):
                if name not in indexed_paths:
                    c, date = self._fields_from_yaml(name)
                    writer.add_document(path=unicode(name), content=c,
                                        date=date)
        # <channelname>.yaml is the only file that can change
        name = u"{}.yaml".format(self.channel)
        path = os.path.join(self.log_dir, name)
        if os.path.isfile(path):
            modtime = os.path.getmtime(path)
            if modtime > self.last_index_update:
                c, date = self._fields_from_yaml(name)
                if name in indexed_paths:
                    writer.delete_by_term("path", name)
                writer.update_document(path=name, content=c, date=date)
        writer.commit()
        self.last_index_update = time.time()

    def update_index(self):
        return threads.deferToThread(self._update_index)

    def _search_logs(self, request):
        querystr = request.args["q"][0]
        if "page" in request.args:
            try:
                page = int(request.args["page"][0])
            except ValueError:
                page = -1
        else:
            page = 1
        if page < 1:
            log_data = "Invalid page number specified"
            request.write(search_page_template.format(log_data=log_data,
                                                      title=self.title,
                                                      header=header,
                                                      footer=footer,
                                                      channel=self.channel))
            request.finish()
            return
        with self.ix.searcher() as searcher:
            query = QueryParser("content", self.ix.schema).parse(querystr)
            results = searcher.search_page(query, page,
                                           pagelen=SearchPage.PAGELEN,
                                           sortedby="date", reverse=True)
            log_data = ""
            for hit in results:
                log_data += ("<ul class='accordion'><div><input id='id{date}' "
                             "type='checkbox'/><label for='id{date}'>{date}"
                             "</label><article class='accordion-article'>"
                             "<a href='/{channel}?date={date}'>Full log</a>"
                             "</br>".format(channel=self.channel,
                                            date=hit["date"].strftime(
                                                "%Y-%m-%d")) +
                             hit.highlights("content") +
                             "</article></div></ul>")
            else:
                if not results.is_last_page():
                    log_data += "<a href='?q={}&page={}'>Next</a>".format(querystr, page+1)
            if not results:
                log_data = "No Logs found containg: {}".format(
                    htmlescape(querystr))
        request.write(search_page_template.format(log_data=log_data,
                                                  title=self.title,
                                                  header=header,
                                                  footer=footer,
                                                  channel=self.channel))
        request.finish()

    def render_GET(self, request):
        if not request.args or request.args["q"] == ['']:
            return search_page_template.format(log_data="", title=self.title,
                                               header=header, footer=footer,
                                               channel=self.channel)
        d = threads.deferToThread(self._search_logs, request)
        d.addErrback(_onError, request)
        return NOT_DONE_YET
