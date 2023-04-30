# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2020-2023>  <Sebastian Schmidt>

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
from twisted.web.template import Tag, tags
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
import typing

from . import abstract
from backends import Backends
from util import filesystem as fs
from util.decorators import maybe_deferred
from util.formatting import ColorCodes, good_contrast_with_black, from_human_readable
from util import formatting


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
    status TEXT CHECK(status in ("RUNNING", "CANCELED", "PASSED", "TIED", "FAILED", "VETOED", "DECIDED")) DEFAULT "RUNNING",
    category INTEGER,
    FOREIGN KEY (creator) REFERENCES Users(id) ON UPDATE CASCADE,
    FOREIGN KEY (vetoed_by) REFERENCES Users(id) ON UPDATE CASCADE,
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
    FOREIGN KEY (user) REFERENCES Users(id) ON UPDATE CASCADE
);""",
"""CREATE TABLE IF NOT EXISTS Categories (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT CHECK(color in ("white", "black", "darkblue", "darkgreen", "red", "darkred", "darkmagenta", "darkorange", "yellow", "lime", "darkcyan", "cyan", "blue", "magenta", "darkgray", "lightgray", "")),
    confidential BOOLEAN DEFAULT false CHECK(confidential in (true, false)), -- only for filtering on website
    default_duration_seconds INTEGER
);"""]


UserPrivilege = Enum("UserPrivilege", "REVOKED USER ADMIN")
PollStatus = Enum("PollStatus", "RUNNING CANCELED PASSED TIED FAILED VETOED DECIDED")
VoteDecision = Enum("VoteDecision", "NONE ABSTAIN YES NO")

PollDelayedCalls = namedtuple("PollDelayedCalls", "end_warning end")
VoteCount = namedtuple("VoteCount", "not_voted abstained yes no")

PollListStatusFilterType = typing.Literal["RUNNING", "CANCELED", "PASSED", "TIED",
                                          "FAILED", "VETOED", "DECIDED", "ENDED", "ALL"]
PollListStatusFilter = Enum("PollListStatusFilter", typing.get_args(PollListStatusFilterType))
UserListStatusFilterType = typing.Literal["ADMIN", "ACTIVE", "REVOKED", "ALL"]
UserListStatusFilter = Enum("UserListStatusFilter", typing.get_args(UserListStatusFilterType))
UserModifyFieldType = typing.Literal["name", "privilege"]
PollModifyFieldType = typing.Literal["category", "description"]
VoteDecisionType = typing.Literal["yes", "no", "abstain"]
CategoryModifyFieldType = typing.Literal["description", "color", "confidential", "duration"]


ChatHelp = namedtuple("ChatHelp", "subCommands flags params pos_params")
CategoryInfo = namedtuple("CategoryInfo", "id_ name description color confidential default_duration_seconds")


class OptionsWithoutHandlers(usage.Options):
    def _gather_handlers(self):
        return [], '', {}, {}, {}, {}

    @classmethod
    def chat_help(cls):
        subCommands = []
        flags = []
        params = []
        pos_params = []
        for long, short, _, desc in getattr(cls, "subCommands", []):
            long = formatting.colored(long, ColorCodes.cyan)
            if short:
                subCommands.append(Tag("")(long, f" ({short}): {desc}"))
            else:
                subCommands.append(Tag("")(long, f": {desc}"))
        for long, short, desc in getattr(cls, "optFlags", []):
            if short:
                flags.append("--{}, -{}: {}".format(long, short, desc))
            else:
                flags.append("--{}: {}".format(long, desc))
        for parameter in getattr(cls, "optParameters", []):
            long, short, default, desc = parameter[:4]
            if isinstance(default, Enum):
                desc += f" ({', '.join([e.name for e in type(default)])})"
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
                    parameter_description = p.name
                    if p.annotation is not Parameter.empty:
                        if typing.get_origin(p.annotation) == typing.Literal:
                            parameter_description += f" {typing.get_args(p.annotation)}"
                        else:
                            parameter_description += f" ({p.annotation.__name__})"
                    if p.default is not Parameter.empty:
                        parameter_description += f" (default {p.default})"
                    pos_params.append(parameter_description)
        return ChatHelp(subCommands=subCommands, flags=flags, params=params,
                        pos_params=pos_params)


class UserAddOptions(OptionsWithoutHandlers):
    optParameters = [
        ['privilege', 'p', UserPrivilege.USER, "Privilege for the new User",
            lambda x: UserPrivilege[x.upper()]]
    ]

    def parseArgs(self, name: str):
        self["user"] = name


class UserModifyOptions(OptionsWithoutHandlers):
    optFlags = [
        ['auth', 'a', "Use auth of the user directly"],
    ]

    def parseArgs(self, user: str, field: UserModifyFieldType, value: str):
        self["user"] = user
        self["field"] = field
        self["value"] = value

    def postOptions(self):
        if self["field"] not in ["name", "privilege"]:
            raise usage.UsageError("Invalid column name specified")
        if self["field"] == "privilege":
            self["value"] = self["value"].upper()


class UserListOptions(OptionsWithoutHandlers):
    def parseArgs(self, filter: UserListStatusFilterType = "ACTIVE"):
        self["filter"] = UserListStatusFilter[filter.upper()]


class UserOptions(OptionsWithoutHandlers):
    subCommands = [
        ['add', None, UserAddOptions, "Add a new user (admin only)"],
        ['modify', 'mod', UserModifyOptions, "Modify user name or rights (admin only)"],
        ['list', 'ls', UserListOptions, "List users"]
    ]


class VoteOptions(OptionsWithoutHandlers):
    optFlags = [
        ['yes', 'y', "autoconfirm changes"],
    ]

    def parseArgs(self, poll_id: int, decision: VoteDecisionType, *comment):
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
        if len(description) == 0:
            raise usage.UsageError("Description is required")
        self["description"] = " ".join(description)

    def postOptions(self):
        if sum([self["yes"], self["no"], self["abstain"]]) >= 2:
            raise usage.UsageError("'yes', 'no' and 'abstain' flags are exclusive")


class PollModifyOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id: int, field: PollModifyFieldType, *value):
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
    def parseArgs(self, poll_id: int):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollVetoOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id: int, *reason):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")
        self["reason"] = " ".join(reason)


class PollDecideOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id: int):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollExpireOptions(OptionsWithoutHandlers):
    def parseArgs(self, poll_id: int, *value):
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
    def parseArgs(self, poll_id: int):
        try:
            self["poll_id"] = int(poll_id)
        except ValueError:
            raise usage.UsageError("PollID has to be an integer")


class PollOptions(OptionsWithoutHandlers):
    subCommands = [
        ['create', 'call', PollCreateOptions, "Create a new poll"],
        ['modify', 'mod', PollModifyOptions, "Modify a poll (admin only)"],
        ['cancel', None, PollCancelOptions, "Cancel a poll (vote caller only)"],
        ['veto', None, PollVetoOptions, "Veto a poll (admin only)"],
        ['decide', None, PollDecideOptions, "Decide a poll (admin only)"],
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

    def parseArgs(self, name: str, *description):
        self["name"] = name
        self["description"] = " ".join(description)


class CategoryModifyOptions(OptionsWithoutHandlers):
    durationRegex = re.compile(r"((\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?$")

    def parseArgs(self, name: str, field: CategoryModifyFieldType, *value):
        self["name"] = name
        self["field"] = field
        self["value"] = " ".join(value)

    def postOptions(self):
        if self["field"] not in typing.get_args(CategoryModifyFieldType):
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
        elif self["field"] == "duration":
            self["field"] = "default_duration_seconds"
            if self["value"].lower() in ["none", "null"] or not self["value"]:
                self["value"] = None
            else:
                parsed = CategoryModifyOptions.durationRegex.match(self["value"])
                if not parsed:
                    raise usage.UsageError("Invalid duration given")
                days = int(parsed.group(2) or 0)
                hours = int(parsed.group(3) or 0)
                self["value"] = timedelta(days=days, hours=hours)


class CategoryOptions(OptionsWithoutHandlers):
    subCommands = [
        ['add', None, CategoryAddOptions, "Create a new category (admin only)"],
        ['modify', 'mod', CategoryModifyOptions, "Modify a category (admin only)"],
        ['list', 'ls', OptionsWithoutHandlers, "List categories"]
    ]


class HelpOptions(OptionsWithoutHandlers):
    def parseArgs(self, topic: str=None):
        self["topic"] = topic


class CommandOptions(OptionsWithoutHandlers):
    subCommands = [
        ['user', None, UserOptions, "Add/modify users"],
        ['vote', None, VoteOptions, "Vote for a poll"],
        ['poll', None, PollOptions, "Create/modify polls"],
        ['category', None, CategoryOptions, "Create/modify categories"],
        ['yes', None, OptionsWithoutHandlers, "Confirm previous action"],
        ['no', None, OptionsWithoutHandlers, "Abort previous action"],
        ['vhelp', None, HelpOptions, "Help: Chain subcommands with '.'"]
    ]


class Vote(abstract.ChannelWatcher):
    logger = Logger()
    supported_backends = [Backends.IRC, Backends.MATRIX]

    PollEndWarningTime = timedelta(days=2)
    PollDefaultDuration = timedelta(days=15)
    expireTimeRegex = re.compile(r"(extend|reduce)\s+(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?$")
    description_length = 150
    PrivilegeOrder = {"ADMIN": 0, "USER": 10, "REVOKED": 20} # Lower means shown earlier

    poll_id_stub = 'Poll #<font color="darkorange"><t:slot name="poll_id"/></font>'
    poll_status_stub = '<font><t:attr name="color"><t:slot name="status_color"/></t:attr><t:slot name="status"/></font>'
    category_stub = '<font><t:attr name="color"><t:slot name="category_fg"/></t:attr><t:attr name="background-color"><t:slot name="category_bg"/></t:attr><t:slot name="category"/></font>'
    description_stub = '<font color="darkcyan"><t:slot name="description"/></font>'
    creator_stub = '<font color="blue"><t:slot name="creator"/></font>'
    user_stub = '<font color="blue"><t:slot name="user"/></font>'
    comment_stub = '<font color="cyan"><t:slot name="comment"/></font>'
    standing_stub = 'YES:<font color="lime"><t:slot name="yes"/></font> | NO:<font color="red"><t:slot name="no"/></font> | ABSTAINED:<t:slot name="abstained"/> | OPEN:<t:slot name="not_voted"/>'
    final_standing_stub = 'YES:<font color="lime"><t:slot name="yes"/></font> | NO:<font color="red"><t:slot name="no"/></font> | ABSTAINED:<t:slot name="abstained"/> | NOT VOTED:<t:slot name="not_voted"/>'

    missing_voter_stub = from_human_readable('Your vote is required in channel <t:slot name="channel"/> for poll #<font color="darkorange"><t:slot name="poll_id"/></font>')
    user_added_stub = from_human_readable('Successfully added user <font color="blue"><t:slot name="user"/></font> (<t:slot name="auth"/>)')
    user_modified_stub = from_human_readable('Successfully modified user <font color="blue"><t:slot name="user"/></font>')
    new_poll_stub = from_human_readable(f'New {poll_id_stub} by {creator_stub}: <a><t:attr name="href"><t:slot name="url"/></t:attr>{description_stub}</a>')
    poll_description_change_stub = from_human_readable(f'{poll_id_stub}: description changed to <t:slot name="description"/>')
    poll_vetoed_stub = from_human_readable(f'{poll_id_stub}: vetoed')
    poll_decided_stub = from_human_readable(f'{poll_id_stub}: decided')
    poll_cancelled_stub = from_human_readable(f'{poll_id_stub}: cancelled')
    warn_poll_end_stub = from_human_readable(f'{poll_id_stub} is running out soon: {description_stub} by {creator_stub}: {standing_stub}')
    poll_end_stub = from_human_readable(f'{poll_id_stub} {poll_status_stub}: {description_stub} by {creator_stub}: {final_standing_stub}')
    poll_list_stub = from_human_readable(f'{poll_id_stub} by {creator_stub} ({poll_status_stub}): {description_stub}')
    poll_info_stub = from_human_readable(f'{poll_id_stub} by {creator_stub} ({poll_status_stub}): {description_stub}<br/>{standing_stub}')
    vote_changed_stub = from_human_readable(f'{poll_id_stub}: {user_stub} changed vote from <font><t:attr name="color"><t:slot name="previous_decision_color"/></t:attr><t:slot name="previous_decision"/></font> to <font><t:attr name="color"><t:slot name="decision_color"/></t:attr><t:slot name="decision"/></font>: {comment_stub}')
    new_vote_stub = from_human_readable(f'{poll_id_stub}: {user_stub} voted <font><t:attr name="color"><t:slot name="decision_color"/></t:attr><t:slot name="decision"/></font>: {comment_stub}')
    current_result_stub = from_human_readable(f'Current Result: {standing_stub}')
    already_voted_stub = from_human_readable(f'You already voted for this poll (<font><t:attr name="color"><t:slot name="decision_color"/></t:attr><t:slot name="decision"/></font>: {comment_stub}), please confirm, with \'<t:slot name="prefix"/>yes\' or \'<t:slot name="prefix"/>no\'')

    class Colors:
        poll_id = ColorCodes.darkorange
        user = ColorCodes.blue
        description = ColorCodes.darkcyan
        comment = ColorCodes.cyan
        yes = ColorCodes.lime
        no = ColorCodes.red
        PASSED = ColorCodes.lime
        FAILED = ColorCodes.red
        TIED = ColorCodes.darkorange
        VETOED = ColorCodes.darkred
        DECIDED = ColorCodes.darkgreen
        ADMIN = ColorCodes.darkgreen
        USER = ColorCodes.lime
        REVOKED = ColorCodes.darkred


    def __init__(self, bot, channel, config):
        super(Vote, self).__init__(bot, channel, config)
        self.prefix = config.get("prefix", "!")
        self._poll_url = config.get("poll_url", None)
        self._http_secret = config.get("http_secret", None)
        self.notification_channel = config.get("notification_channel", None)
        poll_duration = config.get("poll_duration", None)
        if not isinstance(poll_duration, int) or poll_duration <= 2:
            self.poll_duration = Vote.PollDefaultDuration
        else:
            self.poll_duration = timedelta(days=poll_duration)
        vote_configdir = os.path.join(fs.adirs.user_config_dir, "vote")
        os.makedirs(vote_configdir, exist_ok=True)
        dbfile = os.path.join(vote_configdir, "{}.sqlite".format(self.channel))
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
    def format_time(t):
        return t.strftime("%Y-%m-%d %H:%M:%S")

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
    def insert_poll(cursor, user, description, category, time_start, time_end):
        time_start_str = Vote.format_time(time_start)
        time_end_str = Vote.format_time(time_end)
        cursor.execute('INSERT INTO Polls (description, creator, category, time_start, time_end) '
                'VALUES  (:desc, :creator, :category, :time_start, :time_end);',
                {"desc": description, "creator": user, "category": category,
                 "time_start": time_start_str, "time_end": time_end_str})

    @staticmethod
    def update_poll_status(cursor, poll_id, status):
        cursor.execute('UPDATE Polls '
                       'SET status=:status '
                       'WHERE id=:id;', {"id": poll_id, "status": status.name})
        if status != PollStatus.RUNNING:
            now = datetime.utcnow()
            Vote.update_poll_time_end(cursor, poll_id, now)

    @staticmethod
    def update_poll_time_end(cursor, poll_id, time_end):
        timestr = Vote.format_time(time_end)
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
        now = datetime.utcnow()
        Vote.update_poll_time_end(cursor, poll_id, now)

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
        if field == "default_duration_seconds" and value is not None:
            value = value.seconds + value.days*24*60*60
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
            color = ColorCodes[colorname]
            fg = ColorCodes.black if good_contrast_with_black(color) else ColorCodes.white
            return formatting.colored(name, fg, color)
        return name

    @staticmethod
    def poll_status_color(poll_status: PollStatus) -> ColorCodes:
        if poll_status == PollStatus.PASSED:
            return Vote.Colors.PASSED
        if poll_status == PollStatus.FAILED:
            return Vote.Colors.FAILED
        if poll_status == PollStatus.TIED:
            return Vote.Colors.TIED
        if poll_status == PollStatus.VETOED:
            return Vote.Colors.VETOED
        if poll_status == PollStatus.DECIDED:
            return Vote.Colors.DECIDED
        return ColorCodes.darkgray

    @staticmethod
    def colored_user_status(user_status):
        if user_status == UserPrivilege.ADMIN:
            return formatting.colored(user_status.name, Vote.Colors.ADMIN)
        if user_status == UserPrivilege.USER:
            return formatting.colored(user_status.name, Vote.Colors.USER)
        if user_status == UserPrivilege.REVOKED:
            return formatting.colored(user_status.name, Vote.Colors.REVOKED)
        return user_status.name

    @staticmethod
    def colored_poll_id(poll_id):
        return formatting.colored(str(poll_id), Vote.Colors.poll_id)

    @staticmethod
    def vote_decision_color(decision: VoteDecision) -> ColorCodes:
        if decision == VoteDecision.YES:
            return Vote.Colors.yes
        if decision == VoteDecision.NO:
            return Vote.Colors.no
        return ColorCodes.lightgray

    @defer.inlineCallbacks
    def get_user_privilege(self, name):
        auth = yield self.bot.get_auth(name)
        if not auth:
            Vote.logger.info("User {user} is not authed", user=name)
            return None
        privilege = yield self.dbpool.runQuery('SELECT privilege FROM Users '
                                               'WHERE ID=:auth;', {"auth": auth})
        try:
            return UserPrivilege[privilege[0][0]]
        except Exception as e:
            Vote.logger.debug("Error getting user privilege for {user}: {e}",
                              user=name, e=e)
            return None

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
    def notify_missing_voters(self, poll_id):
        res = yield self.dbpool.runQuery('SELECT id FROM Users WHERE privilege!="REVOKED";')
        if not res:
            Vote.logger.warn("Active poll, but no active user")
            return
        active_users = {x[0] for x in res}
        res = yield self.dbpool.runQuery('SELECT user FROM Votes WHERE poll_id=:poll_id;',
                                         {"poll_id": poll_id})
        users_who_voted = {x[0] for x in res}
        missing_voter_auths = active_users - users_who_voted
        for user in self.bot.userlist[self.channel]:
            auth = yield self.bot.get_auth(user)
            if not auth:
                continue
            if auth in missing_voter_auths:
                msg = Vote.missing_voter_stub.clone()
                msg.fillSlots(channel=self.channel, poll_id=str(poll_id))
                self.bot.notice(user, msg)

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
        msg = Vote.warn_poll_end_stub.clone()
        msg.fillSlots(poll_id=str(poll_id), description=desc, creator=creator,
                      yes=str(vote_count.yes), no=str(vote_count.no),
                      abstained=str(vote_count.abstained),
                      not_voted=str(vote_count.not_voted))
        self.bot.msg(self.channel, msg)
        self.notify_missing_voters(poll_id)

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
        msg = Vote.poll_end_stub.clone()
        msg.fillSlots(poll_id=str(poll_id), status_color=Vote.poll_status_color(result),
                      status=result.name, description=desc, creator=creator,
                      yes=str(vote_count.yes), no=str(vote_count.no),
                      abstained=str(vote_count.abstained),
                      not_voted=str(vote_count.not_voted))
        self.bot.msg(self.channel, msg)
        if self.notification_channel:
            self.bot.msg(self.notification_channel, msg)
        # add Vote "NONE" for all active users who haven't voted
        self.dbpool.runInteraction(Vote.add_not_voted, poll_id)

    @defer.inlineCallbacks
    def is_vote_user(self, user):
        return (yield self.get_user_privilege(user)) in (UserPrivilege.ADMIN, UserPrivilege.USER)

    @defer.inlineCallbacks
    def is_vote_admin(self, user):
        return (yield self.get_user_privilege(user))==UserPrivilege.ADMIN

    def poll_url(self, poll_id=None):
        if self._poll_url is None:
            return None
        if poll_id is None:
            return "{}?key={}".format(self._poll_url, self._http_secret)
        return "{}/{}?key={}".format(self._poll_url, poll_id, self._http_secret)

    @defer.inlineCallbacks
    def cmd_user_add(self, issuer, user, privilege):
        is_admin = yield self.bot.is_user_admin(issuer)
        if not (is_admin or (yield self.is_vote_admin(issuer))):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        if user not in self.bot.userlist[self.channel]:
            self.bot.notice(issuer, "User is not in this channel")
            return
        auth = yield self.bot.get_auth(user)
        if not auth:
            self.bot.notice(issuer, "Couldn't query user's AUTH, aborting...")
            return
        displayname = self.bot.get_displayname(user, self.channel)
        try:
            yield self.dbpool.runInteraction(Vote.insert_user, auth, displayname,
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
        msg = Vote.user_added_stub.clone()
        msg.fillSlots(user=displayname, auth=auth)
        self.bot.notice(issuer, msg)

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
        msg = Vote.user_modified_stub.clone()
        msg.fillSlots(user=user)
        self.bot.notice(issuer, msg)

    @defer.inlineCallbacks
    def cmd_user_list(self, issuer, filter):
        if not(yield self.is_vote_user(issuer)):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        if filter == UserListStatusFilter.ALL:
            filter_string = ""
        elif filter == UserListStatusFilter.ADMIN:
            filter_string = 'WHERE privilege="ADMIN"'
        elif filter == UserListStatusFilter.ACTIVE:
            filter_string = 'WHERE privilege!="REVOKED"'
        elif filter == UserListStatusFilter.REVOKED:
            filter_string = 'WHERE privilege="REVOKED"'
        else:
            Vote.logger.error("Userlist: Invalid filter {filter}, using ACTIVE instead",
                              filter=filter)
            filter_string = 'WHERE privilege!="REVOKED"'
        try:
            users_raw = yield self.dbpool.runQuery('SELECT name, privilege FROM Users ' +
                                                   filter_string + ';')
        except Exception as e:
            self.bot.notice(issuer, f"Couldn't query user list. Reason: {e}")
            Vote.logger.warn("Error querying user list for vote system in channel "
                             "{channel}: {e}", channel=self.channel, e=e)
            return
        users_raw = sorted(users_raw, key=lambda x: Vote.PrivilegeOrder[x[1]])
        messages = []
        msg = Tag("")
        for privilege, userlist in itertools.groupby(users_raw, lambda x: x[1]):
            msg.children.append(Vote.colored_user_status(UserPrivilege[privilege]))
            msg.children.append(": " + ", ".join(x[0] for x in userlist))
            msg.children.append(tags.br)
        self.bot.notice(issuer, msg)

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
            category_id = res.id_
            category_color = res.color
            if res.default_duration_seconds:
                duration = timedelta(seconds=res.default_duration_seconds)
            else:
                duration = self.poll_duration
        else:
            category_id = None
            category_color = None
            duration = self.poll_duration
        with self._lock:
            try:
                now = datetime.now(tz=timezone.utc)
                end = now + duration
                yield self.dbpool.runInteraction(Vote.insert_poll, issuer_auth,
                                                 description, category_id, now, end)
            except Exception as e:
                self.bot.msg(self.channel, "Could not create new poll")
                Vote.logger.warn("Error inserting poll into DB: {error}",
                                 error=e)
                return
            poll_id = yield self.dbpool.runQuery('SELECT MAX(id) FROM Polls;')
            poll_id = poll_id[0][0]
            url = self.poll_url(poll_id)
            if url is None:
                url = ""
            issuer_displayname = self.bot.get_displayname(issuer, self.channel)
            msg = Vote.new_poll_stub.clone()
            msg.fillSlots(poll_id=str(poll_id), creator=issuer_displayname,
                          url=url, description=description)
            if category:
                msg.children.insert(0, " ")
                msg.children.insert(0, Vote.colored_category_name(category, category_color))
            self.bot.msg(self.channel, msg)
            if self.notification_channel:
                self.bot.msg(self.notification_channel, msg)
        self._poll_delay_call(poll_id, end)
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
            value = res.id_
        try:
            yield self.dbpool.runInteraction(Vote.update_poll_field, poll_id,
                                             field, value)
        except Exception as e:
            Vote.logger.warn("")
            self.bot.notice(issuer, "Couldn't modify poll ({})".format(e))
            return
        if field == "description":
            msg = Vote.poll_description_change_stub.clone()
            msg.fillSlots(poll_id=str(poll_id), description=value)
            self.bot.notice(self.channel, msg)
            if self.notification_channel:
                self.bot.notice(self.notification_channel, msg)
        else:
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
            msg = Vote.poll_vetoed_stub.clone().fillSlots(poll_id=str(poll_id))
            self.bot.msg(self.channel, msg)
            if self.notification_channel:
                self.bot.msg(self.notification_channel, msg)
        self._poll_delayed_call_cancel(poll_id)

    @defer.inlineCallbacks
    def cmd_poll_decide(self, issuer, poll_id):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only admins can DECIDE polls")
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
                yield self.dbpool.runInteraction(Vote.update_poll_status, poll_id,
                                                 PollStatus.DECIDED)
            except Exception as e:
                self.bot.notice(issuer, "Error deciding poll, contact the admin")
                Vote.logger.warn("Error deciding poll #{id}: {error}",
                                 id=poll_id, error=e)
                return
            msg = Vote.poll_decided_stub.clone().fillSlots(poll_id=str(poll_id))
            self.bot.msg(self.channel, msg)
            if self.notification_channel:
                self.bot.msg(self.notification_channel, msg)
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
            msg = Vote.poll_cancelled_stub.clone().fillSlots(poll_id=str(poll_id))
            self.bot.msg(self.channel, msg)
            if self.notification_channel:
                self.bot.msg(self.notification_channel, msg)
        self._poll_delayed_call_cancel(poll_id)

    @defer.inlineCallbacks
    def cmd_poll_expire(self, issuer, poll_id, change):
        if not (yield self.is_vote_admin(issuer)):
            self.bot.notice(issuer, "Only admins can change poll duration")
            return
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
            msg = Tag("")("Poll #", Vote.colored_poll_id(poll_id),
                          " will end at ", time_end.isoformat())
            self.bot.msg(self.channel, msg)
            if self.notification_channel:
                self.bot.msg(self.notification_channel, msg)
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
            msg = Vote.poll_list_stub.clone()
            msg.fillSlots(poll_id=str(poll_id), creator=creator, status=status.name,
                          status_color=Vote.poll_status_color(status),
                          description=desc)
            if category:
                msg.children.insert(0, " ")
                msg.children.insert(0, Vote.colored_category_name(category, color))
            self.bot.notice(issuer, msg)

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
        vote_count = yield self.count_votes(poll_id, status==PollStatus.RUNNING)
        msg = Vote.poll_info_stub.clone()
        msg.fillSlots(poll_id=str(poll_id), creator=creator, status=status.name,
                      status_color=Vote.poll_status_color(status),
                      description=desc, yes=str(vote_count.yes),
                      no=str(vote_count.no), abstained=str(vote_count.abstained),
                      not_voted=str(vote_count.not_voted))
        if category:
            msg.children.insert(0, " ")
            msg.children.insert(Vote.colored_category_name(category, color))
        self.bot.notice(issuer, msg)

    def cmd_poll_url(self, issuer):
        url = self.poll_url()
        if url is None:
            url = "N/A"
        self.bot.notice(issuer, url)

    @defer.inlineCallbacks
    def get_category_info(self, category_name):
        res = yield self.dbpool.runQuery('SELECT id, description, color, confidential, '
                                         'default_duration_seconds FROM Categories '
                                         'WHERE name=:name;',
                                         {"name": category_name})
        if not res:
            return None
        return CategoryInfo(id_=res[0][0], name=category_name,
                            description=res[0][1], color=res[0][2],
                            confidential=res[0][3],
                            default_duration_seconds=res[0][4])

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
        self.bot.msg(self.channel, Tag("")("Added category ",
                                           Vote.colored_category_name(name,
                                                                      color)))

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
    def cmd_category_list(self, issuer):
        if not (yield self.is_vote_user(issuer)):
            self.bot.notice(issuer, "Insufficient permissions")
            return
        res = yield self.dbpool.runQuery(
                'SELECT name, description, color, confidential FROM Categories;')
        if not res:
            self.bot.notice(issuer, "There are no categories")
            return
        msg = Tag("")(f"There are {len(res)} categories (confidential marked with *)")
        for name, _, color, secret in res:
            msg.children.append(tags.br)
            msg.children.append("*" if secret else " ")
            msg.children.append(Vote.colored_category_name(name, color))
        self.bot.notice(issuer, msg)

    @defer.inlineCallbacks
    def cmd_vote(self, voter, poll_id, decision, comment, **kwargs):
        if not (yield self.is_vote_user(voter)):
            self.bot.notice(voter, "You are not allowed to vote")
            return
        voterid = yield self.bot.get_auth(voter)
        voter_displayname = self.bot.get_displayname(voter, self.channel)
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
                    'WHERE poll_id=:poll_id AND user=:voterid;',
                    {"poll_id": poll_id, "voterid": voterid})
            if query:
                previous_decision = VoteDecision[query[0][0]]
                previous_comment = query[0][1]
                # require confirmation
                if kwargs['yes']:
                    confirmed = True
                else:
                    confirmation_msg = Vote.already_voted_stub.clone()
                    confirmation_msg.fillSlots(
                            decision=previous_decision.name,
                            decision_color=Vote.vote_decision_color(previous_decision),
                            comment=previous_comment,
                            prefix=self.prefix)
                    confirmed = yield self.require_confirmation(voter, voterid,
                                                                confirmation_msg)
                if not confirmed:
                    return
                yield self.dbpool.runInteraction(Vote.update_vote_decision,
                                                 poll_id, voterid, decision,
                                                 comment)
                msg = Vote.vote_changed_stub.clone()
                msg.fillSlots(poll_id=str(poll_id), user=voter_displayname,
                              previous_decision=previous_decision.name,
                              previous_decision_color=Vote.vote_decision_color(previous_decision),
                              decision=decision.name,
                              decision_color=Vote.vote_decision_color(decision),
                              comment=comment or "No Comment")
            else:
                yield self.dbpool.runInteraction(Vote.insert_vote, poll_id,
                                                 voterid, decision, comment)
                msg = Vote.new_vote_stub.clone()
                msg.fillSlots(poll_id=str(poll_id), user=voter_displayname,
                              decision=decision.name,
                              decision_color=Vote.vote_decision_color(decision),
                              comment=comment or "No Comment")
        except Exception as e:
            self.bot.notice(voter, "An error occured. Please contact the admin.")
            Vote.logger.warn("Encountered error during vote: {}".format(e))
            return
        vote_count = yield self.count_votes(poll_id, True)
        # end poll early on 2/3 majority
        early_consensus = 3*max(vote_count.yes, vote_count.no) >= 2*self._num_active_users
        if not early_consensus:
            current_result = Vote.current_result_stub.clone()
            current_result.fillSlots(yes=str(vote_count.yes), no=str(vote_count.no),
                                     abstained=str(vote_count.abstained),
                                     not_voted=str(vote_count.not_voted))
            msg.children.append(tags.br)
            msg.children.append(current_result)
        self.bot.msg(self.channel, msg)
        if early_consensus:
            self._poll_delayed_call_cancel(poll_id)
            self.end_poll(poll_id)

    @maybe_deferred
    def require_confirmation(self, user, userid, message):
        if userid in self._pending_confirmations:
            self.bot.notice(user, "Another confirmation is already "
                            "pending")
            return False
        self.bot.notice(self.channel, message)
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

    def cmd_vhelp(self, user, topic):
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
                        ColorCodes.red))
                    return

        sig = option_class.chat_help()
        if sig.subCommands:
            msg = Tag("")(formatting.colored("Available commands",
                                             ColorCodes.blue), ": ")
            for i, command in enumerate(sig.subCommands):
                if i>0:
                    msg.children.append(" | ")
                msg.children.append(command)
            self.bot.notice(user, msg)
            return
        msg = Tag("")(desc)
        if sig.flags:
            msg.children.append(formatting.colored("Flags", ColorCodes.yellow))
            msg.children.append(": " + "; ".join(sig.flags))
        if sig.params:
            if len(msg.children):
                msg.children.append(tags.br)
            msg.children.append(formatting.colored("Optional parameters",
                                                   ColorCodes.yellow))
            msg.children.append(": " + "; ".join(sig.params))
        if sig.pos_params:
            if len(msg.children):
                msg.children.append(tags.br)
            msg.children.append(formatting.colored("Positional parameters",
                                                   ColorCodes.lime))
            msg.children.append(": " + "; ".join(sig.pos_params))
        self.bot.notice(user, msg)

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
        # TODO: handle formatted messages
        message = formatting.to_plaintext(message)
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
