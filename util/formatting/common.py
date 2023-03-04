# PyTIBot - Formatting Helper
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

from bidict import bidict
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from dataclasses import dataclass, asdict
from enum import Enum
import re
from typing import NamedTuple, TypeAlias


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
# TODO: ColorCodes -> HTML: code.name.replace("_", "").replace("darkyellow", "darkorange")

## \brief hex color codes for mIRC numerical values
ColorsHex = bidict({
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
    ColorCodes.gray: "#D2D2D2"})

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

@dataclass
class Style:
    underline: bool | None = None
    bold: bool | None = None
    italic: bool | None = None
    strike: bool | None = None
    fg: ColorCodes | str | None = None
    bg: ColorCodes | str | None = None

    def __bool__(self) -> bool:
        return any(asdict(self).values())

class StyledTextFragment(NamedTuple):
    text: str
    style: Style = Style()


StyledText: TypeAlias = str | list[str|StyledTextFragment]


def split_rgb_string(hex_string: str) -> tuple[int]:
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


def closest_colorcode(r: int, g: int, b: int) -> ColorCodes:
    """
    \brief Find the closest color code
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

