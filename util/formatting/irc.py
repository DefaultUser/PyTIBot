# PyTIBot - Formatting Helper
# Copyright (C) <2015-2023>  <Sebastian Schmidt, Mattia Basaglia>

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

from collections import deque
import dataclasses
import re
from twisted.web.template import Tag, slot
from twisted.words.protocols.irc import stripFormatting as stripIrcFormatting
from typing import Generator
from zope import interface

from util.formatting import common
from util.formatting.common import ColorCodes, Style, StyledTextFragment

# https://modern.ircdocs.horse/formatting.html

## \brief Token to start underlined text
_UNDERLINE = "\x1f"
## \brief Token to start bold text
_BOLD = "\x02"
## \brief Token to start colored text
_COLOR = "\x03"
## \brief Token to start italic text
_ITALIC = "\x1d"
## \brief Token to start striked text
_STRIKE = "\x1e"
## \brief Token to end formatted text
_NORMAL = "\x0f"


_irc_parser_pattern = re.compile("(\x1f)|(\x02)|(\x03)(\\d{1,2}(,\\d{1,2})?)?|"
                                 "(\x1d)|(\x1e)|(\x0f)")

def parse_irc(message: str) -> Tag:
    result = Tag("")
    stack = deque()
    stack.append(result)
    style = Style()

    def append_new_tag(tagName: str):
        new_tag = Tag(tagName)
        stack[-1].children.append(new_tag)
        stack.append(new_tag)

    def pop_last_of(tagName: str):
        temp_stack = deque()
        while stack and stack[-1].tagName != tagName:
            temp_stack.append(stack.pop())
        stack.pop()
        while temp_stack:
            old_tag = temp_stack.pop()
            append_new_tag(old_tag.tagName)
            stack[-1].attributes = old_tag.attributes

    substrings = _irc_parser_pattern.split(message)
    if len(substrings) % 9:
        if substrings[0]:
             result.children.append(substrings[0])
        start = 1
    else:
        start = 0
    for i in range(start, len(substrings), 9):
        if substrings[i]:
            if style.underline:
                pop_last_of("u")
            else:
                append_new_tag("u")
            style.underline = not style.underline
        if substrings[i+1]:
            if style.bold:
                pop_last_of("b")
            else:
                append_new_tag("b")
            style.bold = not style.bold
        if substrings[i+2]:
            if not substrings[i+3] and (style.fg or style.bg):
                pop_last_of("font")
                style.fg = None
                style.bg = None
            elif "," in substrings[i+3]:
                if style.fg or style.bg:
                    pop_last_of("font")
                # TODO: handle color codes > 15 better
                style.fg, style.bg = [ColorCodes(val.zfill(2)) for val in
                                      substrings[i+3].split(",")]
                append_new_tag("font")
                stack[-1].attributes["color"] = style.fg
                stack[-1].attributes["background-color"] = style.bg
            else:
                if style.fg or style.bg:
                    pop_last_of("font")
                # TODO: handle color codes > 15 better
                style.fg = ColorCodes(substrings[i+3].zfill(2))
                append_new_tag("font")
                stack[-1].attributes["color"] = style.fg
                if style.bg:
                    stack[-1].attributes["background-color"] = style.bg
        if substrings[i+5]:
            if style.italic:
                pop_last_of("i")
            else:
                append_new_tag("i")
            style.italic = not style.italic
        if substrings[i+6]:
            if style.strike:
                pop_last_of("del")
            else:
                append_new_tag("del")
            style.strike = not style.strike
        if substrings[i+7]:
            style = Style()
            stack.clear()
            stack.append(result)
        if substrings[i+8]:
            stack[-1].children.append(substrings[i+8])
    return result


