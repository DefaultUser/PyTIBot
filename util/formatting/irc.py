# PyTIBot - Formatting Helper
# Copyright (C) <2015-2022>  <Sebastian Schmidt, Mattia Basaglia>

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

import dataclasses
import re
from typing import Generator

from util.formatting.common import ColorCodes, Style, StyledTextFragment


## \brief Token to start underlined text
_UNDERLINE = "\x1f"
## \brief Token to start bold text
_BOLD = "\x02"
## \brief Token to start colored text
_COLOR = "\x03"
## \brief Token to start italic text
_ITALIC = "\x1d"
## \brief Token to end formatted text
_NORMAL = "\x0f"


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


