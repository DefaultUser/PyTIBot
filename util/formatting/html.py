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

from collections import deque
from html import escape as htmlescape
from html import parser as htmlparser
from twisted.web.template import Tag, slot
from typing import Union
from zope import interface

from util.formatting import common
from util.formatting.common import ColorCodes, ColorsHex, HTMLColors, Style, Message


def color_to_string(color: Union[ColorCodes, str]) -> str:
    return ColorsHex[color] if isinstance(color, ColorCodes) else color


class HTMLParseError(Exception):
    pass


_UNPAIRED_TAGS = ("br", "hr", "img")


class SanetizingHTMLParser(htmlparser.HTMLParser):
    """
    Parser for html and matrix messages that restricts the used tags and
    attributes to safe values. It additionally allows `<rainbow>` tags for a
    rainbow colored font.
    The parameter `allow_slots` defines whether `<t:slot>` and `<t:attr>` tags
    shall be ignored. Their usage is according to twisted's web templates.
    """
    # https://spec.matrix.org/v1.5/client-server-api/#mroommessage-msgtypes
    # Allowed tags:
    # font, del, h1, h2, h3, h4, h5, h6, blockquote, p, a, ul, ol, sup, sub,
    # li, b, i, u, strong, em, strike, code, hr, br, div, table, thead,
    # tbody, tr, th, td, caption, pre, span, img, details, summary
    # mx-reply tag is allowed at the beginning of a message
    # Allowed attrs:
    # data-mx-bg-color, data-mx-color, color
    # TODO: support tables, (un)ordered lists, quotes and code/preformatted blocks

    allowed_tags_with_attrs = ("font", "p", "div", "span")
    allowed_tags = ("b", "strong", "u", "i", "em", "cite", "del", "strike", "s",
                    "font", "a", "br", "span", "div", "img", "rainbow",
                    "t:slot", "t:attr")

    def __init__(self, *, allow_slots=False, convert_charrefs=True):
        super().__init__(convert_charrefs=convert_charrefs)
        self.root = Tag("")
        self._stack = deque([self.root])
        self._allow_slots = allow_slots

    @staticmethod
    def parse_html_color(color: str) -> Union[ColorCodes, str]:
        try:
            temp = ColorCodes[color]
            return temp
        except KeyError:
            color = HTMLColors.get(color, color)
            return color

    @staticmethod
    def parse_style(style: str) -> Style:
        result = Style()
        for line in style.split(";"):
            tokens = line.split(":")
            if len(tokens) != 2:
                print("invalid inline style")
                continue
            prop = tokens[0].strip()
            value = tokens[1].strip()
            if prop == "text-decoration" and value == "underline":
                result.underline = True
            elif prop == "text-decoration" and value == "line-through":
                result.strike = True
            elif prop == "font-weight" and value == "bold":
                result.bold = True
            elif prop == "font-style" and value == "italic":
                result.italic = True
            elif prop == "color":
                result.fg = SanetizingHTMLParser.parse_html_color(value)
            elif prop == "background-color":
                result.bg = SanetizingHTMLParser.parse_html_color(value)
        return result

    def handle_starttag(self, tagName: str, attrs: list[tuple[str, str]]):
        if tagName not in SanetizingHTMLParser.allowed_tags:
            return
        # a new 'p' tag can close the previous one implicitly
        if tagName == "p":
            if self._stack[-1].tagName == "p":
                self._stack.pop()
        attrs = dict(attrs)
        sanetized_attrs = {}
        if tagName == "t:slot":
            if self._allow_slots:
                new_tag = slot(attrs["name"])
                self._stack[-1].children.append(new_tag)
            return
        if tagName == "t:attr":
            if self._allow_slots:
                new_tag = Tag("")
                self._stack[-1].attributes[attrs["name"]] = new_tag
                self._stack.append(new_tag)
            return
        if tagName == "img":
            src = attrs.get("src", None)
            self.handle_data(f"inline image {src=}")
            return
        if tagName in SanetizingHTMLParser.allowed_tags_with_attrs:
            if "style" in attrs:
                style = SanetizingHTMLParser.parse_style(attrs["style"])
                if style.bold:
                    sanetized_attrs["bold"] = True
                if style.italic:
                    sanetized_attrs["italic"] = True
                if style.underline:
                    sanetized_attrs["underline"] = True
                if style.strike:
                    sanetized_attrs["strike"] = True
                if style.fg:
                    sanetized_attrs["color"] = style.fg
                if style.bg:
                    sanetized_attrs["background-color"] = style.bg
            if ((color:=attrs.get("color", None)) or
                    (color:=attrs.get("data-mx-color", None))):
                color = SanetizingHTMLParser.parse_html_color(color)
                sanetized_attrs["color"] = color
            if ((color:=attrs.get("background-color", None)) or
                    (color:=attrs.get("data-mx-bg-color", None))):
                color = SanetizingHTMLParser.parse_html_color(color)
                sanetized_attrs["background-color"] = color
        if tagName == "a" and (href:=attrs.get("href", None)):
            sanetized_attrs["href"] = href
        new_tag = Tag(tagName)
        new_tag.attributes = sanetized_attrs
        self._stack[-1].children.append(new_tag)
        if tagName not in _UNPAIRED_TAGS:
            self._stack.append(new_tag)

    def handle_data(self, data: str):
        self._stack[-1].children.append(data)

    def handle_endtag(self, tagName: str):
        if tagName not in SanetizingHTMLParser.allowed_tags:
            return
        if tagName in _UNPAIRED_TAGS:
            # these tags can have an end tag, but don't have to depending on
            # which version of HTML is used
            return
        if tagName == "t:slot":
            return
        if tagName == "t:attr":
            if not self._allow_slots:
                return
            tagName = ""
        #if tagName in ("ol", "ul") and self._stack[-1].tagName == "li":
        #    self._stack.pop()
        expected_tag = self._stack.pop()
        if tagName != expected_tag.tagName:
            raise HTMLParseError(f"Invalid HTML detected: Expected end of tag "
                                 f"'{expected_tag.tagName}', but got '{tagName}'")

    def close(self):
        super().close()
        if len(self._stack) != 1:
            raise HTMLParseError("Unclosed tag detected")


