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
from enum import Enum
from threading import Lock
import textwrap

from . import abstract
from util import filesystem as fs


_INIT_DB_STATEMENTS = ["""
PRAGMA foreign_keys = ON;""",
"""
CREATE TABLE IF NOT EXISTS Users (
    id TEXT PRIMARY KEY NOT NULL, -- auth
    name TEXT NOT NULL,
    privilege TEXT NOT NULL CHECK (privilege in ("REVOKED", "USER", "ADMIN"))
)""",
"""
CREATE TABLE IF NOT EXISTS Polls (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    creator TEXT NOT NULL,
    vetoed_by TEXT,
    veto_reason TEXT,
    time_start DATETIME DEFAULT CURRENT_TIMESTAMP, -- unix time
    duration INTEGER DEFAULT 604800, -- default duration: 1 week
    status TEXT CHECK(status in ("RUNNING", "CANCELED", "PASSED", "TIED", "FAILED", "VETOED")) DEFAULT "RUNNING",
    FOREIGN KEY (creator) REFERENCES Users(id),
    FOREIGN KEY (vetoed_by) REFERENCES Users(id)
)""",
"""
CREATE TABLE IF NOT EXISTS Votes (
    poll_id INTEGER,
    user TEXT,
    vote TEXT CHECK(vote in ("NONE", "ABSTAIN", "YES", "NO")),
    comment TEXT,
    -- time_create INTEGER, -- needed?
    PRIMARY KEY (poll_id, user),
    FOREIGN KEY (poll_id) REFERENCES Polls(id),
    FOREIGN KEY (user) REFERENCES Users(id)
    -- TODO: check that user currently has privileges to vote
)
"""]


UserPrivilege = Enum("UserPrivilege", "REVOKED USER ADMIN INVALID")
PollStatus = Enum("PollStatus", "RUNNING CANCELED PASSED TIED FAILED VETOED")
VoteDecision = Enum("VoteDecision", "NONE ABSTAIN YES NO")


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

    def parseArgs(self, pollid, decision, *args):
        try:
            self["pollid"] = int(pollid)
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
    def parseArgs(self, pollid):
        try:
            self["pollid"] = int(pollid)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollVetoOptions(OptionsWithoutHandlers):
    def parseArgs(self, pollid, *args):
        try:
            self["pollid"] = int(pollid)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["reason"] = " ".join(args)


class PollExpireOptions(OptionsWithoutHandlers):
    def parseArgs(self, pollid, change):
        try:
            self["pollid"] = int(pollid)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["change"] = change # should accept (now)?(+|-)?(\d+d)?(\d+h)?


