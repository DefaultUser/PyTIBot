# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2023>  <Sebastian Schmidt>

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

from util.formatting import ColorCodes
from util import formatting


def shutdown(bot):
    """Shut down the bot (admin function)"""
    def _shutdown(is_admin, channel, args):
        if is_admin:
            bot.quit(" ".join(args))
        else:
            bot.msg(channel, "I won't listen to you!")

    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_shutdown, channel, args)


def ignore(bot):
    """Modify the ignore list - use '+' or 'add' to extend, '-' or 'remove' \
to remove from the list, 'ls' or 'list' to show the list"""
    def _do_ignore(is_admin, sender, args):
        if is_admin:
            if len(args) == 1 and args[0].lower() in ("ls", "list"):
                ignorelist = bot.get_ignorelist()
                if ignorelist:
                    bot.notice(sender, ", ".join(ignorelist))
                else:
                    bot.notice(sender, "Ignorelist is empty")
            elif len(args) < 2:
                bot.notice(sender, "Too few arguments")
            else:
                task = args[0]
                nicks = args[1:]

                if task.lower() in ("+", "add"):
                    for nick in nicks:
                        # don't add to short nicks
                        # may ignore everything otherwise(regex)
                        if len(nick) > 3:
                            bot.add_to_ignorelist(nick)
                            bot.notice(sender, "Added {} to the ignore "
                                       "list".format(nick))
                        else:
                            bot.notice(sender, "Pattern {} too short, must "
                                       "have at least 3 chars".format(nick))
                elif task.lower() in ("-", "remove"):
                    for nick in nicks:
                        if bot.is_user_ignored(nick):
                            bot.remove_from_ignorelist(nick)
                            bot.notice(sender, "Removed {} from the ignore "
                                       "ignore list".format(nick))
                        else:
                            bot.notice(sender, "{} was not found in the "
                                       "ignore list".format(nick))
                else:
                    bot.notice(sender,
                               formatting.colored("Invalid call - check the"
                                                  " help", ColorCodes.red))

    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_do_ignore, sender, args)


def join(bot):
    """Join a channel ('join #channel=key' for password protected channels)"""
    def _join(is_admin, channels):
        if is_admin:
            for channel in channels:
                if "=" in channel:
                    channel, key = channel.split("=", 1)
                    # TODO: should the key be saved?
                    bot.join(channel, key)
                else:
                    bot.join(channel)

    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_join, args)


def part(bot):
    """Part channel(s)"""
    def _part(is_admin, channels):
        if is_admin:
            for c in channels:
                bot.leave(c)

    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_part, args)


def change_nick(bot):
    """Change the nick"""
    def _change_nick(is_admin, newnick):
        if is_admin:
            bot.setNick(newnick)

    while True:
        args, sender, channel = yield
        if args:
            bot.is_user_admin(sender).addCallback(_change_nick, args[0])


def about(bot):
    """Information about this bot"""
    info = ("PyTIBot - sources and info can be found at "
            "https://github.com/DefaultUser/PyTIBot")
    while True:
        args, sender, channel = yield
        bot.msg(channel, info)


def reload_config(bot):
    """Reload the config"""
    def _reload(is_admin):
        if is_admin:
            bot.reload()

    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_reload)

def kick(bot):
    """Kick a user from a channel (kick <#channel> <user>)"""
    def _do_kick(is_user_admin: bool, sender: str, args: list):
        if not is_user_admin:
            bot.notice(sender, formatting.colored("You're not my boss",
                                                  ColorCodes.red))
            return
        if len(args) != 2:
            bot.notice(sender, formatting.colored("Invalid call - wrong number"
                                                  " of arguments", ColorCodes.red))
            return
        channel, user = args
        bot.kick(channel, user)
    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_do_kick, sender, args)

def ban(bot):
    """ban a user from a channel (ban <#channel> <user>)"""
    def _do_ban(is_user_admin: bool, sender: str, args: list):
        if not is_user_admin:
            bot.notice(sender, formatting.colored("You're not my boss",
                                                  ColorCodes.red))
            return
        if len(args) != 2:
            bot.notice(sender, formatting.colored("Invalid call - wrong number"
                                                  " of arguments", ColorCodes.red))
            return
        channel, user = args
        bot.ban(channel, user)
        bot.kick(channel, user)
    while True:
        args, sender, channel = yield
        bot.is_user_admin(sender).addCallback(_do_ban, sender, args)
