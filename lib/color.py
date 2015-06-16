# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
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


## \brief Maps color names to the corresponding mIRC numerical values
## (as a two-digit strings)
color_code = {
    "black"       : "00",
    "white"       : "01",
    "dark_blue"   : "02",
    "dark_green"  : "03",
    "red"         : "04",
    "dark_red"    : "05",
    "dark_magenta": "06",
    "dark_yellow" : "07",
    "yellow"      : "08",
    "green"       : "09",
    "dark_cyan"   : "10",
    "cyan"        : "11",
    "blue"        : "12",
    "magenta"     : "13",
    "dark_gray"   : "14",
    "gray"        : "15"
}

## \brief Token to start colored text
_colortoken = "\x03"

def colored(text, fgcolor, bgcolor=None, endtoken=False):
    """
    \brief Colorize a string
    \param fgcolor Color name to be used as text color
    \param bgcolor Color name to be used as background color, can be None
    \param endtoken Send the colortoken at the end to end colored text
    \returns A string with IRC colors if color is valid
    """
    if fgcolor not in color_code:
        print("Color %s not valid, no color added" % fgcolor)
        return text
    if bgcolor and bgcolor in color_code:
        colorinfo = "%s,%s" % (color_code[fgcolor], color_code[bgcolor])
    else:
        colorinfo = color_code[fgcolor]
    if endtoken:
        return _colortoken + colorinfo + text + _colortoken
    return _colortoken + colorinfo + text


def rainbow_color(factor, colors):
    """
    \brief Return a color in the rainbow
    \param factor        A value in [0,1]
    \param colors        Color names to be featured in the rainbow
    \returns The numerical value of the selected color
    """
    return color_code[colors[int(factor*len(colors))]]


def rainbow(text, colors=["red","dark_yellow","green","cyan","blue","magenta"]):
    """
    \brief Colorize a string as a rainbow
    \param text          Input text
    \param colors        Color names to be featured in the rainbow
    \returns A string with valid IRC color codes inserted at the right positions
    """
    ret = ""
    color = ""
    for index, char in enumerate(text):
        newcolor = rainbow_color(float(index)/len(text), colors)
        if newcolor != color:
            color = newcolor
            ret += _colortoken + color
        ret += char
    return ret