class PollListOptions(OptionsWithoutHandlers):
    optParameters = [
        ['status', 's', PollStatus.RUNNING, "Filter with this status",
            lambda x: PollStatus[x.upper()]],
        ['count', 'c', 0, "Limit list to the first <n> items", int],
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
        self._setup()

    @defer.inlineCallbacks
    def _setup(self):
        yield self.dbpool.runInteraction(Vote.initialize_databases)
        self.query_active_user_count()

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
    def update_pollstatus(cursor, pollid, status):
        cursor.execute('UPDATE Polls '
                       'SET status = "{status}" '
                       'WHERE id = "{pollid}";'.format(pollid=pollid,
                                                       status=status.name))

    @staticmethod
    def update_poll_veto(cursor, pollid, vetoed_by, reason):
        cursor.execute('UPDATE Polls '
                       'SET status = "VETOED", vetoed_by = "{vetoed_by}", '
                       'veto_reason = "{reason}" '
                       'WHERE id = "{pollid}";'.format(pollid=pollid,
                                                       vetoed_by=vetoed_by,
                                                       reason=reason))

    @staticmethod
    def insert_voteresult(cursor, pollid, user, decision, comment):
        cursor.execute('INSERT INTO Votes (poll_id, user, vote, comment) '
                       'VALUES ("{}", "{}", "{}", "{}");'.format(pollid, user,
                                                                 decision.name,
                                                                 comment))

    @staticmethod
    def update_votedecision(cursor, pollid, user, decision, comment):
        cursor.execute('UPDATE Votes '
                       'SET vote = "{decision}", comment = "{comment}" '
                       'WHERE poll_id = "{pollid}" '
                       'AND user = "{user}";'.format(pollid=pollid, user=user,
                                                     decision=decision.name,
                                                     comment=comment))

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
        # a DB query is required anyways (for the current permissions
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
            voteid = yield self.dbpool.runQuery('SELECT MAX(id) FROM Polls')
            voteid = voteid[0][0]
            self.bot.msg(self.channel, "New poll #{voteid} by {user}({url}): "
                         "{description}".format(voteid=voteid, user=issuer,
                                                url="URL TODO",
                                                description=description))
        if kwargs["yes"]:
            self.cmd_vote(issuer, voteid, VoteDecision.YES, "")
        elif kwargs["no"]:
            self.cmd_vote(issuer, voteid, VoteDecision.NO, "")
        elif kwargs["abstain"]:
            self.cmd_vote(issuer, voteid, VoteDecision.ABSTAIN, "")

    @defer.inlineCallbacks
    def cmd_poll_veto(self, issuer, pollid, reason):
        issuer_privilege = yield self.get_user_privilege(issuer)
        if issuer_privilege != UserPrivilege.ADMIN:
            self.bot.notice(issuer, "Only admins can VETO polls")
            return
        issuer_auth = yield self.bot.get_auth(issuer)
        with self._lock: # TODO: is this needed?
            status = yield self.dbpool.runQuery(
                    'SELECT status FROM Polls '
                    'WHERE id = "{}";'.format(pollid))
            if not status:
                self.bot.notice(issuer, "No Poll with given ID found, "
                                "aborting...")
                return
            status = PollStatus[status[0][0]]
            if status != PollStatus.RUNNING:
                self.bot.notice(issuer, "Poll #{} isn't running ({})".format(
                    pollid, status.name))
                return
            try:
                # TODO: confirmation?
                yield self.dbpool.runInteraction(Vote.update_poll_veto, pollid,
                                                 issuer_auth, reason)
            except Exception as e:
                self.bot.notice(issuer, "Error vetoing poll, contact the "
                                "admin")
                Vote.logger.warn("Error vetoing poll #{id}: {error}",
                                 id=pollid, error=e)
                return
            # TODO: remove poll from (future) list of running polls and cancel its Deferred
            self.bot.msg(self.channel, "Poll #{} vetoed".format(pollid))

    @defer.inlineCallbacks
    def cmd_poll_cancel(self, issuer, pollid):
        with self._lock: # TODO: needed?
            temp = yield self.dbpool.runQuery(
                    'SELECT creator, status FROM Polls '
                    'WHERE id = "{}";'.format(pollid))
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
                    pollid, status.name))
                return
            try:
                yield self.dbpool.runInteraction(Vote.update_pollstatus, pollid,
                                                 PollStatus.CANCELED)
            except Exception as e:
                self.bot.notice(issuer, "Error cancelling poll, contact the "
                                "admin")
                Vote.logger.warn("Error cancelling poll #{id}: {error}",
                                 id=pollid, error=e)
                return
            # TODO: remove poll from (future) list of running polls and cancel its Deferred
            self.bot.msg(self.channel, "Poll #{} cancelled".format(pollid))

    @defer.inlineCallbacks
    def cmd_vote(self, voter, pollid, decision, comment, **kwargs):
        privilege = yield self.get_user_privilege(voter)
        if privilege not in [UserPrivilege.USER, UserPrivilege.ADMIN]:
            self.bot.notice(voter, "You are not allowed to vote")
            return
        voterid = yield self.bot.get_auth(voter)
        pollstatus = yield self.dbpool.runQuery('SELECT status FROM Polls '
                'WHERE id = "{}";'.format(pollid))
        if not pollstatus:
            self.bot.notice(voter, "Poll #{} doesn't exist".format(pollid))
            return
        pollstatus = PollStatus[pollstatus[0][0]]
        if pollstatus != PollStatus.RUNNING:
            self.bot.notice(voter, "Poll #{} is not running ({})".format(pollid,
                pollstatus.name))
            return
        try:
            query = yield self.dbpool.runQuery(
                    'SELECT vote, comment FROM Votes '
                    'WHERE poll_id = "{}" AND user = "{}";'.format(pollid,
                                                                   voterid))
            if query:
                previous_decision = VoteDecision[query[0][0]]
                previous_comment = query[0][1]
                self.bot.notice(voter, "You already voted for this poll "
                                "({vote}: {comment}), please confirm with "
                                "'{prefix}yes' or '{prefix}no".format(
                                    vote=previous_decision.name,
                                    comment=textwrap.shorten(previous_comment,
                                                             50),
                                    prefix=self.prefix))
                # require confirmation, override pending confirmations
                # TODO: split to function
                self._pending_confirmations[voterid] = defer.Deferred()
                self._pending_confirmations[voterid].addTimeout(60, reactor)
                try:
                    confirmed = yield self._pending_confirmations[voterid]
                    if confirmed:
                        self.dbpool.runInteraction(Vote.update_votedecision,
                                                   pollid, voterid, decision,
                                                   comment)
                        self.bot.msg(self.channel, "{} changed vote from {} "
                                     "to {} for poll #{}: {}".format(voter,
                                         previous_decision.name, decision.name,
                                         pollid, textwrap.shorten(comment, 50)
                                         or "No comment given"))
                except defer.TimeoutError as e:
                    self.bot.notice(voter, "Confirmation timed out")
                finally:
                    self._pending_confirmations.pop(voterid)
            else:
                yield self.dbpool.runInteraction(Vote.insert_voteresult, pollid,
                                                 voterid, decision, comment)
                self.bot.msg(self.channel,
                             "{} voted {} for poll #{}: {}".format(voter,
                                 decision.name, pollid,
                                 textwrap.shorten(comment, 50) or "No comment given"))
        except Exception as e:
            Vote.logger.warn("Encountered error during vote: {}".format(e))
        # TODO: check if poll is decided

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

    def join(self, user):
        pass

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