@interface.implementer(common.ITagProcessor)
class TagToIrcFormatter:
    # TODO: support <hn>
    def __init__(self):
        self.buffer = ""
        self._style_stack = deque()
        self._style_stack.append(Style())
        self._slotDataStack = deque()
        self._slotDataStack.append({})
        self._rainbow_position = 0
        self._rainbow_content_length = 0
        self._rainbow_tag_depth = -1

    def handle_slot(self, slt: slot):
        self.handle_data(self._slotDataStack[-1][slt.name])

    def handle_newline(self):
        if stripIrcFormatting(self.buffer) == "":
            return
        style = self._style_stack[-1]
        self.buffer += "\n"
        if style.bold:
            self.buffer += _BOLD
        if style.italic:
            self.buffer += _ITALIC
        if style.underline:
            self.buffer += _UNDERLINE
        if style.strike:
            self.buffer += _UNDERLINE
        if style.fg:
            self.buffer += _COLOR + style.fg.value
            if style.bg:
                self.buffer += "," + style.bg.value

    def handle_starttag(self, tag: Tag):
        style = dataclasses.replace(self._style_stack[-1])
        slotData = {**self._slotDataStack[-1], **(tag.slotData or {})}
        self._slotDataStack.append(slotData)
        tagName = tag.tagName
        if common.is_bold(tag) and not style.bold:
            style.bold = True
            self.buffer += _BOLD
        if common.is_italic(tag) and not style.italic:
            style.italic = True
            self.buffer += _ITALIC
        if common.is_del(tag) and not style.strike:
            style.strike = True
            self.buffer += _STRIKE
        if common.is_underlined(tag) and not style.underline:
            style.underline = True
            self.buffer += _UNDERLINE
        elif tagName == "rainbow":
            self._rainbow_content_length = len(common.to_plaintext(
                tag.clone().fillSlots(**slotData)))
            self._rainbow_tag_depth = len(self._style_stack)
        # TODO: same for <hn>
        if common.is_display_block(tag):
            self.handle_newline()
        if (common.is_colored(tag) and self._rainbow_content_length == 0):
            fg = tag.attributes.get("color", None)
            bg = tag.attributes.get("background-color", None)
            if fg and not (fg == style.fg and bg == style.bg):
                if isinstance(fg, Tag):
                    fg = common.handle_attribute_tag(fg, self._slotDataStack)
                if not isinstance(fg, ColorCodes):
                    fg = common.closest_colorcode(fg)
                self.buffer += _COLOR + fg.value
                style.fg = fg
                if bg:
                    if isinstance(bg, Tag):
                        bg = common.handle_attribute_tag(bg, self._slotDataStack)
                    if not isinstance(bg, ColorCodes):
                        bg = common.closest_colorcode(bg)
                    self.buffer += "," + bg.value
                    style.bg = bg
        elif tagName == "br":
            self.handle_newline()
        self._style_stack.append(style)

    def handle_data(self, data: str):
        def prepare_text_fragment(fragment):
            style = self._style_stack[-1]
            if self._rainbow_content_length == 0:
                return fragment
            ret = ""
            for char in fragment:
                new_color = rainbow_color(
                        self._rainbow_position/self._rainbow_content_length,
                        common.RAINBOW_COLORS)
                self._rainbow_position += 1
                if new_color != style.fg:
                    ret += _COLOR + new_color.value
                    # set the color for all styles in the stack after the rainbow tag
                    for i in range(self._rainbow_tag_depth, len(self._style_stack)):
                        self._style_stack[i].fg = new_color
                ret += char
            return ret

        fragments = data.split("\n")
        self.buffer += prepare_text_fragment(fragments[0])
        for item in fragments[1:]:
            self.handle_newline()
            self.buffer += prepare_text_fragment(item)

    def handle_endtag(self, tag: Tag):
        style = self._style_stack.pop()
        self._slotDataStack.pop()
        parent_style = self._style_stack[-1]
        control_char = None
        tagName = tag.tagName
        if common.is_bold(tag) and not parent_style.bold:
            control_char = _BOLD
        if common.is_italic(tag) and not parent_style.italic:
            control_char = _ITALIC
        if common.is_del(tag) and not parent_style.strike:
            control_char = _STRIKE
        if common.is_underlined(tag) and not parent_style.underline:
            control_char = _UNDERLINE
        if common.is_colored(tag) or tag.tagName == "rainbow":
            current_fg = style.fg
            current_bg = style.bg
            parent_fg = parent_style.fg
            parent_bg = parent_style.bg
            if parent_fg is None and current_fg is not None:
                control_char = _COLOR
            elif parent_fg is not None:
                if parent_bg is None and current_bg is not None:
                    control_char = _COLOR*2 + parent_fg.value
                elif parent_bg is not None and current_bg != parent_bg:
                    control_char = _COLOR + parent_fg.value + "," + parent_bg.value
                elif parent_fg != current_fg and parent_bg == current_bg:
                    control_char = _COLOR + parent_fg.value
        if control_char:
            self.buffer += control_char
        if common.is_display_block(tag):
            self.handle_newline()
        if tag.tagName == "rainbow":
            self._rainbow_position = 0
            self._rainbow_content_length = 0
        elif tag.tagName == "a" and (href:=tag.attributes.get("href", None)):
            self.buffer += f" ({href})"


