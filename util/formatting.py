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

from enum import IntEnum, Enum
import re
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from dataclasses import dataclass
from html import escape as htmlescape
from typing import Generator, NamedTuple
from twisted.web.template import tags, Tag


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

url_pat = re.compile(r"(((https?)|(ftps?)|(sftp))://[^\s\"\')]+)")

## \brief Maps color names to the corresponding mIRC numerical values
## (as a two-digit strings)
## These colors shall serve as a generic set of colors used throughout the application
ColorCodes = Enum("ColorCodes", {
    "white": "00",
    "black": "01",
    "dark_blue": "02",
    "dark_green": "03",
    "red": "04",
    "dark_red": "05",
    "dark_magenta": "06",
    "dark_yellow": "07",
    "yellow": "08",
    "green": "09",
    "dark_cyan": "10",
    "cyan": "11",
    "blue": "12",
    "magenta": "13",
    "dark_gray": "14",
    "gray": "15"
})

## \brief hex color codes for mIRC numerical values
ColorsHex = {
    ColorCodes.white: "#FFFFFF",
    ColorCodes.black: "#000000",
    ColorCodes.dark_blue: "#00007F",
    ColorCodes.dark_green: "#009300",
    ColorCodes.red: "#FF0000",
    ColorCodes.dark_red: "#7F0000",
    ColorCodes.dark_magenta: "#9C009C",
    ColorCodes.dark_yellow: "#FC7F00",
    ColorCodes.yellow: "#FFFF00",
    ColorCodes.green: "#00FC00",
    ColorCodes.dark_cyan: "#009393",
    ColorCodes.cyan: "#00FFFF",
    ColorCodes.blue: "#0000FC",
    ColorCodes.magenta: "#FF00FF",
    ColorCodes.dark_gray: "#7F7F7F",
    ColorCodes.gray: "#D2D2D2"}

# dict that indicates if a color is a good background for black text
good_contrast_with_black = {
    ColorCodes.white: True,
    ColorCodes.black: False,
    ColorCodes.dark_blue: False,
    ColorCodes.dark_green: True,
    ColorCodes.red: True,
    ColorCodes.dark_red: True,
    ColorCodes.dark_magenta: True,
    ColorCodes.dark_yellow: True,
    ColorCodes.yellow: True,
    ColorCodes.green: True,
    ColorCodes.dark_cyan: True,
    ColorCodes.cyan: True,
    ColorCodes.blue: True,
    ColorCodes.magenta: True,
    ColorCodes.dark_gray: True,
    ColorCodes.gray: True
}

ANSI_CSI = "\x1b["
ANSI_FG_START = 30
ANSI_BG_START = 40
ANSIColors = IntEnum("ANSIColors", "black red green yellow blue magenta cyan white",
                     start=0)


@dataclass
class Style:
    underline: bool | None = None
    bold: bool | None = None
    italic: bool | None = None
    fg: ColorCodes | None = None
    bg: ColorCodes | None = None

class StyledTextFragment(NamedTuple):
    text: str
    style: Style | None = None


def colored(text, fgcolor, bgcolor=None, endtoken=True):
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


def rainbow_color(factor, colors):
    """
    \brief Return a color in the rainbow
    \param factor        A value in [0,1]
    \param colors        Color names to be featured in the rainbow
    \returns The numerical value of the selected color
    """
    return colors[int(factor*len(colors))]


def rainbow(text, colors=[ColorCodes.red, ColorCodes.dark_yellow, ColorCodes.green,
                          ColorCodes.cyan, ColorCodes.blue, ColorCodes.magenta]):
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


def underlined(text, endtoken=True):
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


def italic(text, endtoken=True):
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


def bold(text, endtoken=True):
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


