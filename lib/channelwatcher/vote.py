# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2020>  <Sebastian Schmidt>

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

from twisted.enterprise import adbapi
from twisted.internet import defer, reactor
from twisted.logger import Logger
from twisted.python import usage
import os
from collections import namedtuple, defaultdict
from datetime import datetime, timedelta, timezone
import dateparser
from enum import Enum
import itertools
import re
from threading import Lock
import textwrap
from inspect import signature, Parameter

from . import abstract
from util import filesystem as fs
from util.decorators import maybe_deferred
from util import formatting
from util.formatting import IRCColorCodes


_INIT_DB_STATEMENTS = ["""
PRAGMA foreign_keys = ON;""",
"""CREATE TABLE IF NOT EXISTS Users (
    id TEXT PRIMARY KEY NOT NULL, -- auth
    name TEXT NOT NULL,
    privilege TEXT NOT NULL CHECK (privilege in ("REVOKED", "USER", "ADMIN"))
);""",
"""CREATE TABLE IF NOT EXISTS Polls (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    creator TEXT NOT NULL,
    vetoed_by TEXT,
    veto_reason TEXT,
    time_start DATETIME DEFAULT (DATETIME('now', 'UTC')), -- always use UTC
    time_end DATETIME DEFAULT (DATETIME('now', 'UTC', '+15 days')), -- always use UTC
    status TEXT CHECK(status in ("RUNNING", "CANCELED", "PASSED", "TIED", "FAILED", "VETOED")) DEFAULT "RUNNING",
    category INTEGER,
    FOREIGN KEY (creator) REFERENCES Users(id),
    FOREIGN KEY (vetoed_by) REFERENCES Users(id),
    FOREIGN KEY (category) REFERENCES Categories(id) ON DELETE SET NULL
);""",
"""CREATE TABLE IF NOT EXISTS Votes (
    poll_id INTEGER,
    user TEXT,
    vote TEXT CHECK(vote in ("NONE", "ABSTAIN", "YES", "NO")),
    comment TEXT,
    -- time_create INTEGER, -- needed?
    PRIMARY KEY (poll_id, user),
    FOREIGN KEY (poll_id) REFERENCES Polls(id),
    FOREIGN KEY (user) REFERENCES Users(id)
    -- TODO: check that user currently has privileges to vote
);""",
"""CREATE TABLE IF NOT EXISTS Categories (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT CHECK(color in ("white", "black", "dark_blue", "dark_green", "red", "dark_red", "dark_magenta", "dark_yellow", "yellow", "green", "dark_cyan", "cyan", "blue", "magenta", "dark_gray", "gray", "")), -- IRC colors
    confidential BOOLEAN DEFAULT false CHECK(confidential in (true, false)) -- only for filtering on website
);"""]


UserPrivilege = Enum("UserPrivilege", "REVOKED USER ADMIN INVALID")
PollStatus = Enum("PollStatus", "RUNNING CANCELED PASSED TIED FAILED VETOED")
VoteDecision = Enum("VoteDecision", "NONE ABSTAIN YES NO")

PollDelayedCalls = namedtuple("PollDelayedCalls", "end_warning end")
VoteCount = namedtuple("VoteCount", "not_voted abstained yes no")

PollListStatusFilter = Enum("PollListStatusFilter", "RUNNING CANCELED PASSED TIED FAILED VETOED ENDED ALL")


IRCHelp = namedtuple("IRCHelp", "subCommands flags params pos_params")


class OptionsWithoutHandlers(usage.Options):
    def _gather_handlers(self):
        return [], '', {}, {}, {}, {}

    @classmethod
    def irc_help(cls):
        subCommands = []
        flags = []
        params = []
        pos_params = []
        for long, short, _, desc in getattr(cls, "subCommands", []):
            long = formatting.colored(long, formatting.IRCColorCodes.cyan)
            if short:
                subCommands.append("{} ({}): {}".format(long, short, desc))
            else:
                subCommands.append("{}: {}".format(long, desc))
        for long, short, desc in getattr(cls, "optFlags", []):
            if short:
                flags.append("--{}, -{}: {}".format(long, short, desc))
            else:
                flags.append("--{}: {}".format(long, desc))
        for parameter in getattr(cls, "optParameters", []):
            long, short, default, desc = parameter[:4]
            if isinstance(default, Enum):
                default = default.name
            if short:
                params.append("--{}=, -{}: {} (default: {})".format(
                    long, short, desc, default))
            else:
                params.append("--{}=: {} (default: {})".format(long, desc, default))
        sig = signature(cls.parseArgs)
        if len(sig.parameters) > 1:
            for p in sig.parameters.values():
                if p.name == "self":
                    continue
                if p.kind == Parameter.VAR_POSITIONAL:
                    pos_params.append("{}...".format(p.name))
                else:
                    pos_params.append(p.name)
        return IRCHelp(subCommands=subCommands, flags=flags, params=params,
                       pos_params=pos_params)


class UserAddOptions(OptionsWithoutHandlers):
    optParameters = [
        ['privilege', 'p', UserPrivilege.USER, "Privilege for the new User (USER|ADMIN)",
            lambda x: UserPrivilege[x.upper()]]
    ]

    def parseArgs(self, name):
        self["user"] = name


class UserModifyOptions(OptionsWithoutHandlers):
    optFlags = [
        ['auth', 'a', "Use auth of the user directly"],
    ]

    def parseArgs(self, user, field, value):
        self["user"] = user
        self["field"] = field
        self["value"] = value

    def postOptions(self):
        if self["field"] not in ["name", "privilege"]:
            raise usage.UsageError("Invalid column name specified")
        if self["field"] == "privilege":
            self["value"] = self["value"].upper()


