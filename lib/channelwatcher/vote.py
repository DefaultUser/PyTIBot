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
from twisted.internet import defer
from twisted.logger import Logger
import os
from enum import Enum
from threading import Lock

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
    creator INTEGER NOT NULL,
    time_start DATETIME DEFAULT CURRENT_TIMESTAMP, -- unix time
    duration INTEGER DEFAULT 604800, -- default duration: 1 week
    status TEXT CHECK(status in ("RUNNING", "CANCELED", "PASSED", "TIED", "FAILED", "VETOED")) DEFAULT "RUNNING",
    FOREIGN KEY (creator) REFERENCES Users(id)
)""",
"""
CREATE TABLE IF NOT EXISTS VoteResults (
    poll_id INTEGER,
    user_id INTEGER,
    vote TEXT CHECK(vote in ("NONE", "ABSTAIN", "YES", "NO")),
    comment TEXT,
    time_create INTEGER, -- needed?
    PRIMARY KEY (poll_id, user_id),
    FOREIGN KEY (poll_id) REFERENCES Polls(id),
    FOREIGN KEY (user_id) REFERENCES Users(id)
    -- TODO: check that user currently has privileges to vote
)
"""]


UserPrivilege = Enum("UserPrivilege", "REVOKED USER ADMIN INVALID")

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
        self.dbpool.runInteraction(Vote.initialize_databases)
        self._lock = Lock()

    @staticmethod
    def initialize_databases(cursor):
        for statement in _INIT_DB_STATEMENTS:
            cursor.execute(statement)

    @staticmethod
    def insert_user(cursor, auth, user, privilege="USER"):
        cursor.execute('INSERT INTO Users (id, name, privilege) '
                       'VALUES ("{}", "{}", "{}");'.format(auth, user,
                                                           privilege))

    @staticmethod
    def insert_poll(cursor, user, description):
        cursor.execute('INSERT INTO Polls (description, creator) '
                       'VALUES  ("{}", "{}");'.format(user, description))

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
    def add_user(self, issuer, user, privilege="USER"):
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
        self.bot.notice(issuer, "Successfully added User {} ({})".format(user,
                                                                         auth))

    @defer.inlineCallbacks
    def vote_call(self, issuer, description):
        privilege = yield self.get_user_privilege(issuer)
        if privilege not in [UserPrivilege.USER, UserPrivilege.ADMIN]:
            self.bot.notice(issuer, "You are not allowed to create votes")
            return
        with self._lock:
            try:
                yield self.dbpool.runInteraction(Vote.insert_poll, issuer,
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
        if task == "adduser":
            if not (len(tokens) in (2, 3)):
                self.bot.notice(user, "Incorrect call for adduser")
                return
            self.add_user(user, *tokens[1:])
        elif task == "vcall":
            if len(tokens) < 2:
                self.bot.notice(user, "Please add a description")
                return
            self.vote_call(user, " ".join(tokens[1:]))

    def connectionLost(self, reason):
        pass