format_pattern = re.compile("(\x1f)|(\x02)|(\x03)(\\d{1,2}(,\\d{1,2})?)?|"
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
    substrings = format_pattern.split(text)
    style = Style()
    if len(substrings) % 8:
        # first substring has no formatting information
        yield StyledTextFragment(text=substrings[0], style=style)
        start = 1
    else:
        start = 0
    for i in range(start, len(substrings), 8):
        if substrings[i]:
            style.underline = not style.underline
        if substrings[i+1]:
            style.bold = not style.bold
        if substrings[i+2]:
            if not substrings[i+3]:
                style.fg = None
                style.bg = None
            elif "," in substrings[i+3]:
                style.fg, style.bg = [ColorCodes(val.zfill(2)) for val in
                                      substrings[i+3].split(",")]
            else:
                style.fg = ColorCodes(substrings[i+3].zfill(2))
        if substrings[i+5]:
            style.italic = not style.italic
        if substrings[i+6]:
            # big reset switch
            style = Style()
        yield StyledTextFragment(text=substrings[i+7], style=style)

def _style_html_string(style):
    styles = []
    if style.underline:
        styles.append("text-decoration:underline")
    if style.bold:
        styles.append("font-weight:bold")
    if style.fg:
        styles.append("color:{}".format(ColorsHex[style.fg]))
    if style.bg:
        styles.append("background-color:{}".format(
            ColorsHex[style.bg]))
    if style.italic:
        styles.append("font-style:italic")
    return styles

def _styled_fragment_to_html(fragment: StyledTextFragment,
                             link_urls: bool=True) -> str:
    styles = _style_html_string(fragment.style)
    if link_urls:
        text = url_pat.sub(r"<a href='\1'>\1</a>", fragment.text)
    if styles:
        return '<span style="{style}">{text}</span>'.format(
            style=";".join(styles), text=fragment.text)
    return fragment.text


def to_html(text, link_urls=True):
    """
    \brief Convert a string with IRC formatting information to html formatting
    """
    html = ""
    for frag in _extract_irc_style(htmlescape(text)):
        html += _styled_fragment_to_html(frag, link_urls)
    return html


def _styled_fragment_to_matrix(fragment: StyledTextFragment) -> str:
    text, style = fragment
    if style.underline:
        text = "<u>"+text+"</u>"
    if style.bold:
        text = "<b>"+text+"</b>"
    if style.italic:
        text = "<i>"+text+"</i>"
    color = ""
    if style.fg:
        # 'color' seems to be better supported than 'data-mx-color'
        color += " color=\""+ColorsHex[style.fg]+"\""
    if style.bg:
        # 'background-color' is not mentioned in the spec and doesn't seem to be
        # supported in clients
        color += " data-mx-bg-color=\""+ColorsHex[style.bg]+"\""
    if color:
        text = "<font"+color+">"+text+"</font>"
    return text


def to_matrix(text):
    """
    \brief Convert a string with IRC formatting information to matrix format
    """
    result = ""
    for frag in _extract_irc_style(htmlescape(text)):
        result += _styled_fragment_to_matrix(frag)
    return result


def _styled_fragment_to_tags(fragment: StyledTextFragment,
                             link_urls: bool=True) -> str | Tag:
    text, style = fragment
    styles = _style_html_string(style)
    if link_urls:
        if url_pat.search(text):
            frag_list = []
            start = 0
            for match in url_pat.finditer(text):
                frag_list.append(text[start:match.start()])
                link = match.group(0)
                frag_list.append(tags.a(link, href=link))
                start = match.end()
            if start < len(text):
                frag_list.append(text[start:])
            text = frag_list
    if styles:
        return tags.span(text, style=";".join(styles))
    return text


def to_tags(text, link_urls=True):
    """
    \brief Convert a string with IRC formatting information to web template tags
    """
    # <span style="color:{color}">{substr}</span>
    # <span style="background-color:{bg_color}">{substr}</span>
    # <span style="text-decoration:underline">{substr}</span>
    # <span style="font-style:italic">{substr}</span>
    # <span style="font-weight:bold">{substr}</span>
    t = []
    for frag in _extract_irc_style(text):
        t.append(_styled_fragment_to_tags(frag, link_urls))
    return t


colorpat = re.compile(r"\$COLOR(\((\d{{1,2}}|{colors})(,(\d{{1,2}}|{colors}))?\))?".format(
    colors="|".join([color.name for color in ColorCodes])))
rainbowpat = re.compile(r"\$RAINBOW\(([^)]+)\)")
def from_human_readable(text):
    """
    \brief Convert human readable formatting information to IRC formatting
    """
    def colorname_sub(match):
        fg = match.group(2)
        if fg is not None:
            if fg.isdecimal():
                fg = ColorCodes(fg)
            else:
                fg = ColorCodes[fg]
        bg = match.group(4)
        if bg is not None:
            if bg.isdecimal():
                bg = ColorCodes(bg)
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
    text = colorpat.sub(colorname_sub, text)
    text = rainbowpat.sub(lambda match: rainbow(match.group(1)),
                          text)
    # other formatting
    text = text.replace("$UNDERLINE", _UNDERLINE)
    text = text.replace("$BOLD", _BOLD)
    text = text.replace("$ITALIC", _ITALIC)
    text = text.replace("$NOFORMAT", _NORMAL)
    return text


def ansi_colored(text, fg=None, bg=None):
    infocodes = []
    if fg is not None:
        infocodes.append(str(fg.value + ANSI_FG_START))
    if bg is not None:
        infocodes.append(str(bg.value + ANSI_BG_START))
    return ANSI_CSI + ";".join(infocodes) + "m" + text + ANSI_CSI + "0m"


def split_rgb_string(hex_string):
    """
    \brief Convert a hex string to a R G B tuple
    \param hex_string string in the form of 'rgb' or 'rrggbb' (leading '#' will
    be stripped)
    \returns 3-tuple with values between 0 and 255
    """
    hex_string = hex_string.lstrip("#")
    if len(hex_string) == 3:
        r, g, b = map(lambda x: int(x*2, 16), hex_string)
        return r, g, b
    elif len(hex_string) == 6:
        r, g, b = map(lambda x: int(x, 16), [hex_string[i:i+2] for i in
                                             range(0, len(hex_string), 2)])
        return r, g, b
    raise ValueError("Needs a string of form 'rgb' or 'rrggbb")


def closest_irc_color(r, g, b):
    """
    \brief Find the closest irc color
    \param r Red value (0-255)
    \param g Green value (0-255)
    \param b Blue value (0-255)
    \returns The closest irc color name
    """
    color_lab1 = convert_color(sRGBColor(r, g, b, is_upscaled=True), LabColor)

    def sort_function(val):
        col = convert_color(sRGBColor(*split_rgb_string(val[1]),
                                      is_upscaled=True), LabColor)
        return delta_e_cie2000(color_lab1, col)
    closest_color, closest_distance = min(ColorsHex.items(),
                                          key=sort_function)
    return closest_color
