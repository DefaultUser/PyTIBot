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

from html import escape as htmlescape
from twisted.web.template import tags, Tag

from util.formatting.common import ColorsHex, Style, StyledTextFragment, url_pat
from util.formatting.irc import _extract_irc_style


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


def _style_html_string(style: Style) -> str:
    # TODO: handle hex colors
    styles = []
    if style.underline:
        styles.append("text-decoration:underline")
    if style.bold:
        styles.append("font-weight:bold")
    if style.fg:
        # TODO: don't replace ColorCode with Hex value
        styles.append("color:{}".format(ColorsHex[style.fg]))
    if style.bg:
        # TODO: don't replace ColorCode with Hex value
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


def to_html(text: str, link_urls: bool=True) -> str:
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


def to_matrix(text: str) -> str:
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


def to_tags(text: str, link_urls: bool=True) -> list[Tag]:
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