def parse_html(data: str, allow_slots=False) -> Tag:
    p = SanetizingHTMLParser(allow_slots=allow_slots)
    p.feed(data)
    p.close()
    return p.root


@interface.implementer(common.ITagProcessor)
class TagToMatrixFormatter:
    styled_tagnames = {"bold": "b", "italic": "i", "underline": "u",
                       "strike": "del"}
    style_attr_order = ("bold", "italic", "underline", "strike")

    def __init__(self):
        self.buffer = ""
        self._slotDataStack = deque()
        self._slotDataStack.append({})
        self._rainbow_position = 0
        self._rainbow_content_length = 0

    def handle_slot(self, slt: slot):
        self.handle_data(self._slotDataStack[-1][slt.name])

    def handle_starttag(self, tag: Tag):
        tagName = tag.tagName
        if tagName == "rainbow":
            slotData = {}
            self._rainbow_content_length = len(common.to_plaintext(
                tag.clone().fillSlots(**self._slotDataStack[-1])))
            return
        slotData = {**self._slotDataStack[-1], **(tag.slotData or {})}
        self._slotDataStack.append(slotData)
        attributes = {}
        for attr in TagToMatrixFormatter.style_attr_order:
            if attr in tag.attributes:
                self.buffer += f"<{TagToMatrixFormatter.styled_tagnames[attr]}>"
        if color := tag.attributes.get("color", None):
            if isinstance(color, Tag):
                color = common.handle_attribute_tag(color, self._slotDataStack)
            attributes["color"] = color_to_string(color)
            tagName = "font"
        if color := tag.attributes.get("background-color", None):
            if isinstance(color, Tag):
                color = common.handle_attribute_tag(color, self._slotDataStack)
            attributes["data-mx-bg-color"] = color_to_string(color)
            tagName = "font"
        if href := tag.attributes.get("href", None):
            if isinstance(href, Tag):
                href = common.handle_attribute_tag(href, self._slotDataStack)
            attributes["href"] = href
        if not tagName:
            return
        self.buffer += "<" + tagName
        for key, value in attributes.items():
            self.buffer += f" {key}=\"{value}\""
        self.buffer += ">"

    def handle_data(self, data: str):
        def rainbow_color_at(relative_position: float) -> str:
            if relative_position > 1 or relative_position < 0:
                raise ValueError("relative position in rainbow has to be in [0,1]")
            index = int(relative_position * (len(common.RAINBOW_COLORS) - 1))
            current_color = common.RAINBOW_COLORS[index]
            next_color = common.RAINBOW_COLORS[index + 1]
            blend_factor = relative_position * (len(common.RAINBOW_COLORS) - 1) - index
            return common.interpolate_color(current_color, next_color, blend_factor)

        data = htmlescape(data)
        if self._rainbow_content_length:
            for char in data:
                color = rainbow_color_at(self._rainbow_position / self._rainbow_content_length)
                self._rainbow_position += 1
                self.buffer += f"<font color=\"{color}\">{char}</font>"
        else:
            self.buffer += data

    def handle_endtag(self, tag: Tag):
        self._slotDataStack.pop()
        if tag.tagName == "rainbow":
            self._rainbow_content_length = 0
            return
        if not tag.tagName:
            return
        if tag.tagName in _UNPAIRED_TAGS:
            return
        if (tag.attributes.get("color", None) or tag.attributes.get("background-color",
                                                                    None)):
            tagName = "font"
        else:
            tagName = tag.tagName
        self.buffer += f"</{tagName}>"
        for attr in TagToMatrixFormatter.style_attr_order[::-1]:
            if attr in tag.attributes:
                self.buffer += f"</{TagToMatrixFormatter.styled_tagnames[attr]}>"


