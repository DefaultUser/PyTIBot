# -*- coding: utf-8 -*-

# PyTIBot - Formatting Helper
# Copyright (C) <2015-2020>  <Sebastian Schmidt, Mattia Basaglia>

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
from collections import namedtuple
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from twisted.web.template import tags

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
IRCColorCodes = Enum("IRCColorCodes", {
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
IRCColorsHex = {
    IRCColorCodes.white: "#FFFFFF",
    IRCColorCodes.black: "#000000",
    IRCColorCodes.dark_blue: "#00007F",
    IRCColorCodes.dark_green: "#009300",
    IRCColorCodes.red: "#FF0000",
    IRCColorCodes.dark_red: "#7F0000",
    IRCColorCodes.dark_magenta: "#9C009C",
    IRCColorCodes.dark_yellow: "#FC7F00",
    IRCColorCodes.yellow: "#FFFF00",
    IRCColorCodes.green: "#00FC00",
    IRCColorCodes.dark_cyan: "#009393",
    IRCColorCodes.cyan: "#00FFFF",
    IRCColorCodes.blue: "#0000FC",
    IRCColorCodes.magenta: "#FF00FF",
    IRCColorCodes.dark_gray: "#7F7F7F",
    IRCColorCodes.gray: "#D2D2D2"}

# dict that indicates if a color is a good background for black text
good_contrast_with_black = {
    IRCColorCodes.white: True,
    IRCColorCodes.black: False,
    IRCColorCodes.dark_blue: False,
    IRCColorCodes.dark_green: True,
    IRCColorCodes.red: True,
    IRCColorCodes.dark_red: True,
    IRCColorCodes.dark_magenta: True,
    IRCColorCodes.dark_yellow: True,
    IRCColorCodes.yellow: True,
    IRCColorCodes.green: True,
    IRCColorCodes.dark_cyan: True,
    IRCColorCodes.cyan: True,
    IRCColorCodes.blue: True,
    IRCColorCodes.magenta: True,
    IRCColorCodes.dark_gray: True,
    IRCColorCodes.gray: True
}

ANSI_CSI = "\x1b["
ANSI_FG_START = 30
ANSI_BG_START = 40
ANSIColors = IntEnum("ANSIColors", "black red green yellow blue magenta cyan white",
                     start=0)


def colored(text, fgcolor, bgcolor=None, endtoken=True):
    """
    \brief Colorize a string
    \param fgcolor IRCColorCodes color to be used as text color
    \param bgcolor IRCColorCodes color to be used as background color, can be None
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


def rainbow(text, colors=[IRCColorCodes.red, IRCColorCodes.dark_yellow, IRCColorCodes.green,
                          IRCColorCodes.cyan, IRCColorCodes.blue, IRCColorCodes.magenta]):
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

styled_text = namedtuple("StyledText", "text style")


def _extract_irc_style(text):
    """
    \brief Extract IRC formatting information from string
    """
    # <span style="color:{color}">{substr}</span>
    # <span style="background-color:{bg_color}">{substr}</span>
    # <span style="text-decoration:underline">{substr}</span>
    # <span style="font-style:italic">{substr}</span>
    # <span style="font-weight:bold">{substr}</span>
    substrings = format_pattern.split(text)
    style_dict = {"underline": False, "bold": False, "fg": None, "bg": None,
                  "italic": False}
    if len(substrings) % 8:
        # first substring has no formatting information
        yield styled_text(text=substrings[0], style=style_dict)
        start = 1
    else:
        start = 0
    for i in range(start, len(substrings), 8):
        if substrings[i]:
            style_dict["underline"] = not style_dict["underline"]
        if substrings[i+1]:
            style_dict["bold"] = not style_dict["bold"]
        if substrings[i+2]:
            if not substrings[i+3]:
                style_dict["fg"] = None
                style_dict["bg"] = None
            elif "," in substrings[i+3]:
                style_dict["fg"], style_dict["bg"] = [int(val) for val in
                                                      substrings[i+3].split(",")]
            else:
                style_dict["fg"] = int(substrings[i+3])
        if substrings[i+5]:
            style_dict["italic"] = not style_dict["italic"]
        if substrings[i+6]:
            # big reset switch
            style_dict = {"underline": False, "bold": False, "fg": None,
                          "bg": None, "italic": False}
        yield styled_text(text=substrings[i+7], style=style_dict)

def _style_html_string(style_dict):
    styles = []
    if style_dict["underline"]:
        styles.append("text-decoration:underline")
    if style_dict["bold"]:
        styles.append("font-weight:bold")
    if style_dict["fg"]:
        styles.append("color:{}".format(hex_colors[style_dict["fg"]]))
    if style_dict["bg"]:
        styles.append("background-color:{}".format(
            hex_colors[style_dict["bg"]]))
    if style_dict["italic"]:
        styles.append("font-style:italic")
    return styles

def _style_dict_to_html(text, style_dict, link_urls=True):
    styles = _style_html_string(style_dict)
    if link_urls:
        text = url_pat.sub(r"<a href='\1'>\1</a>", text)
    if styles:
        return '<span style="{style}">{text}</span>'.format(
            style=";".join(styles), text=text)
    return text


def to_html(text, link_urls=True):
    """
    \brief Convert a string with IRC formatting information to html formatting
    """
    html = ""
    for frag in _extract_irc_style(text):
        html += _style_dict_to_html(frag.text, frag.style, link_urls)
    return html


def _style_dict_to_tags(text, style_dict, link_urls=True):
    styles = _style_html_string(style_dict)
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
        return tags.span(text, style=styles)
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
        t.append(_style_dict_to_tags(frag.text, frag.style, link_urls))
    return t


colorpat = re.compile(r"\$COLOR(\((\d{{1,2}}|{colors})(,(\d{{1,2}}|{colors}))?\))?".format(
    colors="|".join(["white", "black", "dark_blue", "dark_green", "red", "dark_red",
                     "dark_magenta", "dark_yellow", "yellow", "green", "dark_cyan",
                     "cyan", "blue", "magenta", "dark_gray", "gray"])))
rainbowpat = re.compile(r"\$RAINBOW\(([^)]+)\)")
def from_human_readable(text):
    """
    \brief Convert human readable formatting information to IRC formatting
    """
    def colorname_sub(match):
        fg = match.group(2)
        if fg is not None:
            if fg.isdecimal():
                fg = IRCColorCodes(fg)
            else:
                fg = IRCColorCodes[fg]
        bg = match.group(4)
        if bg is not None:
            if bg.isdecimal():
                bg = IRCColorCodes(bg)
            else:
                bg = IRCColorCodes[bg]
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
    closest_color, closest_distance = min(IRCColorsHex.items(),
                                          key=sort_function)
    return closest_color
