# -*- coding: utf-8 -*-

# PyTIBot - Formatting Helper
# Copyright (C) <2015>  <Sebastian Schmidt, Mattia Basaglia>

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

## \brief Maps color names to the corresponding mIRC numerical values
## (as a two-digit strings)
color_code = {
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
}

## \brief hex color codes for mIRC numerical values
hex_colors = ["#FFFFFF", "#000000", "#00007F", "#009300", "#FF0000",
              "#7F0000", "#9C009C", "#FC7F00", "#FFFF00", "#00FC00",
              "#009393", "#00FFFF", "#0000FC", "#FF00FF", "#7F7F7F",
              "#D2D2D2"]


def colored(text, fgcolor, bgcolor=None, endtoken=False):
    """
    \brief Colorize a string
    \param fgcolor Color name to be used as text color
    \param bgcolor Color name to be used as background color, can be None
    \param endtoken Send the colortoken at the end to end colored text
    \returns A string with IRC colors if color is valid
    """
    if fgcolor not in color_code:
        print("Color {} not valid, no color added".format(fgcolor))
        return text
    if bgcolor and bgcolor in color_code:
        colorinfo = "{},{}".format(color_code[fgcolor], color_code[bgcolor])
    else:
        colorinfo = color_code[fgcolor]
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
    return color_code[colors[int(factor*len(colors))]]


def rainbow(text, colors=["red", "dark_yellow", "green", "cyan", "blue",
                          "magenta"]):
    """
    \brief Colorize a string as a rainbow
    \param text          Input text
    \param colors        Color names to be featured in the rainbow
    \returns A string with valid IRC color codes inserted at the right
    positions
    """
    ret = ""
    color = ""
    for index, char in enumerate(text):
        newcolor = rainbow_color(float(index)/len(text), colors)
        if newcolor != color:
            color = newcolor
            ret += _COLOR + color
        ret += char
    return ret + _COLOR


def underlined(text, endtoken=False):
    """
    \brief Return a underlined string
    \param endtoken end the underlined text
    \returns A underlined string
    """
    if endtoken:
        return _UNDERLINE + text + _UNDERLINE
    return _UNDERLINE + text


def italic(text, endtoken=False):
    """
    \brief Return a italic string
    \param endtoken end the italic text
    \returns A italic string
    """
    if endtoken:
        return _ITALIC + text + _ITALIC
    return _ITALIC + text


def bold(text, endtoken=False):
    """
    \brief Return a bold string
    \param endtoken end the bold text
    \returns A bold string
    """
    if endtoken:
        return _BOLD + text + _BOLD
    return _BOLD + text


format_pattern = re.compile("(\x1f)|(\x02)|(\x03)(\\d{1,2}(,\\d{1,2})?)?|"
                            "(\x1d)|(\x0f)")
# underline, bold, color, (fg,bg?), (,bg), italic, normal


def _info_dict_to_style(info_dict):
    styles = []
    if info_dict["underline"]:
        styles.append("text-decoration:underline")
    if info_dict["bold"]:
        styles.append("font-weight:bold")
    if info_dict["fg"]:
        styles.append("color:{}".format(hex_colors[info_dict["fg"]]))
    if info_dict["bg"]:
        styles.append("background-color:{}".format(
            hex_colors[info_dict["bg"]]))
    if info_dict["italic"]:
        styles.append("font-style:italic")

    if styles:
        return '<span style="{style}">{{text}}</span>'.format(
            style=";".join(styles))
    return "{text}"


def to_html(text):
    """
    \brief Convert a string with IRC formatting information to html formatting
    """
    # <span style="color:{color}">{substr}</span>
    # <span style="background-color:{bg_color}">{substr}</span>
    # <span style="text-decoration:underline">{substr}</span>
    # <span style="font-style:italic">{substr}</span>
    # <span style="font-weight:bold">{substr}</span>
    substrings = format_pattern.split(text)
    if len(substrings) % 8:
        # first substring has no formatting information
        html = substrings[0]
        start = 1
    else:
        html = ""
        start = 0
    info_dict = {"underline": False, "bold": False, "fg": None, "bg": None,
                 "italic": False}
    for i in range(start, len(substrings), 8):
        if substrings[i]:
            info_dict["underline"] = not info_dict["underline"]
        if substrings[i+1]:
            info_dict["bold"] = not info_dict["bold"]
        if substrings[i+2]:
            if not substrings[i+3]:
                info_dict["fg"] = None
                info_dict["bg"] = None
            elif "," in substrings[i+3]:
                info_dict["fg"], info_dict["bg"] = [int(val) for val in
                                                    substrings[i+3].split(",")]
            else:
                info_dict["fg"] = int(substrings[i+3])
        if substrings[i+5]:
            info_dict["italic"] = not info_dict["italic"]
        if substrings[i+6]:
            # big reset switch
            info_dict = {"underline": False, "bold": False, "fg": None,
                         "bg": None, "italic": False}
        html += _info_dict_to_style(info_dict).format(text=substrings[i+7])
    return html
