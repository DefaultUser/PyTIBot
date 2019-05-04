# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2016-2020>  <Sebastian Schmidt>

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
from twisted.internet import threads, reactor
from twisted.internet.task import LoopingCall, deferLater
from twisted.logger import Logger
from twisted.web.template import Element, XMLFile, renderer, tags, flatten, Tag
from twisted.python.filepath import FilePath

from whoosh.index import create_in
from whoosh import fields, highlight
from whoosh.qparser import QueryParser

import yaml
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape as htmlescape

from util import log, formatting
from util import filesystem as fs
from util.misc import str_to_bytes, bytes_to_str
from util.internet import webpage_error_handler, BaseResource
from util.whoosh_tag_formatter import WhooshTagFormatter


logger = Logger()


LEVEL_ALL = 10
LEVEL_MOST = 11
LEVEL_IMPORTANT = 16

date_regex = re.compile(r"^(19|20)\d\d[- /.](0[1-9]|1[012])[- /.](0[1-9]|"
                        r"[12][0-9]|3[01])$")


def _prepare_yaml_element(element):
    """Prepare a yaml element for display in html"""
    element["time"] = element["time"][11:]
    if "message" in element:
        element["message"] = formatting.to_tags(element["message"],
                                                link_urls=True)


def add_resources_to_root(root):
    for f in fs.listdir("resources"):
        relpath = "/".join(["resources", f])
        if not (f.endswith(".html") or f.endswith(".inc")):
            root.putChild(str_to_bytes(f), File(fs.get_abs_path(relpath),
                                                defaultType="text/plain"))


class HeaderElement(Element):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/header.inc")))


class FooterElement(Element):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/footer.inc")))


class PageElement(Element):
    def __init__(self, page, *args, **kwargs):
        self.page = page
        super(PageElement, self).__init__(*args, **kwargs)

    @renderer
    def title(self, request, tag):
        return tag(self.page.title)

    @renderer
    def header(self, request, tag):
        yield HeaderElement()

    @renderer
    def footer(self, request, tag):
        yield FooterElement()


class BasePageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/base_page_template.html")))

    @renderer
    def channel_item(self, request, tag):
        for channel in self.page.channels:
            yield tag.clone()(tags.a(channel, href=channel.lstrip("#")))


class BasePage(BaseResource):
    def __init__(self, config):
        super(BasePage, self).__init__()
        self.title = config["HTTPLogServer"].get("title", "PyTIBot Log Server")
        # add channel logs
        self.channels = config["HTTPLogServer"].get("channels", [])
        search_pagelen = config["HTTPLogServer"].get("search_pagelen", 5)
        indexer_procs = config["HTTPLogServer"].get("indexer_procs", 1)
        for channel in self.channels:
            name = channel.lstrip("#")
            self.putChild(str_to_bytes(name),
                          LogPage(name, log.get_channellog_dir(config),
                                  "#{} - {}".format(name, self.title),
                                  search_pagelen, indexer_procs))
        # add resources
        add_resources_to_root(self)

    def element(self):
        return BasePageElement(self)


class LogPageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/log_page_template.html")))
    js = 'window.onload = (function() {{document.getElementById("LevelPicker").value = "{}";}});'

    @staticmethod
    def get_log_level(request):
        MIN_LEVEL = LEVEL_IMPORTANT
        try:
            MIN_LEVEL = int(request.args.get(b"level", [MIN_LEVEL])[0])
        except ValueError as e:
            logger.warn("Got invalid log 'level' in request arguments: "
                        "{lvl}", lvl=request.args[b"level"])
        return MIN_LEVEL

    @staticmethod
    def get_date(request):
        date = bytes_to_str(request.args.get(b"date", [b"current"])[0])
        if date == "current":
            date = datetime.today().strftime("%Y-%m-%d")
        return date

    @renderer
    def date_input(self, request, tag):
        return tag.fillSlots(date=LogPageElement.get_date(request))

    @renderer
    def levelPicker_setter(self, request, tag):
        level = LogPageElement.get_log_level(request)
        return tag(LogPageElement.js.format(level))

    @renderer
    def search_link(self, request, tag):
        return tag.fillSlots(channel=self.page.channel_link())

    @renderer
    def log_row(self, request, tag):
        date = LogPageElement.get_date(request)
        level = LogPageElement.get_log_level(request)
        found = False
        for i, data in enumerate(self.page.log_items(date, level)):
            found = True
            timetag = tags.td(tags.span(id=str(i)),
                              tags.a(data["time"], href="#{}".format(i)),
                              class_="time")
            user = ""
            msg = ""
            if data["levelname"] == "MSG":
                user = data["user"]
                msg = data["message"]
            elif data["levelname"] == "ACTION":
                user = tags.i("*{}".format(data["user"]))
                msg = tags.i(data["data"])
            elif data["levelname"] == "NOTICE":
                user = "[{}".format(data["user"])
                msg = "{}]".format(data["message"])
            elif data["levelname"] == "KICK":
                user = "<--"
                msg = "{kickee} was kicked by {kicker}({message})".format(**data)
            elif data["levelname"] == "QUIT":
                user = "<--"
                msg = "QUIT: {user}({quitMessage})".format(**data)
            elif data["levelname"] == "PART":
                user = "<--"
                msg = "{} left the channel".format(data["user"])
            elif data["levelname"] == "JOIN":
                user = "-->"
                msg = "{} joined the channel".format(data["user"])
            elif data["levelname"] == "NICK":
                user = ""
                msg = "{oldnick} is now known as {newnick}".format(
                    data["oldnick"], data["newnick"])
            elif data["levelname"] == "TOPIC":
                user = ""
                msg = "{user} changed topic to: {topic}".format(
                    data["user"], data["topic"])
            elif data["levelname"] == "ERROR":
                user = tags.span("ERROR", style="color:#ff0000")
                msg = data["msg"]
            usertag = tags.td(user, class_="user")
            datatag = tags.td(msg)
            yield tag.clone()(timetag, usertag, datatag)
        if not found:
            yield tag("Log not found")


class LogPage(BaseResource):
    def __init__(self, channel, log_dir, title, search_pagelen, indexer_procs,
                 singlechannel=False):
        super(LogPage, self).__init__()
        self.channel = channel.lstrip("#")
        self.log_dir = log_dir
        self.title = title
        self.singlechannel = singlechannel
        self.putChild(b"search", SearchPage(self.channel, log_dir, title,
                                            search_pagelen, indexer_procs,
                                            singlechannel=singlechannel))

        if singlechannel:
            add_resources_to_root(self)

    def channel_link(self):
        if self.singlechannel:
            return ""
        return self.channel

    def log_items(self, date, level):
        filename = None
        if date == datetime.today().strftime("%Y-%m-%d"):
            filename = "{}.yaml".format(self.channel)
        elif date_regex.match(date):
            filename = "{}.{}.yaml".format(self.channel, date)
        elif date == "current":
            filename = "{}.yaml".format(self.page.channel)
        if filename and os.path.isfile(os.path.join(self.log_dir, filename)):
            with open(os.path.join(self.log_dir, filename)) as logfile:
                for i, data in enumerate(yaml.full_load_all(logfile)):
                    if data["levelno"] > level:
                        _prepare_yaml_element(data)
                        yield data

    def element(self):
        return LogPageElement(self)


class SearchPageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/search_page_template.html")))

    @renderer
    def channel_page(self, request, tag):
        return tag.fillSlots(channel=self.page.channel_link())

    @renderer
    def search_item(self, request, tag):
        if b"q" not in request.args or request.args[b"q"] == ['']:
            yield tag("")
        else:
            querystr = bytes_to_str(request.args[b"q"][0])
            if b"page" in request.args:
                try:
                    page = int(request.args[b"page"][0])
                except ValueError:
                    page = -1
            else:
                page = 1
            if page < 1:
                yield tag("Invalid page number specified")
            else:
                results = self.page.search_logs(querystr, page)
                if not results["hits"]:
                    yield tag("No Logs found containing: {}".format(querystr))
                for hit in results["hits"]:
                    date = hit["date"].strftime("%Y-%m-%d")
                    href = "{}?date={}".format(self.page.channel_link(), date)
                    yield tag.clone()(tags.div(tags.label(tags.a(date,
                                                                 href=href)),
                                               hit["content"]))
                if not results["last_page"]:
                    yield tag.clone()(tags.a("Next",
                        href="?q={}&page={}".format(querystr, page+1)))


class SearchPage(BaseResource):
    def __init__(self, channel, log_dir, title, pagelen, indexer_procs,
                 singlechannel=False):
        super(SearchPage, self).__init__()
        self.channel = channel
        self.log_dir = log_dir
        self.title = title
        self.last_index_update = 0
        self.pagelen = pagelen
        self.indexer_procs = indexer_procs
        self.singlechannel = singlechannel
        self.ix = None
        threads.deferToThread(self._setup_index)

    def _fields_from_yaml(self, name):
        path = os.path.join(self.log_dir, name)
        with open(path) as f:
            content = []
            for element in yaml.full_load_all(f.read()):
                if element["levelname"] == "MSG":
                    msg = irc.stripFormatting(element["message"])
                    content.append(msg)
            datestr = name.lstrip(self.channel + ".").rstrip(".yaml")
            try:
                date = datetime.strptime(datestr, "%Y-%m-%d")
            except ValueError:
                # default to today
                date = datetime.now()
            # U+2026 is "horizontal ellipsis"
            c = u"\u2026 ".join(content)
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
        ix = create_in(indexpath, schema)
        writer = ix.writer(procs=self.indexer_procs)
        for name in os.listdir(self.log_dir):
            if name.startswith(self.channel + ".") and name.endswith(".yaml"):
                c, date = self._fields_from_yaml(name)
                writer.add_document(path=name, content=c, date=date)
        writer.commit()
        self.last_index_update = time.time()
        self.ix = ix
        lc = LoopingCall(self.update_index)
        reactor.callFromThread(lc.start, 30, now=False)

    def update_index(self):
        with self.ix.searcher() as searcher:
            writer = self.ix.writer(procs=self.indexer_procs)
            indexed_paths = set()
            for field in searcher.all_stored_fields():
                indexed_paths.add(field["path"])
        for name in os.listdir(self.log_dir):
            if name.startswith(self.channel + ".") and name.endswith(".yaml"):
                if name not in indexed_paths:
                    c, date = self._fields_from_yaml(name)
                    writer.add_document(path=name, content=c,
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

    def channel_link(self):
        if self.singlechannel:
            return ".."
        return "/{}".format(self.channel)

    def search_logs(self, querystr, page):
        with self.ix.searcher() as searcher:
            query = QueryParser("content", self.ix.schema).parse(querystr)
            res_page = searcher.search_page(query, page,
                                            pagelen=self.pagelen,
                                            sortedby="date", reverse=True)
            res_page.results.fragmenter = highlight.SentenceFragmenter(
                sentencechars=u".!?\u2026", charlimit=None)
            res_page.results.formatter = WhooshTagFormatter()
            log_data = ""
            res = {"last_page": res_page.is_last_page(), "hits": []}
            for hit in res_page:
                res["hits"].append({"date": hit["date"], "content": hit.highlights("content")})
            return res

    def element(self):
        return SearchPageElement(self)

        if self.ix is None:
            return str_to_bytes(search_page_template.format(
                log_data="Indexing..., Please try again later",
                title=self.title, header=header, footer=footer,
                channel=self.channel_link()))
