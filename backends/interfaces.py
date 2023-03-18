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

from typing import Optional
import zope.interface

from util.formatting import Message


class IBot(zope.interface.Interface):
    """Interface for all Bot backends"""
    userlist: dict[str,list[str]] = zope.interface.Attribute("""Dictionary containing all users per channel""")

    def setNick(newnick: str):
        """Set a new nickname"""

    def msg(target: str, message: Message, length: Optional[int]=None):
        """Send a message to a channel/room/user"""

    def notice(target: str, message: Message, length: Optional[int]=None):
        """Send a notice to a channel/room/user"""

    def describe(channel: str, action: str):
        """Do an action/emote"""

    def join(channel: str):
        """Join a channel"""

    def leave(channel: str):
        """Leave a channel"""

    def kick(channel: str, user: str, reason: str=""):
        """Kick a user from a channel"""

    def ban(channel: str, user: str, reason: str=""):
        """Ban a user from a channel"""

    def enable_command(cmd: str, name: str, add_to_config: bool=False):
        """Enable a command"""

    def enable_trigger(trigger: str, add_to_config: bool=False):
        """Enable a trigger"""

    def ignore_user(user: str) -> bool:
        """Test whether to ignore a user"""

    def get_auth(user: str) -> str:
        """Get a users auth"""

    def is_user_admin(user: str) -> bool:
        """Check if a user is an admin for the bot"""

    def reload():
        """(Re)load settings from config"""

    def quit(message: Optional[str]=None):
        """Quit the bot"""


class IBotProvider(zope.interface.Interface):
    """Interface for objects that provide access to the running bot instance"""
    bot: IBot = zope.interface.Attribute("""The bot instance""")

    def get_bot() -> Optional[IBot]:
        """Getter for the bot instance"""

