# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2019-2023>  <Sebastian Schmidt>

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

from whoosh import highlight
from twisted.web.template import tags


class WhooshTagFormatter(highlight.Formatter):
    """
    Whoosh Formatter for use with twisted.web.template
    Based on whoosh's HtmlFormatter by Matt Chaput
    """
    def format_token(self, text, token, replace=False):
        ttext = highlight.get_text(text, token, replace)
        return tags.b(ttext, class_="match")

    def format_fragment(self, fragment, replace=False):
        output = []
        index = fragment.startchar
        text = fragment.text

        for t in fragment.matches:
            if t.startchar is None:
                continue
            if t.startchar < index:
                continue
            if t.startchar > index:
                output.append(self._text(text[index:t.startchar]))
            output.append(self.format_token(text, t, replace))
            index = t.endchar
        output.append(self._text(text[index:fragment.endchar]))
        return output

    def format(self, fragments, replace=False):
        formatted = [self.format_fragment(f, replace=replace)
                     for f in fragments]
        i = 1
        while i < len(formatted):
            formatted.insert(i, self.between)
            i += 2
        return tags.div(*formatted)
