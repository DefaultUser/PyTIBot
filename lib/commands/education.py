# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015-2020>  <Sebastian Schmidt>

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

import random
from twisted.internet import threads, defer
from treq import get
from util import formatting

try:
    import xmlrpclib
except ImportError:
    import xmlrpc.client as xmlrpclib


def rand(bot):
    """Randomizer, opt args: 'range int1 int2', 'frange float1 float2' or \
list of choices"""
    while True:
        args, sender, senderhost, channel = yield
        try:
            if not args:
                result = random.choice(["Heads", "Tails"])
            elif args[0].lower() == "range":
                result = str(random.randint(int(args[1]), int(args[2])))
            elif args[0].lower() == "frange":
                result = str(random.uniform(float(args[1]), float(args[2])))
            else:
                result = random.choice(args)
        except (IndexError, ValueError):
            result = formatting.colored("Invalid call - check the help",
                                        formatting.IRCColorCodes.red)
        bot.msg(channel, result)


def search_pypi(bot):
    """Search for python packages from PyPI - usage: (search|info) packages"""
    _baseurl = "https://pypi.python.org/pypi/{}/json"
    _maxlen = 400
    _client = xmlrpclib.ServerProxy("https://pypi.python.org/pypi")

    def _handle_search_results(results, channel):
        packagenames = [item['name'] for item in results]
        num_packages = len(packagenames)
        if num_packages < 10:
            show_result = ", ".join(packagenames)
        else:
            show_result = ", ".join(packagenames[:10]) + " ..."
        bot.msg(channel, str(num_packages) + " packages found: " + show_result)

    @defer.inlineCallbacks
    def _handle_info_results(results, channel):
        data = yield results.json()
        name = data["info"]["name"].encode("utf-8")
        author = data["info"]["author"].encode("utf-8")
        description = data["info"]["description"].encode("utf-8")
        description = description.replace("\n", " ")
        if len(description) > _maxlen:
            description = description[:_maxlen] + "..."
        bot.msg(channel, "{} by {}: {}".format(formatting.bold(name, True),
                                               formatting.bold(author, True),
                                               description), length=510)
        bot.msg(channel, data["info"]["package_url"].encode("utf-8"))

    def _handle_error(error, arg, channel):
        bot.msg(channel, "No such package: {}".format(arg))

    while True:
        args, sender, senderhost, channel = yield
        if len(args) < 2 or not args[0] in ["search", "info"]:
            bot.msg(channel, formatting.colored("Invalid call - check the help",
                                                formatting.IRCColorCodes.red))
            continue

        if args[0] == "search":
            for package in args[1:]:
                d = threads.deferToThread(_client.search, ({'name': package}))
                d.addCallback(_handle_search_results, channel)
        elif args[0] == "info":
            for package in args[1:]:
                url = _baseurl.format(package)
                d = get(url)
                d.addCallback(_handle_info_results, channel)
                d.addErrback(_handle_error, package, channel)
