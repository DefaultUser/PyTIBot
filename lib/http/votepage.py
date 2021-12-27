# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2021>  <Sebastian Schmidt>

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

from twisted.web.template import XMLFile, renderer, tags
from twisted.web.resource import NoResource
from twisted.python.filepath import FilePath
from twisted.enterprise import adbapi
from twisted.logger import Logger

import os
from collections import defaultdict

from .common import PageElement, webpage_error_handler, BaseResource
from lib.channelwatcher.vote import PollListStatusFilter

from util.misc import bytes_to_str
from util import filesystem as fs
from util.formatting import IRCColorCodes, IRCColorsHex, good_contrast_with_black


log = Logger()


class VotePageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/vote_page_template.html")))

    @staticmethod
    def category_style(color):
        if not color:
            return None
        try:
            color_code = IRCColorCodes[color]
            if good_contrast_with_black[color_code]:
                fg = IRCColorCodes.black
            else:
                fg = IRCColorCodes.white
            return "color: {fg};background-color: {bg};".format(
                    fg=IRCColorsHex[fg], bg=IRCColorsHex[color_code])
        except Exception as e:
            log.info("Category has invalid color: {color}: {e}",
                     color=color, e=e)
            return None

    @staticmethod
    def status_style(status):
        if status == "RUNNING":
            return "color: green;"
        if status == "PASSED":
            return "color: green;"
        if status == "TIED":
            return "color: orange;"
        if status == "FAILED":
            return "color: red;"
        if status == "VETOED":
            return "color: red;"
        if status == "CANCELED":
            return "color: red;"
        if status == "DECIDED":
            return "color: darkgreen;"
        return ""

    @renderer
    def category_option(self, request, tag):
        def _inner(categories):
            try:
                requested_category = bytes_to_str(request.args[b"category"][0])
            except:
                requested_category = "ALL"
            yield tag.clone()("ALL", value="ALL")
            for name, color in categories:
                kwargs = {"value": name}
                if requested_category == name:
                    kwargs["selected"] = "selected"
                style = VotePageElement.category_style(color)
                if style:
                    kwargs["style"] = style
                yield tag.clone()(name, **kwargs)

        show_confidential = self.page.has_key(request)
        return self.page.categories(show_confidential=show_confidential).addCallback(_inner)

    @renderer
    def status_option(self, request, tag):
        try:
            requested_status = bytes_to_str(request.args[b"status"][0])
        except:
            requested_status = "ALL"
        for status in [e.name for e in PollListStatusFilter]:
            kwargs = {"value": status}
            if requested_status == status:
                kwargs["selected"] = "selected"
            yield tag.clone()(status, **kwargs)

    @renderer
    def key_option(self, request, tag):
        if not b"key" in request.args:
            return tag()
        return tags.input("", style="display:none;", name="key",
                          value=request.args[b"key"][0])

    @renderer
    def poll_row(self, request, tag):
        return self._poll_row(request, tag, detail_links=True)

    def _poll_row(self, request, tag, detail_links=False):
        def _inner(polls):
            if not polls:
                yield tag(tags.td("No such poll available", colspan="6",
                                  style="text-align:center;font-size:150%;"))
                return
            for (poll_id, category_name, category_color, title, creator, status,
                    veto_reason, vetoed_by, yes, no, abstain, not_voted,
                    active_users) in polls:
                if not category_name:
                    category_name = ""
                category_options = {}
                style = VotePageElement.category_style(category_color)
                if style:
                    category_options["style"] = style
                if status == "RUNNING":
                    not_voted = active_users - yes - no - abstain
                vote_count = [tags.span(str(yes), style="color:green;"), ":",
                              tags.span(str(no), style="color:red;"),
                              tags.span("({} abstained, {} didn't vote)".format(abstain,
                                                                      not_voted))]
                if status == "VETOED":
                    vote_count = "{} (by {})".format(veto_reason, vetoed_by)
                if detail_links:
                    href = "{}/{}".format(bytes_to_str(self.page.crumb), poll_id)
                    if b"key" in request.args:
                        href += "?key=" + bytes_to_str(request.args[b"key"][0])
                    poll_id = tags.a(str(poll_id), href=href)
                else:
                    poll_id = str(poll_id)
                yield tag.clone()(tags.td(poll_id, class_="vote_id"),
                                  tags.td(str(category_name), class_="vote_category",
                                          **category_options),
                                  tags.td(str(title), class_="vote_title"),
                                  tags.td(str(creator), class_="vote_creator"),
                                  tags.td(str(status), class_="vote_status",
                                          style=VotePageElement.status_style(status)),
                                  tags.td(vote_count, class_="vote_count"))

        show_confidential = self.page.has_key(request)
        if b"category" in request.args:
            category = bytes_to_str(request.args[b"category"][0])
        else:
            category = None
        if b"status" in request.args:
            status = PollListStatusFilter[bytes_to_str(request.args[b"status"][0]).upper()]
        else:
            status = PollListStatusFilter.ALL
        return self.page.polls(show_confidential=show_confidential,
                               category=category, status=status).addCallback(_inner)


