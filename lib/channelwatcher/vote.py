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

from . import abstract
from util import filesystem as fs
from util.decorators import maybe_deferred


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
    FOREIGN KEY (creator) REFERENCES Users(id),
    FOREIGN KEY (vetoed_by) REFERENCES Users(id)
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
);"""]


UserPrivilege = Enum("UserPrivilege", "REVOKED USER ADMIN INVALID")
PollStatus = Enum("PollStatus", "RUNNING CANCELED PASSED TIED FAILED VETOED")
VoteDecision = Enum("VoteDecision", "NONE ABSTAIN YES NO")

PollDelayedCalls = namedtuple("PollDelayedCalls", "end_warning end")
VoteCount = namedtuple("VoteCount", "not_voted abstained yes no")

PollListStatusFilter = Enum("PollListStatusFilter", "RUNNING ENDED ALL")


class OptionsWithoutHandlers(usage.Options):
    def _gather_handlers(self):
        return [], '', {}, {}, {}, {}


class UserAddOptions(OptionsWithoutHandlers):
    def parseArgs(self, name, privilege=None):
        self["user"] = name
        if privilege:
            try:
                self["privilege"] = UserPrivilege[privilege.upper()]
            except KeyError:
                raise usage.UsageError("Invalid privilege specified")
        else:
            self["privilege"] = UserPrivilege.USER


class UserModifyOptions(OptionsWithoutHandlers):
    optFlags = [
        ['auth', 'a', "Use auth of the user directly"],
    ]

    def parseArgs(self, name, privilege):
        self["user"] = name
        try:
            self["privilege"] = UserPrivilege[privilege.upper()]
        except KeyError:
            raise usage.UsageError("Invalid privilege specified")


class UserOptions(OptionsWithoutHandlers):
    subCommands = [
        ['add', None, UserAddOptions, "Add a new user"],
        ['modify', 'mod', UserModifyOptions, "Modify user rights"]
    ]


class VoteOptions(OptionsWithoutHandlers):
    optFlags = [
        ['yes', 'y', "autoconfirm changes"],
    ]

    def parseArgs(self, poll_id, decision, *args):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        try:
            self["decision"] = VoteDecision[decision.upper()]
        except KeyError:
            raise usage.UsageError("Invalid decision specified")
        self["comment"] = " ".join(args)


class PollCreateOptions(OptionsWithoutHandlers):
    optFlags = [
        ['yes', 'y', "Automatically vote yes"],
        ['no', 'n', "Automatically vote no"],
        ['abstain', 'a', "Automatically abstain"],
    ]

    def parseArgs(self, *args):
        if len(args) < 5:
            raise usage.UsageError("Description is required")
        self["description"] = " ".join(args)

    def postOptions(self):
        if sum([self["yes"], self["no"], self["abstain"]]) >= 2:
            raise usage.UsageError("'yes', 'no' and 'abstain' flags are exclusive")


class PollCancelOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollVetoOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id, *args):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["reason"] = " ".join(args)


class PollExpireOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id, *args):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        if not args:
            raise usage.UsageError("No new end time specified")
        self["change"] = " ".join(args) # will be parsed by the command


class PollListOptions(OptionsWithoutHandlers):
    optParameters = [
        ['status', 's', PollListStatusFilter.RUNNING, "Filter with this status",
            lambda x: PollListStatusFilter[x.upper()]],
    ]


class PollOptions(OptionsWithoutHandlers):
    subCommands = [
        ['create', 'call', PollCreateOptions, "Create a new poll"],
        ['cancel', None, PollCancelOptions, "Cancel a poll (vote caller only)"],
        ['veto', None, PollVetoOptions, "Veto a poll (admin only)"],
        ['expire', None, PollExpireOptions,
            "Change Duration of a poll (admin only)"],
        ['list', 'ls', PollListOptions, "List polls"],
        ['url', None, OptionsWithoutHandlers, "Display address of poll website"]
    ]


class HelpOptions(OptionsWithoutHandlers):
    def parseArgs(self, topic=None):
        self.topic = topic


class CommandOptions(OptionsWithoutHandlers):
    subCommands = [
        ['user', None, UserOptions, "Add/modify users"],
        ['vote', None, VoteOptions, "Vote for a poll"],
        ['poll', None, PollOptions, "Create/modify polls"],
        ['yes', None, OptionsWithoutHandlers, "Confirm previous action"],
        ['no', None, OptionsWithoutHandlers, "Abort previous action"],
        ['help', None, HelpOptions, "help"]
    ]


class Vote(abstract.ChannelWatcher):
    logger = Logger()
    PollEndWarningTime = timedelta(days=2)
    PollDefaultDuration = timedelta(days=15)
    expireTimeRegex = re.compile(r"(extend|reduce)\s+(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?$")

    def __init__(self, bot, channel, config):
        super(Vote, self).__init__(bot, channel, config)
        self.prefix = config.get("prefix", "!")
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
                       'VALUES ("{}", "{}", "{}");'.format(auth, user,
                                                           privilege.name))

    @staticmethod
    def update_user(cursor, auth, privilege):
        cursor.execute('UPDATE Users '
                       'SET privilege = "{privilege}" '
                       'WHERE id = "{auth}";'.format(auth=auth,
                                                     privilege=privilege.name))

    @staticmethod
    def insert_poll(cursor, user, description):
        cursor.execute('INSERT INTO Polls (description, creator) '
                       'VALUES  ("{}", "{}");'.format(description, user))

    @staticmethod
    def update_pollstatus(cursor, poll_id, status):
        cursor.execute('UPDATE Polls '
                       'SET status = "{status}" '
                       'WHERE id = "{poll_id}";'.format(poll_id=poll_id,
                                                       status=status.name))

    @staticmethod
    def update_poll_time_end(cursor, poll_id, time_end):
        timestr = time_end.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('UPDATE Polls '
                       'SET time_end = "{time}" '
                       'WHERE id = "{poll_id}";'.format(poll_id=poll_id,
                                                        time=timestr))

    @staticmethod
    def update_poll_veto(cursor, poll_id, vetoed_by, reason):
        cursor.execute('UPDATE Polls '
                       'SET status = "VETOED", vetoed_by = "{vetoed_by}", '
                       'veto_reason = "{reason}" '
                       'WHERE id = "{poll_id}";'.format(poll_id=poll_id,
                                                       vetoed_by=vetoed_by,
                                                       reason=reason))

    @staticmethod
    def insert_voteresult(cursor, poll_id, user, decision, comment):
        cursor.execute('INSERT INTO Votes (poll_id, user, vote, comment) '
                       'VALUES ("{}", "{}", "{}", "{}");'.format(poll_id, user,
                                                                 decision.name,
                                                                 comment))

    @staticmethod
    def update_votedecision(cursor, poll_id, user, decision, comment):
        cursor.execute('UPDATE Votes '
                       'SET vote = "{decision}", comment = "{comment}" '
                       'WHERE poll_id = "{poll_id}" '
                       'AND user = "{user}";'.format(poll_id=poll_id, user=user,
                                                     decision=decision.name,
                                                     comment=comment))

    @staticmethod
    def add_not_voted(cursor, poll_id):
        cursor.execute('INSERT OR IGNORE INTO Votes (poll_id, user, vote) '
                       'SELECT {poll_id}, id, "NONE" FROM Users '
                       'WHERE privilege="USER" OR privilege="ADMIN";'.format(
                           poll_id=poll_id))

    @staticmethod
    def parse_db_timeentry(time):
        return datetime.strptime(time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    @defer.inlineCallbacks
    def get_user_privilege(self, name):
        auth = yield self.bot.get_auth(name)
        if not auth:
            Vote.logger.info("User {user} is not authed", user=name)
            return UserPrivilege.INVALID
        privilege = yield self.dbpool.runQuery('SELECT privilege FROM Users '
                                               'WHERE ID = "{}"'.format(auth))
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
        delayed_calls.end.cancel()
        if delayed_calls.end_warning:
            delayed_calls.end_warning.cancel()

    @defer.inlineCallbacks
    def count_votes(self, poll_id):
        res = yield self.dbpool.runQuery('SELECT vote, COUNT(vote) FROM Votes '
                'WHERE poll_id="{}" GROUP BY vote;'.format(poll_id))
        if not res:
            return VoteCount(abstained=0, yes=0, no=0, not_voted=self._num_active_users)
        c = defaultdict(int)
        for decision, count in res:
            c[VoteDecision[decision]] = int(count)
        sum_votes = sum(c.values())
        return VoteCount(abstained=c[VoteDecision.ABSTAIN], yes=c[VoteDecision.YES],
                         no=c[VoteDecision.NO], not_voted=self._num_active_users-sum_votes)

    @defer.inlineCallbacks
    def warn_end_poll(self, poll_id):
        res = yield self.dbpool.runQuery('SELECT description, creator FROM Polls '
            'WHERE id="{}";'.format(poll_id))
        if not res:
            Vote.logger.warn("Poll with id {poll_id} doesn't exist, but delayed call "
                    "was running", poll_id=poll_id)
            return
        desc, creator = res[0]
        vote_count = yield self.count_votes(poll_id)
        self.bot.msg(self.channel, "Poll #{poll_id} is running out soon: {desc} "
                "by {creator}: YES:{vote_count.yes} | NO:{vote_count.no} | "
                "ABSTAINED:{vote_count.abstained} | OPEN:{vote_count.not_voted}".format(
                    poll_id=poll_id, desc=textwrap.shorten(desc, 50),
                    creator=creator, vote_count=vote_count))

    @defer.inlineCallbacks
    def end_poll(self, poll_id):
        res = yield self.dbpool.runQuery('SELECT description, creator FROM Polls '
            'WHERE id="{}";'.format(poll_id))
        if not res:
            Vote.logger.warn("Poll with id {poll_id} doesn't exist, but delayed call "
                    "was running", poll_id=poll_id)
            return
        desc, creator = res[0]
        vote_count = yield self.count_votes(poll_id)
        if vote_count.yes > vote_count.no:
            result = PollStatus.PASSED
        elif vote_count.yes == vote_count.no:
            result = PollStatus.TIED
        else:
            result = PollStatus.FAILED
        self.dbpool.runInteraction(Vote.update_pollstatus, poll_id, result)
        self.bot.msg(self.channel, "Poll #{poll_id} {result.name}: {desc} "
                "by {creator}: YES:{vote_count.yes} | NO:{vote_count.no} | "
                "ABSTAINED:{vote_count.abstained} | "
                "NOT VOTED:{vote_count.not_voted}".format(
                    poll_id=poll_id, result=result, desc=textwrap.shorten(desc, 50),
                    creator=creator, vote_count=vote_count))
        # add Vote "NONE" for all active users who haven't voted
        self.dbpool.runInteraction(Vote.add_not_voted, poll_id)

    @defer.inlineCallbacks
    def cmd_user_add(self, issuer, user, privilege):
        is_admin = yield self.bot.is_user_admin(issuer)
        issuer_privilege = yield self.get_user_privilege(issuer)
        if not (is_admin or issuer_privilege == UserPrivilege.ADMIN):
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
    def cmd_user_modify(self, issuer, user, privilege, **kwargs):
        is_admin = yield self.bot.is_user_admin(issuer)
        issuer_privilege = yield self.get_user_privilege(issuer)
        if not (is_admin or issuer_privilege == UserPrivilege.ADMIN):
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
                                           'WHERE id = "{}";'.format(auth))
        if not entry:
            self.bot.notice(issuer, "No such user found in the database")
            return
        try:
            yield self.dbpool.runInteraction(Vote.update_user, auth,
                                             privilege)
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
    def cmd_poll_create(self, issuer, description, **kwargs):
        privilege = yield self.get_user_privilege(issuer)
        issuer_auth = yield self.bot.get_auth(issuer)
        if privilege not in [UserPrivilege.USER, UserPrivilege.ADMIN]:
            self.bot.notice(issuer, "You are not allowed to create votes")
            return
        with self._lock:
            try:
                yield self.dbpool.runInteraction(Vote.insert_poll, issuer_auth,
                                                 description)
            except Exception as e:
                self.bot.msg(self.channel, "Could not create new poll")
                Vote.logger.warn("Error inserting poll into DB: {error}",
                                 error=e)
                return
            poll_id = yield self.dbpool.runQuery('SELECT MAX(id) FROM Polls')
            poll_id = poll_id[0][0]
            self.bot.msg(self.channel, "New poll #{poll_id} by {user}({url}): "
                         "{description}".format(poll_id=poll_id, user=issuer,
                                                url="URL TODO",
                                                description=description))
        self._poll_delay_call(poll_id, datetime.now(tz=timezone.utc) + Vote.PollDefaultDuration)
        if kwargs["yes"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.YES, "")
        elif kwargs["no"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.NO, "")
        elif kwargs["abstain"]:
            self.cmd_vote(issuer, poll_id, VoteDecision.ABSTAIN, "")

    @defer.inlineCallbacks
    def cmd_poll_veto(self, issuer, poll_id, reason):
        issuer_privilege = yield self.get_user_privilege(issuer)
        if issuer_privilege != UserPrivilege.ADMIN:
            self.bot.notice(issuer, "Only admins can VETO polls")
            return
        issuer_auth = yield self.bot.get_auth(issuer)
        with self._lock: # TODO: is this needed?
            status = yield self.dbpool.runQuery(
                    'SELECT status FROM Polls '
                    'WHERE id = "{}";'.format(poll_id))
            if not status:
                self.bot.notice(issuer, "No Poll with given ID found, "
                                "aborting...")
                return
            status = PollStatus[status[0][0]]
            if status != PollStatus.RUNNING:
                self.bot.notice(issuer, "Poll #{} isn't running ({})".format(
                    poll_id, status.name))
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
            # TODO: remove poll from (future) list of running polls and cancel its Deferred
            self.bot.msg(self.channel, "Poll #{} vetoed".format(poll_id))
        self._poll_delayed_call_cancel(poll_id)

    @defer.inlineCallbacks
    def cmd_poll_cancel(self, issuer, poll_id):
        with self._lock: # TODO: needed?
            temp = yield self.dbpool.runQuery(
                    'SELECT creator, status FROM Polls '
                    'WHERE id = "{}";'.format(poll_id))
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
                yield self.dbpool.runInteraction(Vote.update_pollstatus, poll_id,
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
                'WHERE id={};'.format(poll_id))
        if not res:
            self.bot.notice(issuer, "Poll #{} doesn't exist".format(poll_id))
            return
        status = PollStatus[res[0][0]]
        current_time_end = res[0][1]
        if status != PollStatus.RUNNING:
            self.bot.notice(issuer, "Poll #{} isn't running".format(poll_id))
            return
        issuer_privilege = yield self.get_user_privilege(issuer)
        if issuer_privilege != UserPrivilege.ADMIN:
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
    def cmd_poll_list(self, issuer, status):
        if status == PollListStatusFilter.RUNNING:
            where = 'WHERE status="RUNNING" '
        elif status == PollListStatusFilter.ENDED:
            where = 'WHERE NOT status="RUNNING" '
        else:
            where = ''
        result = yield self.dbpool.runQuery('SELECT id, status, description FROM Polls ' +
                where + 'ORDER BY id DESC;')
        if not result:
            self.bot.notice(issuer, "No Polls found")
            return
        issuer_id = yield self.bot.get_auth(issuer)
        if not issuer_id:
            issuer_id = issuer
        for i, row in enumerate(result):
            if (i!=0 and i%5==0):
                confirm = yield self.require_confirmation(issuer, issuer_id,
                        "Continue? (confirm with {prefix}yes)".format(
                            prefix=self.prefix))
                if not confirm:
                    return
            self.bot.notice(issuer, "#{poll_id} ({status}): {description}".format(
                poll_id=row[0], status=row[1], description=textwrap.shorten(row[2], 50)))

    @defer.inlineCallbacks
    def cmd_vote(self, voter, poll_id, decision, comment, **kwargs):
        privilege = yield self.get_user_privilege(voter)
        if privilege not in [UserPrivilege.USER, UserPrivilege.ADMIN]:
            self.bot.notice(voter, "You are not allowed to vote")
            return
        voterid = yield self.bot.get_auth(voter)
        pollstatus = yield self.dbpool.runQuery('SELECT status FROM Polls '
                'WHERE id = "{}";'.format(poll_id))
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
                    'WHERE poll_id = "{}" AND user = "{}";'.format(poll_id,
                                                                   voterid))
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
                self.dbpool.runInteraction(Vote.update_votedecision,
                                           poll_id, voterid, decision,
                                           comment)
                self.bot.msg(self.channel, "{} changed vote from {} "
                             "to {} for poll #{}: {}".format(voter,
                                 previous_decision.name, decision.name,
                                 poll_id, textwrap.shorten(comment, 50)
                                 or "No comment given"))
            else:
                yield self.dbpool.runInteraction(Vote.insert_voteresult, poll_id,
                                                 voterid, decision, comment)
                self.bot.msg(self.channel,
                             "{} voted {} for poll #{}: {}".format(voter,
                                 decision.name, poll_id,
                                 textwrap.shorten(comment, 50) or "No comment given"))
        except Exception as e:
            Vote.logger.warn("Encountered error during vote: {}".format(e))
        vote_count = yield self.count_votes(poll_id)
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

    def topic(self, user, topic):
        pass

    def nick(self, oldnick, newnick):
        pass

    @defer.inlineCallbacks
    def join(self, user):
        privilege = yield self.get_user_privilege(user)
        if privilege not in (UserPrivilege.USER, UserPrivilege.ADMIN):
            return
        result = yield self.dbpool.runQuery('SELECT id FROM Polls '
                'WHERE status="RUNNING";')
        if not result:
            return
        num_running_polls = len(result)
        poll_id_list = set(itertools.chain(*result))
        user_id = yield self.bot.get_auth(user)
        result = yield self.dbpool.runQuery('SELECT poll_id FROM Votes '
                'WHERE user="{user_id}" AND poll_id IN ({poll_ids});'.format(
                    user_id=user_id, poll_ids=",".join(map(str, poll_id_list))))
        if not result:
            num_already_voted = 0
        else:
            num_already_voted = len(result)
        remaining = num_running_polls - num_already_voted
        if remaining:
            not_voted = poll_id_list - set(itertools.chain(*result))
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
        task = tokens[0]
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
            print(e)

    def connectionLost(self, reason):
        pass
