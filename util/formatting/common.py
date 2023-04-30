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
from typing import NamedTuple, Union, Optional
import yaml
from zope import interface


url_pat = re.compile(r"(((https?)|(ftps?)|(sftp))://[^\s\"\')]+)")


## \brief Maps color names to the corresponding mIRC numerical values
## (as a two-digit strings)
## These colors shall serve as a generic set of colors used throughout the application
ColorCodes = Enum("ColorCodes", {
    "white": "00",
    "black": "01",
    "darkblue": "02",
    "darkgreen": "03",
    "red": "04",
    "darkred": "05",
    "darkmagenta": "06",
    "darkorange": "07",
    "yellow": "08",
    "lime": "09",
    "darkcyan": "10",
    "cyan": "11",
    "blue": "12",
    "magenta": "13",
    "darkgray": "14",
    "lightgray": "15"
})

## \brief hex color codes for mIRC numerical values
ColorsHex = bidict({
    ColorCodes.white: "#FFFFFF",
    ColorCodes.black: "#000000",
    ColorCodes.darkblue: "#000080",
    ColorCodes.darkgreen: "#006400",
    ColorCodes.red: "#FF0000",
    ColorCodes.darkred: "#8B0000",
    ColorCodes.darkmagenta: "#8B008B",
    ColorCodes.darkorange: "#FF8C00",
    ColorCodes.yellow: "#FFFF00",
    ColorCodes.lime: "#00FF00",
    ColorCodes.darkcyan: "#008B8B",
    ColorCodes.cyan: "#00FFFF",
    ColorCodes.blue: "#0000FF",
    ColorCodes.magenta: "#FF00FF",
    ColorCodes.darkgray: "#7F7F7F",
    ColorCodes.lightgray: "#D3D3D3"})


# The HTML spec defines several named colors:
# https://www.w3.org/TR/css-color-3/#html4
# https://www.w3.org/TR/css-color-3/#svg-color
HTMLColors = {
        "black": "#000000",
        "gray": "#808080",
        "maroon": "#800000",
        "purple": "#800080",
        "fuchsia": "#ff00ff",
        "green": "#008000",
        "lime": "#00ff00",
        "olive": "#808000",
        "yellow": "#ffff00",
        "navy": "#000080",
        "blue": "#0000ff",
        "teal": "#008080",
        "aqua": "#00ffff",
        "aliceblue": "#f0f8ff",
        "antiquewhite": "#faebd7",
        "aquamarine": "#7fffd4",
        "azure": "#f0ffff",
        "beige": "#f5f5dc",
        "bisque": "#ffe4c4",
        "blanchedalmond": "#ffebcd",
        "blueviolet": "#8a2be2",
        "brown": "#a52a2a",
        "burlywood": "#deb887",
        "cadetblue": "#5f9ea0",
        "chartreuse": "#7fff00",
        "chocolate": "#d2691e",
        "coral": "#ff7f50",
        "cornflowerblue": "#6495ed",
        "cornsilk": "#fff8dc",
        "crimson": "#dc143c",
        "cyan": "#00ffff",
        "darkblue": "#00008b",
        "darkcyan": "#008b8b",
        "darkgoldenrod": "#b8860b",
        "darkgray": "#a9a9a9",
        "darkgreen": "#006400",
        "darkgrey": "#a9a9a9",
        "darkkhaki": "#bdb76b",
        "darkmagenta": "#8b008b",
        "darkolivegreen": "#556b2f",
        "darkorange": "#ff8c00",
        "darkorchid": "#9932cc",
        "darkred": "#8b0000",
        "darksalmon": "#e9967a",
        "darkseagreen": "#8fbc8f",
        "darkslateblue": "#483d8b",
        "darkslategray": "#2f4f4f",
        "darkslategrey": "#2f4f4f",
        "darkturquoise": "#00ced1",
        "darkviolet": "#9400d3",
        "deeppink": "#ff1493",
        "deepskyblue": "#00bfff",
        "dimgray": "#696969",
        "dimgrey": "#696969",
        "dodgerblue": "#1e90ff",
        "firebrick": "#b22222",
        "floralwhite": "#fffaf0",
        "forestgreen": "#228b22",
        "gainsboro": "#dcdcdc",
        "ghostwhite": "#f8f8ff",
        "gold": "#ffd700",
        "goldenrod": "#daa520",
        "greenyellow": "#adff2f",
        "grey": "#808080",
        "honeydew": "#f0fff0",
        "hotpink": "#ff69b4",
        "indianred": "#cd5c5c",
        "indigo": "#4b0082",
        "ivory": "#fffff0",
        "khaki": "#f0e68c",
        "lavender": "#e6e6fa",
        "lavenderblush": "#fff0f5",
        "lawngreen": "#7cfc00",
        "lemonchiffon": "#fffacd",
        "lightblue": "#add8e6",
        "lightcoral": "#f08080",
        "lightcyan": "#e0ffff",
        "lightgoldenrodyellow": "#fafad2",
        "lightgray": "#d3d3d3",
        "lightgreen": "#90ee90",
        "lightgrey": "#d3d3d3",
        "lightpink": "#ffb6c1",
        "lightsalmon": "#ffa07a",
        "lightseagreen": "#20b2aa",
        "lightskyblue": "#87cefa",
        "lightslategray": "#778899",
        "lightslategrey": "#778899",
        "lightsteelblue": "#b0c4de",
        "lightyellow": "#ffffe0",
        "limegreen": "#32cd32",
        "linen": "#faf0e6",
        "magenta": "#ff00ff",
        "mediumaquamarine": "#66cdaa",
        "mediumblue": "#0000cd",
        "mediumorchid": "#ba55d3",
        "mediumpurple": "#9370db",
        "mediumseagreen": "#3cb371",
        "mediumslateblue": "#7b68ee",
        "mediumspringgreen": "#00fa9a",
        "mediumturquoise": "#48d1cc",
        "mediumvioletred": "#c71585",
        "midnightblue": "#191970",
        "mintcream": "#f5fffa",
        "mistyrose": "#ffe4e1",
        "moccasin": "#ffe4b5",
        "navajowhite": "#ffdead",
        "oldlace": "#fdf5e6",
        "olivedrab": "#6b8e23",
        "orange": "#ffa500",
        "orangered": "#ff4500",
        "orchid": "#da70d6",
        "palegoldenrod": "#eee8aa",
        "palegreen": "#98fb98",
        "paleturquoise": "#afeeee",
        "palevioletred": "#db7093",
        "papayawhip": "#ffefd5",
        "peachpuff": "#ffdab9",
        "peru": "#cd853f",
        "pink": "#ffc0cb",
        "plum": "#dda0dd",
        "powderblue": "#b0e0e6",
        "red": "#ff0000",
        "rosybrown": "#bc8f8f",
        "royalblue": "#4169e1",
        "saddlebrown": "#8b4513",
        "salmon": "#fa8072",
        "sandybrown": "#f4a460",
        "seagreen": "#2e8b57",
        "seashell": "#fff5ee",
        "sienna": "#a0522d",
        "silver": "#c0c0c0",
        "skyblue": "#87ceeb",
        "slateblue": "#6a5acd",
        "slategray": "#708090",
        "slategrey": "#708090",
        "snow": "#fffafa",
        "springgreen": "#00ff7f",
        "steelblue": "#4682b4",
        "tan": "#d2b48c",
        "thistle": "#d8bfd8",
        "tomato": "#ff6347",
        "turquoise": "#40e0d0",
        "violet": "#ee82ee",
        "wheat": "#f5deb3",
        "white": "#ffffff",
        "whitesmoke": "#f5f5f5",
        "yellowgreen": "#9acd32"
        }