def to_irc(data: Tag|str) -> str:
    if isinstance(data, str):
        return data
    formatter = TagToIrcFormatter()
    common._processStyledText(data, formatter)
    result = formatter.buffer
    while "\n" in result:
        beginning, last_line = result.rsplit("\n", 1)
        if stripIrcFormatting(last_line) == "":
            result = beginning
        else:
            break
    return result


# TODO: refactor so that it returns internal representation and move to __init__.py
def colored(text: str, fgcolor: ColorCodes, bgcolor: ColorCodes=None,
            endtoken: bool=True) -> str:
    """
    \brief Colorize a string
    \param fgcolor ColorCodes color to be used as text color
    \param bgcolor ColorCodes color to be used as background color, can be None
    \param endtoken Send the colortoken at the end to end colored text
    \returns A string with IRC colors if color is valid
    """
    if not isinstance(text, str):
        text = str(text)
    if bgcolor:
        colorinfo = "{},{}".format(fgcolor.value, bgcolor.value)
    else:
        colorinfo = fgcolor.value
    if endtoken:
        return _COLOR + colorinfo + text + _COLOR
    return _COLOR + colorinfo + text


def rainbow_color(factor: float, colors: list[ColorCodes])-> ColorCodes:
    """
    \brief Return a color in the rainbow
    \param factor        A value in [0,1]
    \param colors        Color names to be featured in the rainbow
    \returns The numerical value of the selected color
    """
    return colors[int(factor*len(colors))]


def rainbow(text: str, colors: list[ColorCodes] = [
        ColorCodes.red, ColorCodes.dark_yellow, ColorCodes.green, ColorCodes.cyan,
        ColorCodes.blue, ColorCodes.magenta]) -> str:
    """
    \brief Colorize a string as a rainbow
    \param text          Input text
    \param colors        Color names to be featured in the rainbow
    \returns A string with valid IRC color codes inserted at the right
    positions
    """
    if not isinstance(text, str):
        text = str(text)
    ret = ""
    color = ""
    for index, char in enumerate(text):
        newcolor = rainbow_color(float(index)/len(text), colors)
        if newcolor != color:
            color = newcolor
            ret += _COLOR + color.value
        ret += char
    return ret + _COLOR


def underlined(text: str, endtoken: bool=True) -> str:
    """
    \brief Return a underlined string
    \param endtoken end the underlined text
    \returns A underlined string
    """
    if not isinstance(text, str):
        text = str(text)
    if endtoken:
        return _UNDERLINE + text + _UNDERLINE
    return _UNDERLINE + text


