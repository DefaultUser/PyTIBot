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

import random
import os
import sys
from twisted.internet import defer
from twisted.logger import Logger
from treq import get
from bidict import bidict
import argparse

from util import filesystem as fs
from util.formatting import ColorCodes
from util import formatting


log = Logger()


morse_dict = bidict({'A': '.-', 'B': '-...', 'C': '-.-.',
                     'D': '-..', 'E': '.', 'F': '..-.',
                     'G': '--.', 'H': '....', 'I': '..',
                     'J': '.---', 'K': '-.-', 'L': '.-..',
                     'M': '--', 'N': '-.', 'O': '---',
                     'P': '.--.', 'Q': '--.-', 'R': '.-.',
                     'S': '...', 'T': '-', 'U': '..-',
                     'V': '...-', 'W': '.--', 'X': '-..-',
                     'Y': '-.--', 'Z': '--..',
                     '0': '-----', '1': '.----', '2': '..---',
                     '3': '...--', '4': '....-', '5': '.....',
                     '6': '-....', '7': '--...', '8': '---..',
                     '9': '----.', ' ': ''})


def morse(bot):
    """Translate to morse code"""
    while True:
        args, sender, channel = yield
        message = " ".join(args)
        morsecode = []
        for char in message:
            morsecode.append(morse_dict.get(char.upper(), char))
        morsecode = " ".join(morsecode)
        bot.msg(channel, morsecode, length=510)


def unmorse(bot):
    """Translate from morse code"""
    while True:
        args, sender, channel = yield
        newstring = ""
        for char in args:
            newstring += morse_dict.inv.get(char, char)
        bot.msg(channel, newstring.lower(), length=510)


def joke(bot):
    """Chuck Norris jokes from http://icndb.com"""
    url = "http://api.icndb.com/jokes/random/1"

    @defer.inlineCallbacks
    def _tell_joke(response, channel, name=None):
        data = yield response.json()
        cnjoke = data['value'][0]['joke']
        cnjoke = cnjoke.replace("&quot;", "\"")
        if name:
            cnjoke = cnjoke.replace("Chuck Norris", name)
        bot.msg(channel, str(cnjoke), length=510)

    while True:
        args, sender, channel = yield
        get(url).addCallback(_tell_joke, channel, " ".join(args))


if sys.version_info.major == 3 and sys.version_info.minor < 9:
    class ArgParser(argparse.ArgumentParser):
        def __init__(self, *args, exit_on_error=True, **kwargs):
            super().__init__(*args, **kwargs)
            self.exit_on_error = exit_on_error

        def error(self, message):
            if self.exit_on_error:
                super().error(message)
            else:
                raise argparse.ArgumentError(None, message)
else:
    ArgParser = argparse.ArgumentParser

def fortune(bot):
    """Unix fortune: fortune --list for available fortunes, -l to \
allow long fortunes, -o to allow offensive fortunes"""
    paths = [r"/usr/share/fortune/", r"/usr/share/games/fortune/",
             r"/usr/share/fortunes/", r"/usr/share/games/fortunes/",
             fs.get_abs_path("fortunes")]
    num_lines_short = 3
    parser = ArgParser(exit_on_error=False)
    parser.add_argument("-l", action='store_true')
    parser.add_argument("-o", action='store_true')
    parser.add_argument("--list", action='store_true')
    parser.add_argument("files", nargs='*')

    def _display_filename(filename):
        """
        Strip the fortune base path
        """
        for path in paths:
            if filename.startswith(path):
                return filename.replace(path, "", 1).lstrip("/")

    def _find_files(offensive=False):
        """
        Find all fortune files in the system
        """
        fortune_files = []
        # only one should be used, but check both anyways
        for path in paths:
            if not os.path.isdir(path):
                continue
            for root, dirs, files in os.walk(path):
                for f in files:
                    if "." in f:
                        continue
                    if offensive or not _display_filename(root) == 'off':
                        fortune_files.append(os.path.join(root, f))
        return fortune_files

    def _get_random_fortune(filename, onlyshort=True):
        """
        Get a random fortune out of the file <filename>
        """
        with open(filename) as f:
            data = f.read()
        fortunes = data.split("\n%\n")
        # remove empty strings
        while "" in fortunes:
            fortunes.remove("")
        if onlyshort:
            for fortune in fortunes[:]:
                # last line has no "\n"
                if fortune.count("\n") >= num_lines_short:
                    fortunes.remove(fortune)
        if not fortunes:
            return "No fortunes found"
        fortune = random.choice(fortunes)
        if _display_filename(filename).startswith("off/"):
            fortune = fortune.encode("rot13")
        return fortune

    while True:
        args, sender, channel = yield
        try:
            options, unknown_options = parser.parse_known_args(args)
        except Exception as e:
            log.warn("Error parsing fortune arguments: {e}", e=e)
            bot.msg(channel, formatting.colored("Invalid input for fortune",
                                                ColorCodes.red))
            continue
        if unknown_options:
            log.warn("Fortune: Unknown options: {options}",
                     options=unknown_options)
            bot.msg(channel, formatting.colored("Invalid input for fortune",
                                                ColorCodes.red))
            continue
        if options.list:
            fortunes = []
            for f in _find_files(offensive=options.o):
                fortunes.append(_display_filename(f))
            bot.msg(channel, "Available fortunes: {}".format(
                ", ".join(fortunes)))
        else:
            considered_files = []
            only_short = not options.l
            if not options.files:
                # Don't use offensive fortunes by default
                considered_files = _find_files(offensive=options.o)
            else:
                for arg in options.files:
                    for f in _find_files(offensive=True):
                        if arg == _display_filename(f):
                            considered_files.append(f)
                            break
            # nothing found?
            if not considered_files:
                bot.msg(channel, "No fortunes found")
            else:
                result = _get_random_fortune(random.choice(considered_files),
                                             only_short)
                bot.msg(channel, result)
