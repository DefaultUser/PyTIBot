# PyTIBot - Formatting Helper
# Copyright (C) <2022-2023>  <Sebastian Schmidt>

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

from twisted.web.template import Tag, tags
from typing import Optional, Union

from util.formatting.common import ColorCodes, ColorsHex, good_contrast_with_black
from util.formatting.common import to_plaintext, Message
from util.formatting.html import parse_html, to_matrix
from util.formatting.irc import to_irc


def __ensure_available():
    """Ensure that these are available by importing util/formatting"""
    to_irc
    to_matrix
    to_plaintext
    good_contrast_with_black
    ColorsHex


def from_human_readable(text: str) -> Tag:
    return parse_html(text, allow_slots=True)


def colored(text: Message, fg: Union[ColorCodes, str],
            bg: Optional[Union[ColorCodes, str]] = None) -> Tag:
    new_tag = tags.font(text, color=fg)
    if bg:
        new_tag.attributes["background-color"] = bg
    return new_tag


def rainbow(text: Message) -> Tag:
    return Tag("rainbow")(text)


def underlined(text: Message) -> Tag:
    return tags.u(text)


def italic(text: Message) -> Tag:
    return tags.i(text)


def bold(text: Message) -> Tag:
    return tags.b(text)


def strike(text: Message) -> Tag:
    return Tag("del")(text)
