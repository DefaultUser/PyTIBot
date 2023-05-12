# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2023>  <Sebastian Schmidt>

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

import re
from fnmatch import fnmatch
import itertools
import typing

from twisted.logger import Logger


logger = Logger()


def str_to_bytes(data):
    return bytes(data, "utf-8")


def bytes_to_str(data):
    return str(data, "utf-8")


def annotation_to_str(annotation):
    def type_to_str(t: type) -> str:
        return t.__name__
    origin = typing.get_origin(annotation)
    if origin == typing.Literal:
        return ", ".join(typing.get_args(annotation))
    if origin == typing.Union:
        args = typing.get_args(annotation)
        if type(None) in args: # -> typing.Optional
            return f"Optional[{', '.join(map(type_to_str, args[:-1]))}]"
        return ' | '.join(map(type_to_str, args))
    if isinstance(annotation, type):
        return type_to_str(annotation)
    return ""


def filter_dict(data, rule):
    """
    Returns True if rule applies to the dictionary
    """
    def _f(fragment, subdata):
        key_path, cmp, val = re.split(r"\s*(==|!=)\s*", fragment, maxsplit=1)
        temp = subdata
        key_path = key_path.split(".")
        for path_index, key_frag in enumerate(key_path):
            if key_frag == "*":
                if isinstance(temp, list):
                    star_replacements = map(str, range(len(temp)))
                else:
                    # otherwise it's a dict
                    star_replacements = temp.keys()
                return all(_f(".".join([star, *key_path[path_index + 1:]]) + cmp + val, temp)
                           for star in star_replacements)
            if isinstance(temp, list) and key_frag.isnumeric():
                key_frag = int(key_frag)
            temp = temp[key_frag]
        # values from rules are always strings
        temp = str(temp)
        if cmp == "!=":
            return all(not fnmatch(temp, v) for v in re.split(r"\s*\|\s*", val))
        return any(fnmatch(temp, v) for v in re.split(r"\s*\|\s*", val))

    try:
        if all(map(_f, re.split(r"\s+AND\s+", rule), itertools.repeat(data))):
            return True
    except Exception as e:
        logger.warn("Filter rule '{rule}' couldn't be applied: {e}",
                    rule=rule, e=e)
    return False
