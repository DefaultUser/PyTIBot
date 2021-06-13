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

import zope.interface


class IBotProvider(zope.interface.Interface):
    """Interface for objects that provide access to the running bot instance"""
    bot = zope.interface.Attribute("""The bot instance""")

    def get_bot():
        """Getter for the bot instance"""


class IBot(zope.interface.Interface):
    userlist = zope.interface.Attribute("""Dictionary containing all users per channel""")

    """Interface for all Bot backends"""
    def msg(target, message, length=None):
        """Send a message to a channel/room/user"""

    def notice(target, message, length=None):
        """Send a notice to a channel/room/user"""

    def join(channel):
        """Join a channel"""

    def leave(channel):
        """Leave a channel"""

    def kick(channel, user, reason=""):
        """Kick a user from a channel"""

    def ban(channel, user, reason=""):
        """Ban a user from a channel"""

    def enable_command(cmd, name, add_to_config=False):
        """Enable a command"""

    def enable_trigger(trigger, add_to_config=False):
        """Enable a trigger"""

    def ignore_user(user):
        """Test whether to ignore a user"""

    def user_info(user):
        """Get additional information about a user"""

    def get_auth(user):
        """Get a users auth"""

    def is_user_admin(user):
        """Check if a user is an admin for the bot"""

    def quit(message=None):
        """Quit the bot"""

