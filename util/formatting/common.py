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
from collections import deque
from colormath.color_objects import ColorBase, sRGBColor, LabColor, HSVColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from dataclasses import dataclass, asdict
from enum import Enum
import re
from twisted.web.template import Tag, slot
from typing import NamedTuple, TypeAlias
import yaml
from zope import interface


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


def good_contrast_with_black(color: str|ColorCodes) -> bool:
    """
    Indicates if a color has good contrast with black. This is achieved by
    looking at the `Value` in `HSV` color space
    """
    if isinstance(color, ColorCodes):
        color = ColorsHex[color]
    return convert_color(sRGBColor(*split_rgb_string(color), is_upscaled=True),
                         HSVColor).hsv_v > 0.5


RAINBOW_COLORS = (ColorCodes.red, ColorCodes.dark_yellow, ColorCodes.green,
                  ColorCodes.cyan, ColorCodes.blue, ColorCodes.magenta)


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


def is_bold(tag: Tag) -> bool:
    return (tag.tagName in ("b", "strong") or
            tag.attributes.get("bold", False))


def is_italic(tag: Tag) -> bool:
    return (tag.tagName in ("i", "em", "cite") or
            tag.attributes.get("italic", False))


def is_del(tag: Tag) -> bool:
    return (tag.tagName in ("del", "strike", "s") or
            tag.attributes.get("strike", False))


def is_underlined(tag: Tag) -> bool:
    return (tag.tagName == "u" or
            tag.attributes.get("underline", False))


def is_display_block(tag: Tag) -> bool:
    return tag.tagName in ("p", "div")


def is_colored(tag: Tag) -> bool:
    return (tag.tagName in ("font", "span", "div") and
            ("color" in tag.attributes or
             "background-color" in tag.attributes))


def handle_attribute_tag(attr: Tag, slotDataStack: deque):
    if len(attr.children) == 1:
        item = attr.children[0]
        if isinstance(item, slot):
            return slotDataStack[-1][item.name]
        return item
    temp = []
    for child in attr.children:
        if isinstance(child, slot):
            temp.append(slotDataStack[-1][item.name])
        else:
            temp.append(child)
    return "".join(temp)


class ITagProcessor(interface.Interface):
    def handle_slot(slt: slot):
        """Called when a slot is encountered"""

    def handle_starttag(tag: Tag):
        """Called when a tag is opened"""

    def handle_data(data: str):
        """Called with a tag's text data"""

    def handle_endtag(tag: Tag):
        """Called when a tag is closed"""


@interface.implementer(ITagProcessor)
class TagToPlainFormatter:
    # TODO: support <hn> (markdown style)
    def __init__(self):
        self.buffer = ""
        self._slotDataStack = []

    def handle_newline(self):
        if self.buffer:
            self.buffer += "\n"

    def handle_slot(self, slt: slot):
        for slotData in self._slotDataStack[::-1]:
            if slotData and slt.name in slotData:
                self.handle_data(slotData[slt.name])
                return
        raise KeyError(f"Unfilled Slot {slt.name}")

    def handle_starttag(self, tag: Tag):
        self._slotDataStack.append(tag.slotData)
        if tag.tagName == "br" or is_display_block(tag):
            self.handle_newline()

    def handle_data(self, data: str):
        fragments = data.split("\n")
        self.buffer += fragments[0]
        for item in fragments[1:]:
            self.handle_newline()
            self.buffer += item

    def handle_endtag(self, tag: Tag):
        self._slotDataStack.pop()
        if tag.tagName == "a" and (href:=tag.attributes.get("href", None)):
            self.buffer += f" ({href})"
        if is_display_block(tag):
            self.handle_newline()