class VotePage(BaseResource):
    def __init__(self, crumb, config):
        super().__init__(crumb)
        self.channel = config["channel"]
        self.title = config.get("title", "Vote Page")
        self.key = config.get("key", None) # key to show confidential and running polls
        vote_configdir = os.path.join(fs.adirs.user_config_dir, "vote")
        dbfile = os.path.join(vote_configdir,
                              "{}.sqlite".format(self.channel))
        self.dbpool = adbapi.ConnectionPool("sqlite3", dbfile,
                                            check_same_thread=False)

    def has_key(self, request):
        if not self.key:
            return False
        if not b"key" in request.args:
            return False
        supplied_key = bytes_to_str(request.args[b"key"][0])
        return supplied_key == self.key

    def categories(self, show_confidential=False):
        if not show_confidential:
            return self.dbpool.runQuery('SELECT name, color FROM Categories '
                                        'WHERE NOT confidential IS True;')
        return self.dbpool.runQuery('SELECT name, color FROM Categories;')

    def polls(self, poll_id=None, status=PollListStatusFilter.ALL, category=None,
              show_confidential=False):
        filters = []
        values = {}
        if poll_id is not None:
            try:
                values["poll_id"] = int(poll_id)
                filters.append('Polls.id=:poll_id')
            except ValueError as e:
                log.warn("Couldn't filter by poll_id: {e}", e=e)
        if not show_confidential:
            filters.append('NOT Categories.confidential IS True')
            filters.append('Polls.status!="RUNNING"')
        if category and category != "ALL":
            filters.append('Categories.name=:category')
            values["category"] = category
        if status != PollListStatusFilter.ALL:
            if status == PollListStatusFilter.ENDED:
                filters.append('Polls.status!="RUNNING"')
            else:
                filters.append('Polls.status=:status')
                values["status"] = status.name
        if filters:
            where = 'WHERE ' + ' AND '.join(filters) + ' '
        else:
            where = ''
        return self.dbpool.runQuery(
                'SELECT Polls.id, Categories.name, Categories.color, Polls.description, Users.name, Polls.status, '
                       'Polls.veto_reason, (SELECT name FROM Users WHERE Polls.vetoed_by=id), '
                       '(SELECT count() FROM Votes WHERE Polls.id=Votes.poll_id AND Votes.vote="YES"), '
                       '(SELECT count() FROM Votes WHERE Polls.id=Votes.poll_id AND Votes.vote="NO"), '
                       '(SELECT count() FROM Votes WHERE Polls.id=Votes.poll_id AND Votes.vote="ABSTAIN"), '
                       '(SELECT count() FROM Votes WHERE Polls.id=Votes.poll_id AND Votes.vote="NONE"), '
                       '(SELECT count() FROM Users WHERE Users.privilege="USER" OR Users.privilege="ADMIN") '
                'FROM Polls LEFT JOIN Categories ON Polls.category=Categories.id '
                           'LEFT JOIN Users ON Polls.creator=Users.id ' +
                where +
                'ORDER BY Polls.id DESC;', values)

    def element(self):
        return VotePageElement(self)

    def getChild(self, name, request):
        if name == b"":
            # redirect to parent
            return super().getChild(name, request)
        try:
            poll_id = int(name)
        except:
            return NoResource("Invalid PollID supplied")
        try:
            return VoteDetailPage(name, self, poll_id)
        except Exception as e:
            log.warn("Couldn't dispatch to VoteDetailPage: {e}", e=e)
        return super().getChild(name, request)


class VoteDetailPageElement(PageElement):
    loader = XMLFile(FilePath(fs.get_abs_path("resources/vote_detail_page_template.html")))

    _poll_row = VotePageElement._poll_row

    @renderer
    def back(self, request, tag):
        href = request.path + b"/.."
        if b"key" in request.args:
            href += b"?key="+ request.args[b"key"][0]
        return tag("Back", href=href)

    @renderer
    def poll_row(self, request, tag):
        return self._poll_row(request, tag, detail_links=False)

    @renderer
    def vote_row(self, request, tag):
        def _inner(votes):
            for voter, decision, comment in votes:
                decision_kwargs = dict()
                if decision == "YES":
                    decision_kwargs["style"] = "color:green;"
                elif decision =="NO":
                    decision_kwargs["style"] = "color:red;"
                yield tag.clone()(tags.td(voter, class_="vote_user"),
                                  tags.td(decision, class_="vote_decision",
                                          **decision_kwargs),
                                  tags.td(comment or "", class_="vote_comment"))

        show_confidential = self.page.has_key(request)
        return self.page.votes(show_confidential=show_confidential).addCallback(_inner)


class VoteDetailPage(BaseResource):
    def __init__(self, crumb, parent, poll_id):
        super().__init__(crumb)
        self.parent = parent
        self.poll_id = poll_id
        self.title = parent.title + "(#{})".format(poll_id)

    def polls(self, *args, **kwargs):
        kwargs["poll_id"] = self.poll_id
        return self.parent.polls(*args, **kwargs)

    def votes(self, show_confidential=False):
        if show_confidential:
            return self.parent.dbpool.runQuery(
                    'SELECT Users.name, Votes.vote, Votes.comment '
                    'FROM Votes LEFT JOIN Users ON Votes.user=Users.id '
                    'WHERE poll_id=:poll_id;', {"poll_id": self.poll_id})
        return self.parent.dbpool.runQuery(
                'SELECT Users.name, Votes.vote, Votes.comment '
                'FROM Votes LEFT JOIN '
                    '(SELECT Polls.id, Polls.status, Categories.confidential '
                        'FROM Polls LEFT JOIN Categories ON Polls.category=Categories.id) AS TEMP '
                    'on Votes.poll_id=TEMP.id '
                    'LEFT JOIN Users ON Votes.user=Users.id '
                'WHERE TEMP.status!="RUNNING" AND NOT TEMP.confidential IS True '
                'AND Votes.poll_id=:poll_id;',
                {"poll_id": self.poll_id})

    def has_key(self, request):
        return self.parent.has_key(request)

    def element(self):
        return VoteDetailPageElement(self)