def good_contrast_with_black(color: Union[str,ColorCodes]) -> bool:
    """
    Indicates if a color has good contrast with black. This is achieved by
    looking at the `Value` in `HSV` color space
    """
    if isinstance(color, ColorCodes):
        color = ColorsHex[color]
    return convert_color(sRGBColor(*split_rgb_string(color), is_upscaled=True),
                         HSVColor).hsv_v > 0.5


RAINBOW_COLORS = (ColorCodes.red, ColorCodes.darkorange, ColorCodes.lime,
                  ColorCodes.cyan, ColorCodes.blue, ColorCodes.magenta)


Message = Union[str, Tag]


@dataclass
class Style:
    underline: Optional[bool] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    strike: Optional[bool] = None
    fg: Optional[Union[ColorCodes, str]] = None
    bg: Optional[Union[ColorCodes, str]] = None

    def __bool__(self) -> bool:
        return any(asdict(self).values())


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
        self._slotDataStack = deque()
        self._slotDataStack.append({})

    def handle_newline(self):
        if self.buffer:
            self.buffer += "\n"

    def handle_slot(self, slt: slot):
        self.handle_data(self._slotDataStack[-1][slt.name])

    def handle_starttag(self, tag: Tag):
        slotData = {**self._slotDataStack[-1], **(tag.slotData or {})}
        self._slotDataStack.append(slotData)
        if tag.tagName == "br" or is_display_block(tag):
            self.handle_newline()

    def handle_data(self, data: str):
        fragments = data.split("\n")
        self.buffer += fragments[0]
        for item in fragments[1:]:
            self.handle_newline()
            self.buffer += item

    def handle_endtag(self, tag: Tag):
        if tag.tagName == "a" and (href:=tag.attributes.get("href", None)):
            if isinstance(href, Tag):
                href = handle_attribute_tag(href, self._slotDataStack)
            self.buffer += f" ({href})"
        if is_display_block(tag):
            self.handle_newline()
        self._slotDataStack.pop()


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


def to_plaintext(data: Message) -> str:
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


def interpolate_color(color1: Union[ColorCodes, str], color2: Union[ColorCodes, str],
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
    if color in [e.name for e in ColorCodes]:
        return ColorCodes[color]
    if color in HTMLColors:
        color = HTMLColors[color]
    if color.startswith("#"):
        if color in ColorsHex.inv:
            return ColorsHex.inv[color]
        return closest_colorcode_from_rgb(*split_rgb_string(color))
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