class UserOptions(OptionsWithoutHandlers):
    subCommands = [
        ['add', None, UserAddOptions, "Add a new user"],
        ['modify', 'mod', UserModifyOptions, "Modify user name or rights"]
    ]


class VoteOptions(OptionsWithoutHandlers):
    optFlags = [
        ['yes', 'y', "autoconfirm changes"],
    ]

    def parseArgs(self, poll_id, decision, *comment):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        try:
            self["decision"] = VoteDecision[decision.upper()]
        except KeyError:
            raise usage.UsageError("Invalid decision specified")
        self["comment"] = " ".join(comment)


class PollCreateOptions(OptionsWithoutHandlers):
    optFlags = [
        ['yes', 'y', "Automatically vote yes"],
        ['no', 'n', "Automatically vote no"],
        ['abstain', 'a', "Automatically abstain"],
    ]
    optParameters = [
        ['category', 'c', None, "Category for the poll"]
    ]

    def parseArgs(self, *description):
        if len(description) < 5:
            raise usage.UsageError("Description is required")
        self["description"] = " ".join(description)

    def postOptions(self):
        if sum([self["yes"], self["no"], self["abstain"]]) >= 2:
            raise usage.UsageError("'yes', 'no' and 'abstain' flags are exclusive")


class PollModifyOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id, field, *value):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["field"] = field
        if not value:
            raise usage.UsageError("No value specified")
        self["value"] = " ".join(value)

    def postOptions(self):
        if self["field"] not in ["category", "description"]:
            raise usage.UsageError("Invalid column specified")
        elif self["field"] == "category":
            if self["value"].lower() in ["none", "null"]:
                self["value"] = None


class PollCancelOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollVetoOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id, *reason):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["reason"] = " ".join(reason)


class PollExpireOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id, *value):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        if not value:
            raise usage.UsageError("No new end time specified")
        self["change"] = " ".join(value) # will be parsed by the command


class PollListOptions(OptionsWithoutHandlers):
    optParameters = [
        ['status', 's', PollListStatusFilter.RUNNING, "Filter with this status",
            lambda x: PollListStatusFilter[x.upper()]],
        ['category', 'c', None, "Filter with this category"]
    ]


class PollInfoOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollOptions(OptionsWithoutHandlers):
    subCommands = [
        ['create', 'call', PollCreateOptions, "Create a new poll"],
        ['modify', 'mod', PollModifyOptions, "Modify a poll"],
        ['cancel', None, PollCancelOptions, "Cancel a poll (vote caller only)"],
        ['veto', None, PollVetoOptions, "Veto a poll (admin only)"],
        ['expire', None, PollExpireOptions,
            "Change Duration of a poll (admin only)"],
        ['list', 'ls', PollListOptions, "List polls"],
        ['info', None, PollInfoOptions, "Info about poll"],
        ['url', None, OptionsWithoutHandlers, "Display address of poll website"]
    ]


class CategoryAddOptions(OptionsWithoutHandlers):
    optFlags = [
        ['confidential', 's', "Hide this category on the website"]
    ]
    optParameters = [
        ['color', 'c', None, "Color for the category"]
    ]

    def parseArgs(self, name, *description):
        self["name"] = name
        self["description"] = " ".join(description)


class CategoryModifyOptions(OptionsWithoutHandlers):
    def parseArgs(self, name, field, *value):
        self["name"] = name
        self["field"] = field
        self["value"] = " ".join(value)

    def postOptions(self):
        if self["field"] not in ["description", "color", "confidential"]:
            raise usage.UsageError("Invalid column name specified")
        if self["field"] == "confidential":
            if self["value"].lower() in ["true", "yes", "1"]:
                self["value"] = True
            elif self["value"].lower() in ["false", "no", "0"]:
                self["value"] = False
            else:
                raise usage.UsageError("Invalid value given")
        elif self["field"] == "color":
            if self["value"].lower() in ["none", "null"]:
                self["value"] = None


class CategoryListOptions(OptionsWithoutHandlers):
    optFlags = [
        ['verbose', 'v', "Verbose output"]
    ]


class CategoryOptions(OptionsWithoutHandlers):
    subCommands = [
        ['add', None, CategoryAddOptions, "Create a new category"],
        ['modify', 'mod', CategoryModifyOptions, "Modify a category"],
        ['list', 'ls', CategoryListOptions, "List categories"]
    ]


class HelpOptions(OptionsWithoutHandlers):
    def parseArgs(self, topic=None):
        self["topic"] = topic


class CommandOptions(OptionsWithoutHandlers):
    subCommands = [
        ['user', None, UserOptions, "Add/modify users"],
        ['vote', None, VoteOptions, "Vote for a poll"],
        ['poll', None, PollOptions, "Create/modify polls"],
        ['category', None, CategoryOptions, "Create/modify categories"],
        ['yes', None, OptionsWithoutHandlers, "Confirm previous action"],
        ['no', None, OptionsWithoutHandlers, "Abort previous action"],
        ['help', None, HelpOptions, "Help: Chain subcommands with '.'"]
    ]


