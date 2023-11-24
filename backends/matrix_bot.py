# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2021-2023>  <Sebastian Schmidt>

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
from nio import AsyncClient, ClientConfig, MatrixRoom, RoomMessageText, RoomMessageNotice, RoomMemberEvent
from nio import responses as MatrixResponses
from nio.api import RoomPreset
from zope.interface import implementer
from enum import Enum
from typing import Optional, Generator

from backends import Backends
from backends.common import setup_channelwatchers
from backends.interfaces import IBot

from util.aio_compat import future_to_deferred
from util import filesystem as fs
from util.formatting import to_matrix, to_plaintext, Message
from util.formatting.html import parse_html
from util.decorators import maybe_deferred
from util.config import Config


MessageType = Enum("MessageType", {"text": "m.text", "notice": "m.notice"})
# TODO: emote


@implementer(IBot)
class MatrixBot:
    log = Logger()

    def __init__(self, config: Config) -> None:
        self.config = config
        clientConfig = ClientConfig(store_sync_tokens=True)
        self.client = AsyncClient(config["Connection"]["server"],
                                  config["Connection"]["username"],
                                  device_id=config["Connection"].get("deviceID", None),
                                  config=clientConfig,
                                  store_path=fs.adirs.user_cache_dir)
        self.load_settings()
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_notice, RoomMessageNotice)
        self.client.add_event_callback(self.on_memberevent, RoomMemberEvent)

    @staticmethod
    def is_direct_message_room(room: MatrixRoom) -> bool:
        return room.is_group and room.member_count == 2

    def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        MatrixBot.log.info("{room.display_name} | {event.sender} : {event.body}",
                           room=room, event=event)
        room_id = room.room_id
        message = event.body
        if event.formatted_body:
            try:
                message = parse_html(event.formatted_body)
            except Exception as e:
                MatrixBot.log.warn("Failed to parse Matrix RoomMessageText: "
                                   f"{event.formatted_body=} | {e=}")
        # TODO: better support for edits
        try:
            if (event.source['content']['m.relates_to']['rel_type'] == "m.replace" and
                    isinstance(message, str)):
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
        if event.formatted_body:
            try:
                message = parse_html(event.formatted_body)
            except Exception as e:
                MatrixBot.log.warn("Failed to parse Matrix RoomMessageNotice: "
                                   f"{event.formatted_body=} | {e=}")
        # TODO: better support for edits
        try:
            if (event.source['content']['m.relates_to']['rel_type'] == "m.replace" and
                    isinstance(message, str)):
                message = message.removeprefix("* ")
        except KeyError:
            pass
        # channelwatchers
        if room_id in self.channelwatchers:
            for watcher in self.channelwatchers[room_id]:
                watcher.notice(event.sender, message)

    def on_memberevent(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        methodname = f"on_memberevent_{event.membership}"
        if hasattr(self, methodname):
            getattr(self, methodname)(room, event)
        else:
            MatrixBot.log.error("Unexpected RoomMemberEvent: {membership}",
                                membership=event.membership)

    def on_memberevent_invite(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        MatrixBot.log.info("{room.display_name} : {event.state_key} was invited",
                           room=room, event=event)

    def on_memberevent_join(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        if event.prev_membership == "join":
            # displayname or avatar changed
            return
        MatrixBot.log.info("{room.display_name} : {event.state_key} joined",
                           room=room, event=event)
        # TODO: channelwatchers

    def on_memberevent_leave(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        if event.state_key != event.sender:
            self.on_memberevent_kick(room, event)
            return
        if event.prev_membership == "ban":
            MatrixBot.log.info("{room.display_name} : {event.state_key} was unbanned",
                               room=room, event=event)
            return
        MatrixBot.log.info("{room.display_name} : {event.state_key} left",
                           room=room, event=event)
        self.leave_room_if_empty(room)
        # TODO: channelwatchers

    def on_memberevent_kick(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        MatrixBot.log.info("{room.display_name} : {event.state_key} was kicked "
                           "by {event.sender}", room=room, event=event)
        self.leave_room_if_empty(room)
        # TODO: channelwatchers

    def leave_room_if_empty(self, room: MatrixRoom) -> None:
        """Leave ad-hoc rooms when all other users left and no invite is open"""
        if room.is_group and room.member_count < 2:
            self.leave(room.room_id)

    def on_memberevent_ban(self, room: MatrixRoom, event: RoomMemberEvent) -> None:
        MatrixBot.log.info("{room.display_name} : {event.state_key} was banned",
                           room=room, event=event)
        # TODO: channelwatchers

    def load_settings(self) -> None:
        MatrixBot.log.info("Loading settings from {path}", path=self.config._path)
        self.force_dm_to_text = self.config["Connection"].get("force_dm_to_text", False)
        # TODO: setup aliases, triggers, commands
        self.channelwatchers = setup_channelwatchers(self, self.config.get("Channelmodules", {}),
                                                     Backends.MATRIX)

    def reload(self) -> None:
        self.config.load()
        self.load_settings()

    @maybe_deferred
    def get_auth(self, user: str) -> str:
        # the user handle is already unique
        return user

    def get_displayname(self, user: str, channel: str) -> str:
        return self.client.rooms[channel].users[user].display_name

    @maybe_deferred
    def is_user_admin(self, user: str) -> bool:
        return user in self.config["Connection"]["admins"]

    @property
    def userlist(self) -> dict[str, list[str]]:
        return {room_id: list(room.users.keys()) for room_id, room in self.client.rooms.items()}

    async def start(self) -> Deferred:
        response = await future_to_deferred(self.client.login(self.config["Connection"]["password"]))
        if isinstance(response, MatrixResponses.LoginError):
            MatrixBot.log.error("Error logging in {response}", response=response)
            raise EnvironmentError("Login failed")
        MatrixBot.log.info("Login successfull")
        # WARNING: don't await the signedOn method
        # it requires a first sync to know the already joined rooms
        self.signedOn()
        await future_to_deferred(self.client.sync_forever(timeout=30000, loop_sleep_time=1000,
                                                          full_state=True))
        return Deferred()

    @inlineCallbacks
    def signedOn(self) -> Generator[None, None, None]:
        yield future_to_deferred(asyncio.ensure_future(self.client.synced.wait()))
        for room in self.config["Connection"]["channels"]:
            if room not in self.client.rooms:
                self.join(room)

    def quit(self, ignored=None) -> None:
        self.stop()
        MatrixBot.log.info("Shutting down")
        reactor.stop()

    def stop(self) -> None:
        future_to_deferred(self.client.close())

    @staticmethod
    def formatted_message_content(message: Message) -> dict[str, str]:
        if isinstance(message, str):
            return {"body": message}
        unformatted = to_plaintext(message)
        formatted = to_matrix(message)
        return {"body": unformatted, "format": "org.matrix.custom.html",
                "formatted_body": formatted}

    @inlineCallbacks
    def get_or_create_direct_message_room(self, user: str) -> Generator[str, MatrixRoom, str]:
        for room_id, room in self.client.rooms.items():
            if MatrixBot.is_direct_message_room(room) and user in room.users:
                return room_id
        resp = yield future_to_deferred(self.client.room_create(is_direct=True, invite=[user],
                                        preset=RoomPreset.trusted_private_chat))
        return resp.room_id

    def resolve_joined_room_alias(self, target: str) -> Optional[str]:
        for room_id, room in self.client.rooms.items():
            if room.machine_name == target:
                return room_id
        else:
            MatrixBot.log.info("No room with alias {target} found", target=target)
            return None

    @inlineCallbacks
    def _send_message(self, msgtype: MessageType, target: str, message: Message):
        # direct messages will stay open until the user leaves the room
        if target.startswith("@"):
            target = yield self.get_or_create_direct_message_room(target)
            if self.force_dm_to_text:
                msgtype = MessageType.text
        elif target.startswith("#"):
            target = self.resolve_joined_room_alias(target)
        if target is None:
            return
        content = {"msgtype": msgtype.value,
                   **MatrixBot.formatted_message_content(message)}
        future_to_deferred(self.client.room_send(room_id=target,
                                                 message_type="m.room.message",
                                                 content=content))

    def msg(self, target: str, message: Message, length=None) -> None:
        self._send_message(MessageType.text, target, message)

    def notice(self, target: str, message: Message, length=None) -> None:
        self._send_message(MessageType.notice, target, message)

    def join(self, channel: str, _) -> None:
        future_to_deferred(self.client.join(channel))

    @inlineCallbacks
    def leave(self, channel: str):
        response = yield future_to_deferred(self.client.room_leave(channel))
        if isinstance(response, MatrixResponses.RoomLeaveError):
            MatrixBot.log.error("Couldn't leave room {channel}", channel=channel)
            return
        future_to_deferred(self.client.room_forget(channel))

    def kick(self, channel: str, user: str, reason: str = "") -> None:
        future_to_deferred(self.client.room_kick(channel, user, reason))

    def ban(self, channel: str, user: str, reason: str = "") -> None:
        future_to_deferred(self.client.room_ban(channel, user, reason))