def to_matrix(data: Message) -> str:
    if isinstance(data, str):
        return data
    formatter = TagToMatrixFormatter()
    common._processStyledText(data, formatter)
    return formatter.buffer


rainbow_style = ("background:linear-gradient(to right, " +
                 f"{', '.join(c.name for c in common.RAINBOW_COLORS)});" +
                 "color:transparent;background-clip:text;-webkit-background-clip:text")


@interface.implementer(common.ITagProcessor)
class TagModernizer:
    def __init__(self):
        self.root = None
        self._parent_stack = deque()

    def handle_slot(self, slt: slot):
        self._parent_stack[-1].children.append(slot(slt.name))

    def handle_starttag(self, tag: Tag):
        tagName = tag.tagName
        attributes = {}
        style = []
        if tagName == "rainbow":
            tagName = "span"
            style = [rainbow_style]
        elif tagName == "font":
            tagName = "span"
        new_tag = Tag(tagName)
        if self.root is None:
            self.root = new_tag
        if color := tag.attributes.get("color", None):
            style.append("color:")
            if isinstance(color, Tag):
                for child in color.children:
                    if isinstance(child, slot):
                        style.append(slot(child.name))
                    else:
                        style.append(color_to_string(child))
            else:
                style.append(color_to_string(color))
            style.append(";")
        if color := tag.attributes.get("background-color", None):
            style.append("background-color:")
            if isinstance(color, Tag):
                for child in color.children:
                    if isinstance(child, slot):
                        style.append(slot(child.name))
                    else:
                        style.append(color_to_string(child))
            else:
                style.append(color_to_string(color))
            style.append(";")
        if tag.attributes.get("bold", False):
            style.append("font-weight:bold;")
        if tag.attributes.get("italic", False):
            style.append("font-style:italic;")
        if tag.attributes.get("underline", False):
            style.append("text-decoration:underline;")
        if tag.attributes.get("strike", False):
            style.append("text-decoration:line-through;")
        if href := tag.attributes.get("href", None):
            attributes["href"] = href
        if style:
            if any(map(lambda x: not isinstance(x, str), style)):
                attributes["style"] = Tag("")(*style)
            else:
                attributes["style"] = "".join(style)
        new_tag.attributes = attributes
        if tag.slotData:
            for key, value in tag.slotData.items():
                if isinstance(value, ColorCodes):
                    value = value.name
                new_tag.fillSlots(**{key: value})
        if self._parent_stack:
            self._parent_stack[-1].children.append(new_tag)
        self._parent_stack.append(new_tag)

    def handle_data(self, data: str):
        if self._parent_stack:
            self._parent_stack[-1].children.append(data)

    def handle_endtag(self, tag: Tag):
        self._parent_stack.pop()


def modernize_html(data: Message) -> Message:
    if isinstance(data, str):
        return data
    processor = TagModernizer()
    common._processStyledText(data, processor)
    return processor.root