class Vote(abstract.ChannelWatcher):
    logger = Logger()
    PollEndWarningTime = timedelta(days=2)
    PollDefaultDuration = timedelta(days=15)
    expireTimeRegex = re.compile(r"(extend|reduce)\s+(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?$")

    def __init__(self, bot, channel, config):
        super(Vote, self).__init__(bot, channel, config)
        self.prefix = config.get("prefix", "!")
        self.poll_url = config.get("poll_url", None)
        self.http_secret = config.get("http_secret", None)
        vote_configdir = os.path.join(fs.adirs.user_config_dir, "vote")
        os.makedirs(vote_configdir, exist_ok=True)
        dbfile = os.path.join(vote_configdir,
                              "{}.db".format(self.channel.lstrip("#")))
        self.dbpool = adbapi.ConnectionPool("sqlite3", dbfile,
                                            check_same_thread=False)
        self._lock = Lock()
        self._pending_confirmations = {}
        self._num_active_users = 0
        self._poll_delayed_calls = {}
        self._setup()

    @defer.inlineCallbacks
    def _setup(self):
        yield self.dbpool.runInteraction(Vote.initialize_databases)
        self.query_active_user_count()
        self.setup_poll_delayed_calls()

    @staticmethod
    def initialize_databases(cursor):
        for statement in _INIT_DB_STATEMENTS:
            cursor.execute(statement)

    @staticmethod
    def insert_user(cursor, auth, user, privilege):
        cursor.execute('INSERT INTO Users (id, name, privilege) '
                       'VALUES (:auth, :user, :priv);',
                       {"auth": auth, "user": user,
                        "priv": privilege.name})

    @staticmethod
    def update_user_field(cursor, auth, field, value):
        cursor.execute('UPDATE Users '
                       'SET {field}=:value '
                       'WHERE id=:auth;'.format(field=field),
                       {"auth": auth, "value": value})

    @staticmethod
    def insert_poll(cursor, user, description, category):
        cursor.execute('INSERT INTO Polls (description, creator, category) '
                       'VALUES  (:desc, :creator, :category);',
                       {"desc": description, "creator": user, "category": category})

    @staticmethod
    def update_poll_status(cursor, poll_id, status):
        cursor.execute('UPDATE Polls '
                       'SET status=:status '
                       'WHERE id=:id;', {"id": poll_id, "status": status.name})

    @staticmethod
    def update_poll_time_end(cursor, poll_id, time_end):
        timestr = time_end.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('UPDATE Polls '
                       'SET time_end=:time '
                       'WHERE id=:id;', {"id": poll_id, "time": timestr})

    @staticmethod
    def update_poll_veto(cursor, poll_id, vetoed_by, reason):
        cursor.execute('UPDATE Polls '
                       'SET status = "VETOED", vetoed_by = "{vetoed_by}", '
                       'veto_reason = "{reason}" '
                       'WHERE id = "{poll_id}";'.format(poll_id=poll_id,
                                                       vetoed_by=vetoed_by,
                                                       reason=reason))

    @staticmethod
    def update_poll_field(cursor, poll_id, field, value):
        cursor.execute('UPDATE Polls '
                       'SET {field}=:value '
                       'WHERE id=:poll_id;'.format(field=field),
                       {"poll_id": poll_id, "value": value})

    @staticmethod
    def insert_vote(cursor, poll_id, user, decision, comment):
        cursor.execute('INSERT INTO Votes (poll_id, user, vote, comment) '
                       'VALUES (:id, :user, :decision, :comment);',
                       {"id": poll_id, "user": user, "decision": decision.name,
                        "comment": comment})

    @staticmethod
    def update_vote_decision(cursor, poll_id, user, decision, comment):
        cursor.execute('UPDATE Votes '
                       'SET vote=:decision, comment=:comment '
                       'WHERE poll_id=:id AND user=:user;',
                       {"id": poll_id, "user": user, "decision": decision.name,
                        "comment": comment})

    @staticmethod
    def add_not_voted(cursor, poll_id):
        cursor.execute('INSERT OR IGNORE INTO Votes (poll_id, user, vote) '
                       'SELECT {poll_id}, id, "NONE" FROM Users '
                       'WHERE privilege="USER" OR privilege="ADMIN";'.format(
                           poll_id=poll_id)) # don't use sqlite named params here

    @staticmethod
    def insert_category(cursor, name, description, color, confidential):
        cursor.execute('INSERT INTO Categories (name, description, color, confidential) '
                       'VALUES (:name, :description, :color, :confidential);',
                       {"name": name, "description": description, "color": color,
                        "confidential": confidential})

    @staticmethod
    def update_category_field(cursor, name, field, value):
        cursor.execute('UPDATE Categories '
                       'SET {field}=:value '
                       'WHERE name=:name;'.format(field=field),
                       {"name": name, "value": value})

    @staticmethod
    def parse_db_timeentry(time):
        return datetime.strptime(time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    @staticmethod
    def colored_category_name(name, colorname):
        if colorname:
            color = IRCColorCodes[colorname]
            if formatting.good_contrast_with_black[color]:
                fg = IRCColorCodes.black
            else:
                fg = IRCColorCodes.white
            return formatting.colored(name, fg, color, endtoken=True)
        return name

    @defer.inlineCallbacks
    def get_user_privilege(self, name):
        auth = yield self.bot.get_auth(name)
        if not auth:
            Vote.logger.info("User {user} is not authed", user=name)
            return UserPrivilege.INVALID
        privilege = yield self.dbpool.runQuery('SELECT privilege FROM Users '
                                               'WHERE ID=:auth;', {"auth": auth})
        try:
            return UserPrivilege[privilege[0][0]]
        except Exception as e:
            Vote.logger.debug("Error getting user privilege for {user}: {e}",
                              user=name, e=e)
            return UserPrivilege.INVALID

    @defer.inlineCallbacks
    def query_active_user_count(self):
        self._num_active_users = (yield self.dbpool.runQuery(
            'SELECT COUNT() FROM Users '
            'WHERE privilege="ADMIN" OR privilege="USER";'))[0][0]

    @defer.inlineCallbacks
    def setup_poll_delayed_calls(self):
        res = yield self.dbpool.runQuery('SELECT id, time_end FROM Polls '
                                         'WHERE status="RUNNING";')
        for row in res:
            poll_id = int(row[0])
            time_end = Vote.parse_db_timeentry(row[1])
            self._poll_delay_call(poll_id, time_end)

    def _poll_delay_call(self, poll_id, time_end):
        utcnow = datetime.now(tz=timezone.utc)
        if time_end < utcnow:
            # already ended while bot was down
            self.end_poll(poll_id)
            return
        time_warning = time_end - Vote.PollEndWarningTime
        if time_warning > utcnow:
            delta = time_warning - utcnow
            end_warning_call = reactor.callLater(delta.total_seconds(),
                    self.warn_end_poll, poll_id)
        else:
            end_warning_call = None
        delta = time_end - utcnow
        end_call = reactor.callLater(delta.total_seconds(),
                self.end_poll, poll_id)
        if poll_id in self._poll_delayed_calls:
            delayed_calls = self._poll_delayed_calls[poll_id]
            delayed_calls.end.cancel()
            if delayed_calls.end_warning:
                delayed_calls.end_warning.cancel()
        self._poll_delayed_calls[poll_id] = PollDelayedCalls(end=end_call,
                end_warning=end_warning_call)

    def _poll_delayed_call_cancel(self, poll_id):
        try:
            delayed_calls = self._poll_delayed_calls.pop(poll_id)
        except KeyError:
            Vote.logger.warn("Trying to cancel delayed calls for poll #{poll_id}, "
                             "but no delayed calls found", poll_id=poll_id)
            return
        if delayed_calls.end.active():
            delayed_calls.end.cancel()
        if delayed_calls.end_warning and delayed_calls.end_warning.active():
            delayed_calls.end_warning.cancel()

    @defer.inlineCallbacks
    def count_votes(self, poll_id, is_running):
        res = yield self.dbpool.runQuery('SELECT vote, COUNT(vote) FROM Votes '
                                         'WHERE poll_id=:poll_id GROUP BY vote;',
                                         {"poll_id": poll_id})
        if not res:
            return VoteCount(abstained=0, yes=0, no=0, not_voted=self._num_active_users)
        c = defaultdict(int)
        for decision, count in res:
            c[VoteDecision[decision]] = int(count)
        if is_running:
            sum_votes = sum(c.values())
            c[VoteDecision.NONE] += self._num_active_users-sum_votes
        return VoteCount(abstained=c[VoteDecision.ABSTAIN], yes=c[VoteDecision.YES],
                         no=c[VoteDecision.NO], not_voted=c[VoteDecision.NONE])

    @defer.inlineCallbacks
    def warn_end_poll(self, poll_id):
        res = yield self.dbpool.runQuery(
                'SELECT Polls.description, Users.name FROM Polls, Users '
                'WHERE Polls.id=:poll_id AND Polls.creator=Users.id;',
                {"poll_id": poll_id})
        if not res:
            Vote.logger.warn("Poll with id {poll_id} doesn't exist, but delayed call "
                    "was running", poll_id=poll_id)
            return
        desc, creator = res[0]
        vote_count = yield self.count_votes(poll_id, True)
        self.bot.msg(self.channel, "Poll #{poll_id} is running out soon: {desc} "
                "by {creator}: YES:{vote_count.yes} | NO:{vote_count.no} | "
                "ABSTAINED:{vote_count.abstained} | OPEN:{vote_count.not_voted}".format(
                    poll_id=poll_id, desc=textwrap.shorten(desc, 50),
                    creator=creator, vote_count=vote_count))

    @defer.inlineCallbacks
    def end_poll(self, poll_id):
        res = yield self.dbpool.runQuery(
                'SELECT Polls.description, Users.name FROM Polls, Users '
                'WHERE Polls.id=:poll_id AND Polls.creator=Users.id;',
                {"poll_id": poll_id})
        if not res:
            Vote.logger.warn("Poll with id {poll_id} doesn't exist, but delayed call "
                    "was running", poll_id=poll_id)
            return
        desc, creator = res[0]
        vote_count = yield self.count_votes(poll_id, True)
        if vote_count.yes > vote_count.no:
            result = PollStatus.PASSED
        elif vote_count.yes == vote_count.no:
            result = PollStatus.TIED
        else:
            result = PollStatus.FAILED
        self.dbpool.runInteraction(Vote.update_poll_status, poll_id, result)
        self.bot.msg(self.channel, "Poll #{poll_id} {result.name}: {desc} "
                "by {creator}: YES:{vote_count.yes} | NO:{vote_count.no} | "
                "ABSTAINED:{vote_count.abstained} | "
                "NOT VOTED:{vote_count.not_voted}".format(
                    poll_id=poll_id, result=result, desc=textwrap.shorten(desc, 50),
                    creator=creator, vote_count=vote_count))
        # add Vote "NONE" for all active users who haven't voted
        self.dbpool.runInteraction(Vote.add_not_voted, poll_id)

    @defer.inlineCallbacks
    def is_vote_user(self, user):
        return (yield self.get_user_privilege(user)) in (UserPrivilege.ADMIN, UserPrivilege.USER)

    @defer.inlineCallbacks
    def is_vote_admin(self, user):
        return (yield self.get_user_privilege(user))==UserPrivilege.ADMIN

    @defer.inlineCallbacks
    def cmd_user_add(self, issuer, user, privilege):
        is_admin = yield self.bot.is_user_admin(issuer)
        if not (is_admin or (yield self.is_vote_admin(issuer))):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        auth = yield self.bot.get_auth(user)
        if not auth:
            self.bot.notice(issuer, "Couldn't query user's AUTH, aborting...")
            return
        try:
            yield self.dbpool.runInteraction(Vote.insert_user, auth, user,
                                             privilege)
        except Exception as e:
            self.bot.notice(issuer, "Couldn't add user {} ({}). "
                            "Reason: {}".format(user, auth, e))
            Vote.logger.warn("Error adding user {user} ({auth}) to vote "
                             "system for channel {channel}: {error}",
                             user=user, auth=auth, channel=self.channel,
                             error=e)
            return
        self._num_active_users += 1
        self.bot.notice(issuer, "Successfully added User {} ({})".format(user,
                                                                         auth))

    @defer.inlineCallbacks
    def cmd_user_modify(self, issuer, user, field, value, **kwargs):
        is_admin = yield self.bot.is_user_admin(issuer)
        if not (is_admin or (yield self.is_vote_admin(issuer))):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        if kwargs["auth"]:
            auth = user
        else:
            auth = yield self.bot.get_auth(user)
        if not auth:
            self.bot.notice(issuer, "Couldn't query user's AUTH, aborting...")
            return
        entry = yield self.dbpool.runQuery('SELECT * FROM Users '
                                           'WHERE id=:auth;', {"auth": auth})
        if not entry:
            self.bot.notice(issuer, "No such user found in the database")
            return
        try:
            yield self.dbpool.runInteraction(Vote.update_user_field, auth, field,
                                             value)
        except Exception as e:
            self.bot.notice(issuer, "Couldn't modify user {} ({}). "
                            "Reason: {}".format(user, auth, e))
            Vote.logger.warn("Error modifying user {user} ({auth}) for vote "
                             "system for channel {channel}: {error}",
                             user=user, auth=auth, channel=self.channel,
                             error=e)
            return
        # query DB instead of modifying remembered count directly
        # a DB query is required anyways (for the current permissions)
        self.query_active_user_count()
        self.bot.notice(issuer, "Successfully modified User {}".format(user))

    @defer.inlineCallbacks
    def is_poll_running(self, poll_id):
        status = yield self.dbpool.runQuery(
                'SELECT status FROM Polls WHERE id=:id;',
                {"id": poll_id})
        if not status:
            raise KeyError("No poll with id {poll_id} found".format(poll_id=poll_id))
        status = PollStatus[status[0][0]]
        return status == PollStatus.RUNNING

    @defer.inlineCallbacks
    def cmd_poll_create(self, issuer, description, category, **kwargs):
        issuer_auth = yield self.bot.get_auth(issuer)
        if not (yield self.is_vote_user(issuer)):
            self.bot.notice(issuer, "You are not allowed to create votes")
            return
        if category:
            res = yield self.get_category_info(category)
            if not res:
                self.bot.notice(issuer, "Invalid category specified")
                return
            category_id, category_color = res[0]
        else:
            category_id = None
            category_color = None
        with self._lock:
            try:
                yield self.dbpool.runInteraction(Vote.insert_poll, issuer_auth,
                                                 description, category_id)
            except Exception as e:
                self.bot.msg(self.channel, "Could not create new poll")
                Vote.logger.warn("Error inserting poll into DB: {error}",
                                 error=e)
                return
            poll_id = yield self.dbpool.runQuery('SELECT MAX(id) FROM Polls;')
            poll_id = poll_id[0][0]
            if category:
                category_str = Vote.colored_category_name(category, category_color) + " "
            else:
                category_str = ""
            self.bot.msg(self.channel, "{category}New poll #{poll_id} by {user}({url}): "
                         "{description}".format(poll_id=poll_id, user=issuer,
                                                url="URL TODO",
                                                description=description,
                                                category=category_str))
        self._poll_delay_call(poll_id, datetime.now(tz=timezone.utc) + Vote.PollDefaultDuration)
        if kwargs["yes"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.YES, "")
        elif kwargs["no"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.NO, "")
        elif kwargs["abstain"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.ABSTAIN, "")

    @defer.inlineCallbacks
    def cmd_poll_modify(self, issuer, poll_id, field, value):
        if not(yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "You are not allowed to modify votes")
            return
        try:
            if not(yield self.is_poll_running(poll_id)):
                self.bot.notice(issuer, "Poll isn't running")
                return
        except KeyError:
            self.bot.notice(issuer, "Poll doesn't exist")
            return
        if field == "category" and value:
            res = yield self.get_category_info(value)
            if not res:
                self.bot.notice(issuer, "No such category")
                return
            value = res[0][0]
        try:
            yield self.dbpool.runInteraction(Vote.update_poll_field, poll_id,
                                             field, value)
        except Exception as e:
            Vote.logger.warn("")
            self.bot.notice(issuer, "Couldn't modify poll ({})".format(e))
            return
        self.bot.notice(issuer, "Successfully modified poll")

    @defer.inlineCallbacks
    def cmd_poll_veto(self, issuer, poll_id, reason):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only admins can VETO polls")
            return
        issuer_auth = yield self.bot.get_auth(issuer)
        with self._lock: # TODO: is this needed?
            try:
                if not(yield self.is_poll_running(poll_id)):
                    self.bot.notice(issuer, "Poll isn't running")
                    return
            except KeyError:
                self.bot.notice(issuer, "Poll doesn't exist")
                return
            try:
                # TODO: confirmation?
                yield self.dbpool.runInteraction(Vote.update_poll_veto, poll_id,
                                                 issuer_auth, reason)
            except Exception as e:
                self.bot.notice(issuer, "Error vetoing poll, contact the "
                                "admin")
                Vote.logger.warn("Error vetoing poll #{id}: {error}",
                                 id=poll_id, error=e)
                return
            self.bot.msg(self.channel, "Poll #{} vetoed".format(poll_id))
        self._poll_delayed_call_cancel(poll_id)

    @defer.inlineCallbacks
    def cmd_poll_cancel(self, issuer, poll_id):
        with self._lock: # TODO: needed?
            temp = yield self.dbpool.runQuery(
                    'SELECT creator, status FROM Polls '
                    'WHERE id=:id;', {"id": poll_id})
            if not temp:
                self.bot.notice(issuer, "No Poll with given ID found, "
                                "aborting...")
                return
            poll_creator, status = temp[0]
            status = PollStatus[status]
            issuer_auth = yield self.bot.get_auth(issuer)
            if poll_creator.casefold() != issuer_auth.casefold():
                self.bot.notice(issuer, "Only the creator of a poll can "
                                "cancel it")
                return
            if status != PollStatus.RUNNING:
                self.bot.notice(issuer, "Poll #{} isn't running ({})".format(
                    poll_id, status.name))
                return
            try:
                yield self.dbpool.runInteraction(Vote.update_poll_status, poll_id,
                                                 PollStatus.CANCELED)
            except Exception as e:
                self.bot.notice(issuer, "Error cancelling poll, contact the "
                                "admin")
                Vote.logger.warn("Error cancelling poll #{id}: {error}",
                                 id=poll_id, error=e)
                return
            self.bot.msg(self.channel, "Poll #{} cancelled".format(poll_id))
        self._poll_delayed_call_cancel(poll_id)

    @defer.inlineCallbacks
    def cmd_poll_expire(self, issuer, poll_id, change):
        res = yield self.dbpool.runQuery('SELECT status, time_end FROM Polls '
                                         'WHERE id=:id;', {"id": poll_id})
        if not res:
            self.bot.notice(issuer, "Poll #{} doesn't exist".format(poll_id))
            return
        status = PollStatus[res[0][0]]
        current_time_end = res[0][1]
        if status != PollStatus.RUNNING:
            self.bot.notice(issuer, "Poll #{} isn't running".format(poll_id))
            return
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only admins can change poll duration")
            return
        utcnow = datetime.now(tz=timezone.utc)
        match = Vote.expireTimeRegex.match(change)
        if match:
            days = match.group(2) or 0
            hours = match.group(3) or 0
            delta = timedelta(days=int(days), hours=int(hours))
            if match.group(1) == "reduce":
                delta *= -1
            time_end = Vote.parse_db_timeentry(current_time_end) + delta
        else:
            time_end = dateparser.parse(change).astimezone(timezone.utc)
            if time_end is None:
                self.bot.notice(issuer, "Invalid new end time specified")
                return
        issuer_id = yield self.bot.get_auth(issuer)
        confirmation = yield self.require_confirmation(issuer, issuer_id,
                "Please confirm new expiration date {}".format(time_end.isoformat()))
        if not confirmation:
            return
        self._poll_delayed_call_cancel(poll_id)
        if time_end <= utcnow:
            self.end_poll(poll_id)
            time_end = utcnow
        else:
            self._poll_delay_call(poll_id, time_end)
            self.bot.msg(self.channel, "Poll #{} will end at {}".format(
                poll_id, time_end.isoformat()))
        self.dbpool.runInteraction(Vote.update_poll_time_end, poll_id,
                                   time_end)

    @defer.inlineCallbacks
    def cmd_poll_list(self, issuer, status, category):
        if status == PollListStatusFilter.ENDED:
            statusfilter = 'NOT Polls.status="RUNNING"'
        elif status == PollListStatusFilter.ALL:
            statusfilter = ''
        else:
            statusfilter = 'Polls.status=:status'
        if not category or category=="all":
            categoryfilter = ''
        else:
            categoryfilter = 'Categories.name=:category'
        where = ''
        if statusfilter:
            where = 'WHERE ' + statusfilter
        if categoryfilter:
            if where:
                where += ' AND ' + categoryfilter
            else:
                where = 'WHERE ' + categoryfilter
        result = yield self.dbpool.runQuery(
                'SELECT Polls.id, Polls.status, Polls.description, Users.name, Categories.name, Categories.color '
                'FROM Polls LEFT JOIN Categories ON Polls.category=Categories.id '
                           'LEFT JOIN Users ON Polls.creator=Users.id ' +
                where + ' ORDER BY Polls.id DESC;', {"status": status.name, "category": category})
        if not result:
            self.bot.notice(issuer, "No Polls found")
            return
        issuer_id = yield self.bot.get_auth(issuer)
        if not issuer_id:
            issuer_id = issuer
        for i, (poll_id, poll_status, desc, creator, category, color) in enumerate(result):
            if (i!=0 and i%5==0):
                confirm = yield self.require_confirmation(issuer, issuer_id,
                        "Continue? (confirm with {prefix}yes)".format(
                            prefix=self.prefix))
                if not confirm:
                    return
            if category:
                category_str = Vote.colored_category_name(category, color) + " "
            else:
                category_str = ""
            self.bot.notice(issuer, "{category}#{poll_id} by {creator} ({status}): "
                            "{description}".format(poll_id=poll_id, creator=creator,
                                                   status=poll_status,
                                                   description=textwrap.shorten(desc, 50),
                                                   category=category_str))

    @defer.inlineCallbacks
    def cmd_poll_info(self, issuer, poll_id):
        result = yield self.dbpool.runQuery(
                'SELECT Polls.status, Polls.description, Users.name, Categories.name, Categories.color '
                'FROM Polls LEFT JOIN Categories ON Polls.category=Categories.id '
                           'LEFT JOIN Users ON Polls.creator=Users.id '
                'WHERE Polls.id=:poll_id;', {"poll_id": poll_id})
        if not result:
            self.bot.notice(issuer, "No Poll with ID #{} found".format(poll_id))
            return
        status, desc, creator, category, color = result[0]
        status = PollStatus[status]
        if category:
            category_str = Vote.colored_category_name(category, color) + " "
        else:
            category_str = ""
        vote_count = yield self.count_votes(poll_id, status==PollStatus.RUNNING)
        self.bot.notice(issuer, "{category}Poll #{poll_id} by {creator} {status.name}: {desc}: "
                "YES:{vote_count.yes} | NO:{vote_count.no} | "
                "ABSTAINED:{vote_count.abstained} | NOT VOTED:{vote_count.not_voted}".format(
                    poll_id=poll_id, status=status, desc=textwrap.shorten(desc, 50),
                    creator=creator, vote_count=vote_count,
                    category=category_str))

    def cmd_poll_url(self, issuer):
        if self.poll_url is None:
            url = "N/A"
        else:
            if self.http_secret is None:
                url = self.poll_url
            else:
                url = self.poll_url + "?key=" + self.http_secret
        self.bot.notice(issuer, url)

    def get_category_info(self, category_name):
        return self.dbpool.runQuery('SELECT id, color FROM Categories '
                                    'WHERE name=:name;',
                                    {"name": category_name})

    @defer.inlineCallbacks
    def cmd_category_add(self, issuer, name, description, color, confidential):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only Admins can add categories")
            return
        try:
            yield self.dbpool.runInteraction(Vote.insert_category, name, description,
                                             color or "", confidential!=0)
        except Exception as e:
            Vote.logger.info("Failed to add category: {error}", error=e)
            self.bot.notice(issuer, "Failed to add category: {}".format(e))
            return
        self.bot.msg(self.channel, "Added category {}".format(
            Vote.colored_category_name(name, color)))

    @defer.inlineCallbacks
    def cmd_category_modify(self, issuer, name, field, value):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only Admins can modify categories")
            return
        res = yield self.dbpool.runQuery('SELECT id FROM Categories '
                                         'WHERE name=:name;', {"name": name})
        if not res:
            self.bot.notice(issuer, "Category {} not found".format(name))
            return
        try:
            yield self.dbpool.runInteraction(Vote.update_category_field, name,
                                             field, value)
        except Exception as e:
            Vote.logger.info("Failed to modify category: {error}", error=e)
            self.bot.notice(issuer, "Failed to modify category: {}".format(e))
            return
        self.bot.notice(issuer, "Successfully modified category")

    @defer.inlineCallbacks
    def cmd_category_list(self, issuer, verbose):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        res = yield self.dbpool.runQuery(
                'SELECT name, description, color, confidential FROM Categories;')
        self.bot.notice(issuer, "There are {} categories (confidential marked "
                        "with *)".format(len(res)))
        if verbose:
            issuer_id = yield self.bot.get_auth(issuer)
            for i, (name, desc, color, confidential) in enumerate(res):
                if (i!=0 and i%5==0):
                    confirm = yield self.require_confirmation(issuer, issuer_id,
                            "Continue? (confirm with {prefix}yes)".format(
                                prefix=self.prefix))
                    if not confirm:
                        return
                self.bot.notice(issuer, "{}{}: {}".format("*" if confidential else " ",
                                                          Vote.colored_category_name(name, color),
                                                          desc or "No description"))
        else:
            self.bot.notice(issuer, ", ".join(
                itertools.starmap(lambda n, _, c, s: "{}{}".format(
                                    "*" if s else "", Vote.colored_category_name(n, c)),
                                  res)))

    @defer.inlineCallbacks
    def cmd_vote(self, voter, poll_id, decision, comment, **kwargs):
        if not (yield self.is_vote_user(voter)):
            self.bot.notice(voter, "You are not allowed to vote")
            return
        voterid = yield self.bot.get_auth(voter)
        pollstatus = yield self.dbpool.runQuery(
                'SELECT status FROM Polls WHERE id=:id;', {"id": poll_id})
        if not pollstatus:
            self.bot.notice(voter, "Poll #{} doesn't exist".format(poll_id))
            return
        pollstatus = PollStatus[pollstatus[0][0]]
        if pollstatus != PollStatus.RUNNING:
            self.bot.notice(voter, "Poll #{} is not running ({})".format(poll_id,
                pollstatus.name))
            return
        try:
            query = yield self.dbpool.runQuery(
                    'SELECT vote, comment FROM Votes '
                    'WHERE poll_id=:poll_id AND user=:voter;',
                    {"poll_id": poll_id, "voterid": voterid})
            if query:
                previous_decision = VoteDecision[query[0][0]]
                previous_comment = query[0][1]
                # require confirmation
                if kwargs['yes']:
                    confirmed = True
                else:
                    confirmed = yield self.require_confirmation(voter, voterid,
                            "You already voted for this poll "
                            "({vote}: {comment}), please confirm with "
                            "'{prefix}yes' or '{prefix}no".format(
                                vote=previous_decision.name,
                                comment=textwrap.shorten(previous_comment,
                                                         50) or "No comment",
                                prefix=self.prefix))
                if not confirmed:
                    return
                self.dbpool.runInteraction(Vote.update_vote_decision,
                                           poll_id, voterid, decision,
                                           comment)
                self.bot.msg(self.channel, "{} changed vote from {} "
                             "to {} for poll #{}: {}".format(voter,
                                 previous_decision.name, decision.name,
                                 poll_id, textwrap.shorten(comment, 50)
                                 or "No comment given"))
            else:
                yield self.dbpool.runInteraction(Vote.insert_vote, poll_id,
                                                 voterid, decision, comment)
                self.bot.msg(self.channel,
                             "{} voted {} for poll #{}: {}".format(voter,
                                 decision.name, poll_id,
                                 textwrap.shorten(comment, 50) or "No comment given"))
        except Exception as e:
            Vote.logger.warn("Encountered error during vote: {}".format(e))
        vote_count = yield self.count_votes(poll_id, True)
        if abs(vote_count.yes - vote_count.no) > vote_count.not_voted:
            self._poll_delayed_call_cancel(poll_id)
            self.end_poll(poll_id)

    @maybe_deferred
    def require_confirmation(self, user, userid, message):
        if userid in self._pending_confirmations:
            self.bot.notice(user, "Another confirmation is already "
                            "pending")
            return False
        self.bot.notice(user, message)
        d = defer.Deferred()
        def onTimeout(*args):
            self.bot.notice(user, "Confirmation timed out")
            d.callback(False)
        d.addTimeout(60, reactor, onTimeoutCancel=onTimeout)
        d.addBoth(self._confirmation_finalize, userid)
        self._pending_confirmations[userid] = d
        return d

    def _confirmation_finalize(self, result, userid):
        self._pending_confirmations.pop(userid)
        return result

    def cmd_yes(self, issuer):
        self.confirm_command(issuer, True)

    def cmd_no(self, issuer):
        self.confirm_command(issuer, False)

    @defer.inlineCallbacks
    def confirm_command(self, issuer, decision):
        userid = yield self.bot.get_auth(issuer)
        if not userid in self._pending_confirmations:
            self.bot.notice(issuer, "Nothing to confirm")
            return
        self._pending_confirmations[userid].callback(decision)

    def cmd_help(self, user, topic):
        def get_subOption(option_class, subCommand):
            for long, short, option, desc in option_class.subCommands:
                if subCommand==long or subCommand==short:
                    return option, desc
            raise KeyError("No such subcommand")

        option_class = CommandOptions
        desc = "Vote module"
        if topic:
            for frag in topic.split("."):
                try:
                    option_class, desc = get_subOption(option_class, frag)
                except Exception as e:
                    self.bot.notice(user, formatting.colored(
                        "No such command: "+topic,
                        formatting.IRCColorCodes.red))
                    return

        sig = option_class.irc_help()
        if sig.subCommands:
            self.bot.notice(user, "{}: {}".format(
                formatting.colored("Available commands",
                                   formatting.IRCColorCodes.blue),
                ", ".join(sig.subCommands)))
            return
        self.bot.notice(user, desc)
        if sig.flags:
            self.bot.notice(user, "{}: {}".format(
                formatting.colored("Flags", formatting.IRCColorCodes.yellow),
                ", ".join(sig.flags)))
        if sig.params:
            self.bot.notice(user, "{}: {}".format(
                formatting.colored("Optional parameters",
                                   formatting.IRCColorCodes.yellow),
                ", ".join(sig.params)))
        if sig.pos_params:
            self.bot.notice(user, "{}: {}".format(
                formatting.colored("Positional parameters",
                                   formatting.IRCColorCodes.green),
                ", ".join(sig.pos_params)))

    def topic(self, user, topic):
        pass

    def nick(self, oldnick, newnick):
        pass

    @defer.inlineCallbacks
    def join(self, user):
        if not (yield self.is_vote_user(user)):
            return
        result = yield self.dbpool.runQuery(
                'SELECT id FROM Polls WHERE status="RUNNING";')
        if not result:
            return
        num_running_polls = len(result)
        poll_id_list = set(itertools.chain(*result))
        user_id = yield self.bot.get_auth(user)
        result = yield self.dbpool.runQuery('SELECT poll_id FROM Votes '
                'WHERE user=:user_id AND poll_id IN ({poll_ids});'.format(
                    poll_ids=",".join(map(str, poll_id_list))),
                {"user_id": user_id})
        if not result:
            num_already_voted = 0
        else:
            num_already_voted = len(result)
        remaining = num_running_polls - num_already_voted
        if remaining:
            not_voted = sorted(set(poll_id_list) - set(itertools.chain(*result)))
            self.bot.notice(user, "There are {} open polls without your "
                            "vote ({})".format(remaining, ", ".join(
                                map(str, not_voted))))

    def part(self, user):
        pass

    def quit(self, user, quitMessage):
        pass

    def kick(self, kickee, kicker, message):
        pass

    def notice(self, user, message):
        pass

    def action(self, user, data):
        pass

    def msg(self, user, message):
        if not message.startswith(self.prefix):
            return
        tokens = message.lstrip(self.prefix).split()
        options = CommandOptions()
        try:
            options.parseOptions(tokens)
        except usage.UsageError as e:
            self.bot.notice(user, str(e))
            return
        command = options.subCommand
        if options.subOptions.subCommand:
            commandstr = "cmd_" + command + "_" + options.subOptions.subCommand
            subOptions = options.subOptions.subOptions
        else:
            commandstr = "cmd_" + str(command)
            subOptions = options.subOptions
        try:
            getattr(self, commandstr)(user, **subOptions)
        except Exception as e:
            Vote.logger.info("Error while executing vote command: {error!r}",
                             error=e)

    def connectionLost(self, reason):
        pass
