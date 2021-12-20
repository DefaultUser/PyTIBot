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
import asyncio
from twisted.internet.defer import Deferred, ensureDeferred, inlineCallbacks
from twisted.internet import reactor
from twisted.logger import Logger
from twisted.words.protocols import irc
from nio import AsyncClient, MatrixRoom, RoomMessageText, RoomMessageNotice
from nio import responses as MatrixResponses
from nio.api import RoomPreset
import os
from zope.interface import implementer

from backends import Backends
from backends.common import setup_channelwatchers
from backends.interfaces import IBot

from util.aio_compat import deferred_to_future, future_to_deferred
from util import filesystem as fs
from util import formatting
from util.decorators import maybe_deferred


@implementer(IBot)
class MatrixBot:
    log = Logger()

    def __init__(self, config):
        self.config = config
        self.client = AsyncClient(config["Connection"]["server"],
                                  config["Connection"]["username"],
                                  device_id=config["Connection"].get("deviceID", None))
        self.load_settings()
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_notice, RoomMessageNotice)

    def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        MatrixBot.log.info("{room.display_name} | {event.sender} : {event.body}",
                           room=room, event=event)
        room_id = room.room_id
        message = event.body
        try:
            if event.source['content']['m.relates_to']['rel_type'] == "m.replace":
                message = message.removeprefix("* ")
        except KeyError:
            pass
        # channelwatchers
        if room_id in self.channelwatchers:
            for watcher in self.channelwatchers[room_id]:
                watcher.msg(event.sender, message)
        # TODO: aliases, commands, triggers

    def on_notice(self, room: MatrixRoom, event: RoomMessageNotice) -> None:
        MatrixBot.log.info("{room.display_name} | [{event.sender} : {event.body}]",
                           room=room, event=event)
        room_id = room.room_id
        message = event.body
        try:
            if event.source['content']['m.relates_to']['rel_type'] == "m.replace":
                message = message.removeprefix("* ")
        except KeyError:
            pass
        # channelwatchers
        if room_id in self.channelwatchers:
            for watcher in self.channelwatchers[room_id]:
                watcher.notice(event.sender, message)

    @property
    def state_filepath(self):
        server_address = self.client.homeserver.removeprefix("http://").removeprefix("https://")
        return os.path.join(fs.adirs.user_cache_dir, f"state-{server_address}")

    def load_settings(self):
        MatrixBot.log.info("Loading settings from {path}", path=self.config._path)
        # TODO: setup aliases, triggers, commands
        self.channelwatchers = setup_channelwatchers(self, self.config.get("Channelmodules", {}),
                                                     Backends.MATRIX)

    def reload(self):
        self.config.load()
        self.load_settings()

    @maybe_deferred
    def get_auth(self, user):
        # the user handle is already unique
        return user

    @maybe_deferred
    def is_user_admin(self, user):
        return user in self.config["Connection"]["admins"]

    @property
    def userlist(self):
        return {room_id: list(room.users.keys()) for room_id, room in self.client.rooms.items()}

    async def start(self):
        response = await future_to_deferred(self.client.login(self.config["Connection"]["password"]))
        if isinstance(response, MatrixResponses.LoginError):
            MatrixBot.log.error("Error logging in {response}", response=response)
            raise EnvironmentError("Login failed")
        MatrixBot.log.info("Login successfull")
        # WARNING: don't await the signedOn method
        # it requires a first sync to know the already joined rooms
        self.signedOn()
        sync_token = None
        if (os.path.isfile(self.state_filepath)):
            with open(self.state_filepath) as f:
                sync_token = f.read().strip()
        await future_to_deferred(self.client.sync_forever(timeout=30000, loop_sleep_time=1000,
                                                          since=sync_token, full_state=True))
        return Deferred()

    @inlineCallbacks
    def signedOn(self):
        yield future_to_deferred(asyncio.ensure_future(self.client.synced.wait()))
        for room in self.config["Connection"]["channels"]:
            if room not in self.client.rooms:
                self.join(room)

    def quit(self, ignored=None):
        self.stop()
        # save latest sync token
        with open(self.state_filepath, "w") as f:
            f.write(self.client.next_batch)
        MatrixBot.log.info("Shutting down")
        reactor.stop()

    def stop(self):
        future_to_deferred(self.client.close())

    @staticmethod
    def formatted_message_content(message):
        # FIXME: for now, convert IRC formatting to html
        # formatting is currently designed with only IRC in mind
        unformatted = irc.stripFormatting(message)
        if unformatted == message:
            return {"body": message}
        return {"body": unformatted, "format": "org.matrix.custom.html",
                "formatted_body": formatting.to_matrix(message).replace("\n", "<br/>")}

    @inlineCallbacks
    def get_or_create_direct_message_room(self, user):
        for room_id, room in self.client.rooms.items():
            if room.is_group and room.member_count == 2 and user in room.users:
                return room_id
        resp = yield future_to_deferred(self.client.room_create(is_direct=True, invite=[user],
            preset=RoomPreset.trusted_private_chat))
        return resp.room_id

    def resolve_joined_room_alias(self, target):
        for room_id, room in self.client.rooms.items():
            if room.machine_name == target:
                return room_id
        else:
            MatrixBot.log.info("No room with alias {target} found", target=target)
            return

    @inlineCallbacks
    def msg(self, target, message, length=None):
        # direct messages will stay open until the user leaves the room
        # TODO: leave rooms when the last user left a room
        if target.startswith("@"):
            target = yield self.get_or_create_direct_message_room(target)
        elif target.startswith("#"):
            target = self.resolve_joined_room_alias(target)
        if target is None:
            return
        content = {"msgtype": "m.text", **MatrixBot.formatted_message_content(message)}
        future_to_deferred(self.client.room_send(room_id=target,
                                                 message_type="m.room.message",
                                                 content=content))

    @inlineCallbacks
    def notice(self, target, message, length=None):
        # direct messages will stay open until the user leaves the room
        # TODO: leave rooms when the last user left a room
        # TODO: remove this code duplication
        if target.startswith("@"):
            target = yield self.get_or_create_direct_message_room(target)
        elif target.startswith("#"):
            target = self.resolve_joined_room_alias(target)
        if target is None:
            return
        content = {"msgtype": "m.notice", **MatrixBot.formatted_message_content(message)}
        future_to_deferred(self.client.room_send(room_id=target,
                                                 message_type="m.room.message",
                                                 content=content))

    def join(self, channel):
        future_to_deferred(self.client.join(channel))

    @inlineCallbacks
    def leave(self, channel):
        response = yield future_to_deferred(self.client.room_leave(channel))
        if isinstance(response, MatrixResponses.RoomLeaveError):
            MatrixBot.log.error("Couldn't leave room {channel}", channel=channel)
            return
        future_to_deferred(self.client.room_forget(channel))

    def kick(self, channel, user, reason=""):
        future_to_deferred(self.client.room_kick(channel, user, reason))

    def ban(self, channel, user, reason=""):
        future_to_deferred(self.client.room_ban(channel, user, reason))