def _processStyledText(data: Tag, processor: ITagProcessor):
    stack = deque()
    close_tag_stack = deque()
    stack.append((data, 0))
    while stack:
        item, depth = stack.pop()
        while close_tag_stack and depth <= close_tag_stack[-1][1]:
            close_tag = close_tag_stack.pop()
            processor.handle_endtag(close_tag[0])
        if isinstance(item, str):
            processor.handle_data(item)
            continue
        if isinstance(item, slot):
            processor.handle_slot(item)
            continue
        tagName = item.tagName
        close_tag_stack.append((item, depth))
        processor.handle_starttag(item)
        for child in reversed(item.children):
            stack.append((child, depth+1))
    # Close all tags
    while close_tag_stack:
        close_tag = close_tag_stack.pop()
        processor.handle_endtag(close_tag[0])


def to_plaintext(data: Tag|str) -> str:
    if isinstance(data, str):
        return data
    formatter = TagToPlainFormatter()
    _processStyledText(data, formatter)
    result = formatter.buffer
    while "\n" in result:
        beginning, last_line = result.rsplit("\n", 1)
        if last_line == "":
            result = beginning
        else:
            break
    return result


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


def interpolate_color(color1: ColorCodes|str, color2: ColorCodes|str,
                      factor: float, colorspace: ColorBase = sRGBColor) -> str:
    if isinstance(color1, ColorCodes):
        color1 = ColorsHex[color1]
    if isinstance(color2, ColorCodes):
        color2 = ColorsHex[color2]
    color1 = convert_color(sRGBColor(*split_rgb_string(color1),
                                     is_upscaled=True),
                           colorspace).get_value_tuple()
    color2 = convert_color(sRGBColor(*split_rgb_string(color2),
                                     is_upscaled=True),
                           colorspace).get_value_tuple()
    val = []
    for i in range(3):
        val.append(color1[i] + (color2[i]-color1[i])*factor)
    out_color = convert_color(colorspace(*val), sRGBColor)
    return out_color.get_rgb_hex()


def closest_colorcode_from_rgb(r: int, g: int, b: int) -> ColorCodes:
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


def closest_colorcode(color: str) -> ColorCodes:
    """
    \brief Find the closest color code
    \param color Color definition either as hex string or color name
    """
    if color.startswith("#"):
        if color in ColorsHex.inv:
            return ColorsHex.inv[color]
        return closest_colorcode_from_rgb(*split_rgb_string(color))
    if color in [e.name for e in ColorCodes]:
        return ColorCodes[color]
    if color == "darkorange":
        return ColorCodes.dark_yellow
    color = color.replace("dark", "dark_")
    if color in [e.name for e in ColorCodes]:
        return ColorCodes[color]
    raise ValueError("Invalid color definition")


def colorCode_representer(dumper: yaml.SafeDumper, color: ColorCodes) -> yaml.nodes.MappingNode:
    return dumper.represent_scalar("!ColorCode", color.name)


def colorCode_constructor(loader: yaml.SafeLoader,
                          node: yaml.nodes.MappingNode) -> ColorCodes:
    code = loader.construct_scalar(node)
    return ColorCodes[code]


def tag_representer(dumper: yaml.SafeDumper, tag: Tag) -> yaml.nodes.MappingNode:
    d = {"tagName": tag.tagName, "children": tag.children}
    if tag.attributes:
        d["attributes"] = tag.attributes
    if tag.slotData:
        d["slotData"] = tag.slotData
    return dumper.represent_mapping("!Tag", d)


def tag_constructor(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode) -> Tag:
    mapping = loader.construct_mapping(node, deep=True)
    tag = Tag(mapping["tagName"])(*mapping["children"])
    if attr := mapping.get("attributes", None):
        tag.attributes = attr
    if slotData := mapping.get("slotData", None):
        tag.slotData = slotData
    return tag


def slot_representer(dumper: yaml.SafeDumper, slt: slot) -> yaml.nodes.MappingNode:
    return dumper.represent_scalar("!slot", slt.name)


def slot_constructor(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode) -> slot:
    name = loader.construct_scalar(node)
    return slot(name)


yaml.add_constructor("!ColorCode", colorCode_constructor)
yaml.add_constructor("!Tag", tag_constructor)
yaml.add_constructor("!slot", slot_constructor)
yaml.add_representer(ColorCodes, colorCode_representer)
yaml.add_representer(Tag, tag_representer)
yaml.add_representer(slot, slot_representer)