def italic(text: str, endtoken: bool=True) -> str:
    """
    \brief Return a italic string
    \param endtoken end the italic text
    \returns A italic string
    """
    if not isinstance(text, str):
        text = str(text)
    if endtoken:
        return _ITALIC + text + _ITALIC
    return _ITALIC + text


def bold(text: str, endtoken: bool=True) -> str:
    """
    \brief Return a bold string
    \param endtoken end the bold text
    \returns A bold string
    """
    if not isinstance(text, str):
        text = str(text)
    if endtoken:
        return _BOLD + text + _BOLD
    return _BOLD + text
# END TODO: refactor so that it returns internal representation


_format_pattern = re.compile("(\x1f)|(\x02)|(\x03)(\\d{1,2}(,\\d{1,2})?)?|"
                            "(\x1d)|(\x0f)")
# underline, bold, color, (fg,bg?), (,bg), italic, normal

def _extract_irc_style(text: str) -> Generator[StyledTextFragment, None, None]:
    """
    \brief Extract IRC formatting information from string
    """
    # <span style="color:{color}">{substr}</span>
    # <span style="background-color:{bg_color}">{substr}</span>
    # <span style="text-decoration:underline">{substr}</span>
    # <span style="font-style:italic">{substr}</span>
    # <span style="font-weight:bold">{substr}</span>
    substrings = _format_pattern.split(text)
    style = Style()
    if len(substrings) % 8:
        # first substring has no formatting information
        if substrings[0]:
            yield StyledTextFragment(text=substrings[0], style=style)
        start = 1
    else:
        start = 0
    for i in range(start, len(substrings), 8):
        style = dataclasses.replace(style)
        if substrings[i]:
            style.underline = not style.underline
        if substrings[i+1]:
            style.bold = not style.bold
        if substrings[i+2]:
            if not substrings[i+3]:
                style.fg = None
                style.bg = None
            elif "," in substrings[i+3]:
                # TODO: handle color codes > 15 better
                style.fg, style.bg = [ColorCodes(val.zfill(2)) for val in
                                      substrings[i+3].split(",")]
            else:
                # TODO: handle color codes > 15 better
                style.fg = ColorCodes(substrings[i+3].zfill(2))
        if substrings[i+5]:
            style.italic = not style.italic
        if substrings[i+6]:
            # big reset switch
            style = Style()
        if substrings[i+7]:
            yield StyledTextFragment(text=substrings[i+7], style=style)


_colorpat = re.compile(r"\$COLOR(\((\d{{1,2}}|{colors})(,(\d{{1,2}}|{colors}))?\))?".format(
    colors="|".join([color.name for color in ColorCodes])))
_rainbowpat = re.compile(r"\$RAINBOW\(([^)]+)\)")
# TODO: refactor so that it returns internal representation and move to __init__.py
def from_human_readable(text):
    """
    \brief Convert human readable formatting information to IRC formatting
    """
    def colorname_sub(match):
        fg = match.group(2)
        if fg is not None:
            if fg.isdecimal():
                fg = ColorCodes(f"{fg:02}")
            else:
                fg = ColorCodes[fg]
        bg = match.group(4)
        if bg is not None:
            if bg.isdecimal():
                bg = ColorCodes(f"{bg:02}")
            else:
                bg = ColorCodes[bg]
        if fg and bg:
            col_code = fg.value + "," + bg.value
        elif fg:
            col_code = fg.value
        else:
            col_code = ""
        return _COLOR + col_code
    # Replace colors
    text = _colorpat.sub(colorname_sub, text)
    text = _rainbowpat.sub(lambda match: rainbow(match.group(1)),
                          text)
    # other formatting
    text = text.replace("$UNDERLINE", _UNDERLINE)
    text = text.replace("$BOLD", _BOLD)
    text = text.replace("$ITALIC", _ITALIC)
    text = text.replace("$NOFORMAT", _NORMAL)
    return text


