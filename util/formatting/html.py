# PyTIBot - Formatting Helper
# Copyright (C) <2015-2022>  <Sebastian Schmidt>

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

