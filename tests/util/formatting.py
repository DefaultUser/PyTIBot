# PyTIBot - Formatting Helper
# Copyright (C) <2023>  <Sebastian Schmidt>

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

from twisted.trial import unittest

from typing import Any

from twisted.web.template import Tag, tags, slot

from util.formatting import ColorCodes, to_irc, to_plaintext, to_matrix
from util.formatting import irc
from util.formatting import html


def _compare_tags(testcase: unittest.TestCase, item1: Any, item2: Any):
    testcase.assertEqual(type(item1), type(item2))
    if isinstance(item1, slot):
        testcase.assertEqual(item1.name, item2.name)
    elif not isinstance(item1, Tag):
        testcase.assertEqual(item1, item2)
    else:
        testcase.assertEqual(item1.tagName, item2.tagName)
        testcase.assertEqual(item1.attributes.keys(), item2.attributes.keys())
        for key in item1.attributes.keys():
            _compare_tags(testcase, item1.attributes[key],
                          item2.attributes[key])
        testcase.assertEqual(item1.slotData, item2.slotData)
        testcase.assertEqual(len(item1.children), len(item2.children))
        for child_of_item1, child_of_item2 in zip(item1.children,
                                                  item2.children):
            _compare_tags(testcase, child_of_item1, child_of_item2)


class PlaintextFormattingTestCase(unittest.TestCase):
    def _test_formatting(self, input_value, expected_outcome):
        result = to_plaintext(input_value)
        self.assertEqual(result, expected_outcome)

    def test_simple_string(self):
        input_string = "foo"
        self._test_formatting(input_string, input_string)

    def test_simple_bold(self):
        msg = Tag("")(tags.b("foo"))
        self._test_formatting(msg, "foo")

    def test_simple_fgcolor(self):
        fg = ColorCodes.red
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "foo")

    def test_simple_bgcolor(self):
        fg = ColorCodes.red
        bg = ColorCodes.blue
        msg = Tag("")(tags.font("foo", **{"color": fg, "background-color": bg}))
        self._test_formatting(msg, "foo")

    def test_simple_italic(self):
        msg = Tag("")(tags.i("foo"))
        self._test_formatting(msg, "foo")

    def test_simple_underlined(self):
        msg = Tag("")(tags.u("foo"))
        self._test_formatting(msg, "foo")

    def test_simple_newline(self):
        msg = Tag("")("foo\nbar")
        self._test_formatting(msg, "foo\nbar")
        msg = Tag("")("foo", tags.br(), "bar")
        self._test_formatting(msg, "foo\nbar")
        msg = Tag("")(tags.br(), "bar")
        self._test_formatting(msg, "bar")

    def test_simple_rainbow(self):
        msg = Tag("")(Tag("rainbow")("abcdef"))
        self._test_formatting(msg, "abcdef")
        msg = Tag("")(Tag("rainbow")("abc", tags.b("def")))
        self._test_formatting(msg, "abcdef")

    def test_simple_href(self):
        msg = Tag("")(tags.a("foo", href="example.com"))
        self._test_formatting(msg, "foo (example.com)")

    def test_newline_styled(self):
        msg = Tag("")("foo", tags.b("bar\nbaz"))
        self._test_formatting(msg, "foobar\nbaz")
        msg = Tag("")("foo", tags.b("bar", tags.br(), "baz"))
        self._test_formatting(msg, "foobar\nbaz")
        msg = Tag("")(tags.b(tags.i("bar", tags.br(), "baz")))
        self._test_formatting(msg, "bar\nbaz")
        msg = Tag("")(tags.b(tags.br(), "foo"))
        self._test_formatting(msg, "foo")

    def test_simple_display_blocks(self):
        msg = Tag("")("foo", tags.p("bar"), "baz")
        self._test_formatting(msg, "foo\nbar\nbaz")
        msg = Tag("")(tags.div("bar"), "baz")
        self._test_formatting(msg, "bar\nbaz")
        msg = Tag("")(tags.div("foo"))
        self._test_formatting(msg, "foo")

    def test_sequential_tags(self):
        msg = Tag("")(tags.b("foo"), tags.i("bar"))
        self._test_formatting(msg, "foobar")

    def test_nested_tags(self):
        msg = Tag("")(tags.b(tags.b("foo")))
        self._test_formatting(msg, "foo")
        msg = Tag("")(tags.b(tags.i("foo"), tags.b("bar")))
        self._test_formatting(msg, "foobar")
        # colors
        fg = ColorCodes.red
        bg = ColorCodes.blue
        msg = Tag("")(tags.font("foo", tags.font("bar", color=fg), color=fg))
        self._test_formatting(msg, "foobar")
        # bg color
        msg = Tag("")(tags.font("foo", tags.font("bar", color=fg),
                                    **{"color": fg, "background-color": bg}))
        self._test_formatting(msg, "foobar")

    def test_nested_with_href(self):
        msg = Tag("")("foo", tags.a(tags.b("foo"), href="example.com"))
        self._test_formatting(msg, "foofoo (example.com)")

    def test_slot(self):
        msg = Tag("")("foo", tags.b(slot("slt"), "bar").fillSlots(slt=" "))
        self._test_formatting(msg, "foo bar")
        msg = Tag("")("foo", tags.b(slot("slt"), "bar"))
        self.assertRaises(KeyError, to_plaintext, msg)


class IrcFormattingTestCase(unittest.TestCase):
    def _test_formatting(self, input_value, expected_outcome):
        result = to_irc(input_value)
        self.assertEqual(result, expected_outcome)

    def test_simple_string(self):
        input_string = "foo"
        self._test_formatting(input_string, input_string)

    def test_simple_display_blocks(self):
        msg = Tag("")("foo", tags.p("bar"), "baz")
        self._test_formatting(msg, "foo\nbar\nbaz")
        msg = Tag("")(tags.div("bar"), "baz")
        self._test_formatting(msg, "bar\nbaz")
        msg = Tag("")(tags.div("foo"))
        self._test_formatting(msg, "foo")

    def test_simple_bold(self):
        msg = Tag("")(tags.b("foo"))
        self._test_formatting(msg, "\x02foo\x02")
        msg = Tag("")(tags.strong("foo"))
        self._test_formatting(msg, "\x02foo\x02")
        msg = Tag("")(tags.span("foo", bold=True))
        self._test_formatting(msg, "\x02foo\x02")

    def test_simple_fgcolor(self):
        fg = ColorCodes.red
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "\x03" + fg.value + "foo\x03")
        msg = Tag("")(tags.span("foo", color=fg))
        self._test_formatting(msg, "\x03" + fg.value + "foo\x03")

    def test_simple_fgcolor_named(self):
        fg = "red"
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "\x0304foo\x03")

    def test_simple_fgcolor_hex(self):
        fg = "#ff0000"
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "\x0304foo\x03")
        fg = "#fe0000"
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "\x0304foo\x03")
        fg = "#e00"
        msg = Tag("")(tags.font("foo", color=fg))
        self._test_formatting(msg, "\x0304foo\x03")

    def test_simple_bgcolor(self):
        fg = ColorCodes.red
        bg = ColorCodes.blue
        msg = Tag("")(tags.font("foo", **{"color": fg,
                                              "background-color": bg}))
        self._test_formatting(msg,
                              "\x03" + fg.value + "," + bg.value + "foo\x03")

    def test_bgcolor_without_fgcolor(self):
        # bgcolor can only be shown in conjunction with fgcolor
        bg = ColorCodes.blue
        msg = Tag("")(tags.font("foo", **{"background-color": bg}))
        self._test_formatting(msg, "foo")

    def test_simple_italic(self):
        msg = Tag("")(tags.i("foo"))
        self._test_formatting(msg, "\x1dfoo\x1d")
        msg = Tag("")(tags.em("foo"))
        self._test_formatting(msg, "\x1dfoo\x1d")
        msg = Tag("")(tags.cite("foo"))
        self._test_formatting(msg, "\x1dfoo\x1d")
        msg = Tag("")(tags.span("foo", italic=True))
        self._test_formatting(msg, "\x1dfoo\x1d")

    def test_simple_strike(self):
        msg = Tag("")(Tag("del")("foo"))
        self._test_formatting(msg, "\x1efoo\x1e")
        msg = Tag("")(tags.strike("foo"))
        self._test_formatting(msg, "\x1efoo\x1e")
        msg = Tag("")(tags.s("foo"))
        self._test_formatting(msg, "\x1efoo\x1e")
        msg = Tag("")(tags.span("foo", strike=True))
        self._test_formatting(msg, "\x1efoo\x1e")

    def test_simple_underlined(self):
        msg = Tag("")(tags.u("foo"))
        self._test_formatting(msg, "\x1ffoo\x1f")
        msg = Tag("")(tags.span("foo", underline=True))
        self._test_formatting(msg, "\x1ffoo\x1f")

    def test_simple_newline(self):
        msg = Tag("")("foo\nbar")
        self._test_formatting(msg, "foo\nbar")
        msg = Tag("")("foo", tags.br(), "bar")
        self._test_formatting(msg, "foo\nbar")
        msg = Tag("")(tags.br(), "bar")
        self._test_formatting(msg, "bar")

    def test_simple_rainbow(self):
        msg = Tag("")(Tag("rainbow")("abcdef"))
        self._test_formatting(msg,
                              "\x0304a\x0307b\x0309c\x0311d\x0312e\x0313f\x03")

    def test_simple_href(self):
        msg = Tag("")(tags.a("foo", href="example.com"))
        self._test_formatting(msg, "foo (example.com)")

    def test_newline_styled(self):
        msg = Tag("")("foo", tags.b("bar\nbaz"))
        self._test_formatting(msg, "foo\x02bar\n\x02baz\x02")
        msg = Tag("")("foo", tags.b("bar", tags.br(), "baz"))
        self._test_formatting(msg, "foo\x02bar\n\x02baz\x02")
        msg = Tag("")(tags.b(tags.i("bar", tags.br(), "baz")))
        self._test_formatting(msg, "\x02\x1dbar\n\x02\x1dbaz\x1d\x02")
        msg = Tag("")(tags.b(tags.br(), "foo"))
        self._test_formatting(msg, "\x02foo\x02")
        fg = ColorCodes.red
        bg = ColorCodes.blue
        msg = Tag("")(tags.font(" ", tags.br(), "foo",
                                    **{"color": fg, "background-color": bg}))
        self._test_formatting(msg,
                              "\x03" + fg.value + "," + bg.value + " \n\x03" +
                              fg.value + "," + bg.value + "foo\x03")

    def test_sequential_tags(self):
        msg = Tag("")(tags.b("foo"), tags.i("bar"))
        self._test_formatting(msg, "\x02foo\x02\x1dbar\x1d")
        msg = Tag("")(tags.b("foo"), tags.b("bar"))
        self._test_formatting(msg, "\x02foo\x02\x02bar\x02")

    def test_nested_repeated_tags(self):
        msg = Tag("")(tags.b(tags.b("foo")))
        self._test_formatting(msg, "\x02foo\x02")
        msg = Tag("")(tags.b(tags.b("foo"), tags.b("bar")))
        self._test_formatting(msg, "\x02foobar\x02")
        msg = Tag("")(tags.b(tags.i("foo"), tags.b("bar")))
        self._test_formatting(msg, "\x02\x1dfoo\x1dbar\x02")

    def test_nested_color_tags(self):
        fg = ColorCodes.red
        fg2 = ColorCodes.green
        bg = ColorCodes.blue
        # same fg and bg color
        msg = Tag("")(tags.font("foo", tags.font("bar", color=fg),
                                    color=fg))
        self._test_formatting(msg, "\x03" + fg.value + "foobar\x03")
        # outer has fg and bg, inner only the same fg
        msg = Tag("")(tags.font("foo", tags.font("bar", color=fg),
                                    **{"color": fg, "background-color": bg}))
        self._test_formatting(msg,
                              "\x03" + fg.value + "," + bg.value + "foo\x03" +
                              fg.value + "bar\x03")
        # outer has fg and bg, inner only another fg
        msg = Tag("")(tags.font("foo", tags.font("bar", color=fg2), "baz",
                                    **{"color": fg, "background-color": bg}))
        self._test_formatting(msg,
                              "\x03" + fg.value + "," + bg.value + "foo\x03" +
                              fg2.value + "bar\x03" + fg.value + "baz\x03")
        # outer has no bg color -> after inner tag,
        # all color info has to be cleared and reset to outer style
        msg = Tag("")(tags.font("foo", tags.font("bar",
                                                     **{"color": fg2,
                                                        "background-color": bg}),
                                    "spam", color=fg))
        self._test_formatting(msg,
                              "\x03" + fg.value + "foo\x03" + fg2.value + "," +
                              bg.value + "bar\x03\x03" + fg.value + "spam\x03")
        # same as above, but the outer font tag has no final text child
        # the end could be optimized away, but for now this is good enough
        msg = Tag("")(tags.font("foo", tags.font("bar",
                                                     **{"color": fg,
                                                        "background-color": bg}),
                                    color=fg))
        self._test_formatting(msg,
                              "\x03" + fg.value + "foo\x03" + fg.value + "," +
                              bg.value + "bar\x03\x03" + fg.value + "\x03")

    def test_nested_rainbow(self):
        msg = Tag("")(Tag("rainbow")("abc", tags.b("def")))
        self._test_formatting(msg,
                              "\x0304a\x0307b\x0309c\x02\x0311d\x0312e"
                              "\x0313f\x02\x03")
        # rainbow inhibits inner tag's color information
        fg = ColorCodes.green
        msg = Tag("")(Tag("rainbow")("abc", tags.font("def", color=fg)))
        self._test_formatting(msg,
                              "\x0304a\x0307b\x0309c\x0311d\x0312e\x0313f\x03")
        # rainbow inside a colored block, not the same color as rainbow start or end
        fg = ColorCodes.green
        msg = Tag("")(tags.font("foo ", Tag("rainbow")("abcdef"), " bar",
                                    color=fg))
        self._test_formatting(msg,
                              "\x03" + fg.value +
                              "foo \x0304a\x0307b\x0309c\x0311d\x0312e\x0313f\x03" +
                              fg.value + " bar\x03")
        # rainbow inside a colored block, the same color as rainbow start
        fg = ColorCodes.red
        msg = Tag("")(tags.font("foo ", Tag("rainbow")("abcdef"), " bar",
                                    color=fg))
        self._test_formatting(msg,
                              "\x03" + fg.value +
                              "foo a\x0307b\x0309c\x0311d\x0312e\x0313f\x03" +
                              fg.value + " bar\x03")
        # rainbow inside a colored block, the same color as rainbow end
        fg = ColorCodes.magenta
        msg = Tag("")(tags.font("foo ", Tag("rainbow")("abcdef"), " bar",
                                    color=fg))
        self._test_formatting(msg,
                              "\x03" + fg.value + "foo \x0304a\x0307b\x0309c"
                              "\x0311d\x0312e\x0313f bar\x03")

    def test_nested_with_href(self):
        msg = Tag("")("foo", tags.a(tags.b("foo"), href="example.com"))
        self._test_formatting(msg, "foo\x02foo\x02 (example.com)")
        msg = Tag("")("foo", tags.b(tags.a("foo", href="example.com")))
        self._test_formatting(msg, "foo\x02foo (example.com)\x02")

    def test_slot(self):
        msg = Tag("")("foo", tags.b(slot("slt"), "bar").fillSlots(slt=" "))
        self._test_formatting(msg, "foo\x02 bar\x02")
        msg = Tag("")("foo", tags.b(slot("slt"), "bar"))
        self.assertRaises(KeyError, to_irc, msg)

    def test_attr_slot(self):
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))).fillSlots(slt="red"))
        self._test_formatting(msg, "\x0304foo\x03")
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt")))).fillSlots(slt="red")
        self._test_formatting(msg, "\x0304foo\x03")
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))).fillSlots(slt=ColorCodes.red))
        self._test_formatting(msg, "\x0304foo\x03")
        msg = Tag("")(tags.a("foo", href=Tag("")(slot("slt"))).fillSlots(slt="example.com"))
        self._test_formatting(msg, "foo (example.com)")
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))))
        self.assertRaises(KeyError, to_irc, msg)

    def test_rainbow_with_slot(self):
        msg = Tag("")(Tag("rainbow")("abc", slot("slt"))).fillSlots(slt="def")
        self._test_formatting(msg,
                              "\x0304a\x0307b\x0309c\x0311d\x0312e\x0313f\x03")


class MatrixFormattingTestCase(unittest.TestCase):
    def _test_formatting(self, input_value, expected_outcome):
        result = to_matrix(input_value)
        self.assertEqual(result, expected_outcome)

    def test_simple_string(self):
        input_string = "foo"
        self._test_formatting(input_string, input_string)

    def test_attributes(self):
        msg = Tag("")(tags.font("foo", color=ColorCodes.red))
        self._test_formatting(msg, '<font color="red">foo</font>')
        msg = Tag("")(tags.font("foo", color=ColorCodes.dark_yellow))
        self._test_formatting(msg, '<font color="darkorange">foo</font>')
        msg = Tag("")(tags.font("foo", color="#ff00ff"))
        self._test_formatting(msg, '<font color="#ff00ff">foo</font>')
        msg = Tag("")(tags.font("foo", **{"background-color": "#ff00ff"}))
        self._test_formatting(msg,
                              '<font data-mx-bg-color="#ff00ff">foo</font>')
        msg = Tag("")(tags.div("foo", color=ColorCodes.red))
        self._test_formatting(msg, '<font color="red">foo</font>')

    def test_multiple_attributes(self):
        msg = Tag("")(tags.span("foo", bold=True, strike=True))
        self._test_formatting(msg, '<b><del><span>foo</span></del></b>')
        msg = Tag("")(tags.span("foo", bold=True, strike=True,
                                    color=ColorCodes.red))
        self._test_formatting(msg,
                              '<b><del><font color="red">foo</font></del></b>')

    def test_simple_rainbow(self):
        msg = Tag("")(Tag("rainbow")("abcdef"))
        self._test_formatting(msg,
                              '<font color="#ff0000">a</font><font color="#fd6a00">'
                              'b</font><font color="#54d200">c</font>'
                              '<font color="#00fe80">d</font><font color="#00aafe">'
                              'e</font><font color="#2b00fd">f</font>')

    def test_nested_rainbow(self):
        msg = Tag("")("foo", Tag("rainbow")("abc", tags.b("def")))
        self._test_formatting(msg,
                              'foo<font color="#ff0000">a</font><font color="#fd6a00">'
                              'b</font><font color="#54d200">c</font><b>'
                              '<font color="#00fe80">d</font><font color="#00aafe">'
                              'e</font><font color="#2b00fd">f</font></b>')

    def test_slot(self):
        msg = Tag("")("foo ", tags.b(slot("slt"), " bar").fillSlots(slt="baz"))
        self._test_formatting(msg, "foo <b>baz bar</b>")
        msg = Tag("")("foo", tags.b(slot("slt"), "bar"))
        self.assertRaises(KeyError, to_matrix, msg)

    def test_attr_slot(self):
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))).fillSlots(
            slt="red"))
        self._test_formatting(msg, '<font color="red">foo</font>')
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))).fillSlots(
            slt=ColorCodes.red))
        self._test_formatting(msg, '<font color="red">foo</font>')
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))))
        self.assertRaises(KeyError, to_matrix, msg)

    def test_rainbow_with_slot(self):
        msg = Tag("")(Tag("rainbow")("abc", slot("slt"))).fillSlots(slt="def")
        self._test_formatting(msg,
                              '<font color="#ff0000">a</font><font color="#fd6a00">'
                              'b</font><font color="#54d200">c</font>'
                              '<font color="#00fe80">d</font><font color="#00aafe">'
                              'e</font><font color="#2b00fd">f</font>')

    def test_escape_html(self):
        msg = Tag("")(tags.span("<b>foo</b>"))
        self._test_formatting(msg, "<span>&lt;b&gt;foo&lt;/b&gt;</span>")


RAINBOW_STYLE_CSS = ("background:linear-gradient(to right, red, darkorange, "
                     "green, cyan, blue, magenta);color:transparent;"
                     "background-clip:text;-webkit-background-clip:text")


class HTMLTagModernizerTestCase(unittest.TestCase):
    def _test_formatting(self, input_value, expected_outcome):
        result = html.modernize_html(input_value)
        _compare_tags(self, result, expected_outcome)

    def test_simple_string(self):
        input_string = "foo"
        self._test_formatting(input_string, input_string)

    def test_attributes(self):
        msg = Tag("")(tags.font("foo", color=ColorCodes.red))
        self._test_formatting(msg, Tag("")(tags.span("foo", style="color:red;")))
        msg = Tag("")(tags.font("foo", color=ColorCodes.dark_yellow))
        self._test_formatting(msg, Tag("")(tags.span("foo", style="color:darkorange;")))
        msg = Tag("")(tags.font("foo", color="#ff00ff"))
        self._test_formatting(msg, Tag("")(tags.span("foo", style="color:#ff00ff;")))
        msg = Tag("")(tags.div("foo", bold=True))
        self._test_formatting(msg, Tag("")(tags.div("foo", style="font-weight:bold;")))
        msg = Tag("")(tags.div("foo", italic=True))
        self._test_formatting(msg, Tag("")(tags.div("foo", style="font-style:italic;")))
        msg = Tag("")(tags.div("foo", strike=True))
        self._test_formatting(msg, Tag("")(tags.div("foo", style="text-decoration:line-through;")))
        msg = Tag("")(tags.div("foo", underline=True))
        self._test_formatting(msg, Tag("")(tags.div("foo", style="text-decoration:underline;")))

    def test_simple_rainbow(self):
        msg = Tag("")(Tag("rainbow")("abc", tags.b("def")))
        self._test_formatting(msg, Tag("")(tags.span("abc", tags.b("def"),
                                                         style=RAINBOW_STYLE_CSS)))

    def test_slot(self):
        msg = Tag("")("foo ", tags.b(slot("slt"), " bar"))
        self._test_formatting(msg, Tag("")("foo ", tags.b(slot("slt"), " bar")))

    def test_attr_slot(self):
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt"))))
        self._test_formatting(msg,
                              Tag("")(tags.span("foo", style=Tag("")(
                                  "color:", slot("slt"), ";"))))
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt")))).fillSlots(slt="red")
        self._test_formatting(msg,
                              Tag("")(tags.span("foo", style=Tag("")(
                                  "color:", slot("slt"), ";"))).fillSlots(slt="red"))
        msg = Tag("")(tags.font("foo", color=Tag("")(slot("slt")))).fillSlots(slt=ColorCodes.red)
        self._test_formatting(msg,
                              Tag("")(tags.span("foo", style=Tag("")(
                                  "color:", slot("slt"), ";"))).fillSlots(slt="red"))


class HTMLParserTestCase(unittest.TestCase):
    def _test_parser(self, input_value, expected_outcome):
        parse_result = html.parse_html(input_value)
        _compare_tags(self, parse_result, expected_outcome)

    def _test_parser_with_slots(self, input_value, expected_outcome):
        parse_result = html.parse_html(input_value, allow_slots=True)
        _compare_tags(self, parse_result, expected_outcome)

    def test_simple_string(self):
        self._test_parser("foo", Tag("")("foo"))

    def test_simple_bold(self):
        self._test_parser("<b>foo</b>", Tag("")(tags.b("foo")))
        self._test_parser("foo<b>bar</b>", Tag("")("foo", tags.b("bar")))

    def test_simple_italic(self):
        self._test_parser("<i>foo</i>", Tag("")(tags.i("foo")))
        self._test_parser("foo<i>bar</i>", Tag("")("foo", tags.i("bar")))

    def test_simple_underline(self):
        self._test_parser("<u>foo</u>", Tag("")(tags.u("foo")))
        self._test_parser("foo<u>bar</u>", Tag("")("foo", tags.u("bar")))

    def test_simple_strike(self):
        self._test_parser("<del>foo</del>", Tag("")(Tag("del")("foo")))
        self._test_parser("foo<del>bar</del>", Tag("")("foo", Tag("del")("bar")))

    def test_simple_color(self):
        self._test_parser('<font color="red">foo</font>',
                          Tag("")(tags.font("foo", color=ColorCodes.red)))
        self._test_parser('<font color="darkgreen">foo</font>',
                          Tag("")(tags.font("foo", color=ColorCodes.dark_green)))
        self._test_parser('<font color="darkorange">foo</font>',
                          Tag("")(tags.font("foo", color=ColorCodes.dark_yellow)))
        self._test_parser('<font color="silver">foo</font>',
                          Tag("")(tags.font("foo", color="#c0c0c0")))
        self._test_parser('<font color="#123">foo</font>',
                          Tag("")(tags.font("foo", color="#123")))
        self._test_parser('<font data-mx-color="red">foo</font>',
                          Tag("")(tags.font("foo", color=ColorCodes.red)))
        self._test_parser('<font background-color="red">foo</font>',
                          Tag("")(tags.font("foo",
                                            **{"background-color": ColorCodes.red})))
        self._test_parser('<font data-mx-bg-color="red">foo</font>',
                          Tag("")(tags.font("foo",
                                            **{"background-color": ColorCodes.red})))

    def test_replace_css_style(self):
        self._test_parser('<span style="color:red">foo</span>',
                          Tag("")(tags.span("foo", color=ColorCodes.red)))
        self._test_parser('<span style="background-color:red">foo</span>',
                          Tag("")(tags.span("foo",
                                            **{"background-color": ColorCodes.red})))
        self._test_parser('<div style="text-decoration:line-through">foo</div>',
                          Tag("")(tags.div("foo", strike=True)))
        self._test_parser('<div style="text-decoration:underline">foo</div>',
                          Tag("")(tags.div("foo", underline=True)))
        self._test_parser('<div style="font-weight: bold">foo</div>',
                          Tag("")(tags.div("foo", bold=True)))
        self._test_parser('<div style="font-style: italic">foo</div>',
                          Tag("")(tags.div("foo", italic=True)))

    def test_img_tag(self):
        self._test_parser('<img src="example.com">',
                          Tag("")("inline image src='example.com'"))

    def test_drops_unsupported_tags(self):
        self._test_parser('<script>alert("hax")</script>',
                          Tag("")('alert("hax")'))

    def test_slots(self):
        self._test_parser('foo<t:slot name="slt"/>bar',
                          Tag("")("foo", "bar"))
        self._test_parser_with_slots('foo<t:slot name="slt"/>bar',
                                     Tag("")("foo", slot("slt"), "bar"))

    def test_attr_slot(self):
        self._test_parser('<font><t:attr name="color"><t:slot name="slt" />'
                          '</t:attr>bar</font>',
                          Tag("")(tags.font("bar")))
        self._test_parser_with_slots('<font><t:attr name="color">'
                                     '<t:slot name="slt" /></t:attr>bar</font>',
                                     Tag("")(tags.font("bar",
                                                       color=Tag("")(slot("slt")))))

    def test_invalid_html(self):
        self.assertRaises(html.HTMLParseError,
                          html.parse_html,
                          '<font color="red">foo')

    def test_escaped_html(self):
        self._test_parser("<span>&lt;b&gt;foo&lt;/b&gt;</span>",
                          Tag("")(tags.span("<b>foo</b>")))


class IRCParserTestCase(unittest.TestCase):
    def _test_parser(self, input_value, expected_outcome):
        parse_result = irc.parse_irc(input_value)
        _compare_tags(self, parse_result, expected_outcome)

    def test_simple_string(self):
        self._test_parser("foo", "foo")

    def test_simple_bold(self):
        self._test_parser("\x02foo", Tag("")(tags.b("foo")))
        self._test_parser("\x02foo\x02", Tag("")(tags.b("foo")))
        self._test_parser("bar \x02foo", Tag("")("bar ", tags.b("foo")))
        self._test_parser("bar \x02foo\x02", Tag("")("bar ", tags.b("foo")))
        self._test_parser("bar \x02foo\x02 baz", Tag("")("bar ", tags.b("foo"), " baz"))

    def test_simple_italic(self):
        self._test_parser("\x1dfoo", Tag("")(tags.i("foo")))
        self._test_parser("\x1dfoo\x1d", Tag("")(tags.i("foo")))
        self._test_parser("bar \x1dfoo", Tag("")("bar ", tags.i("foo")))
        self._test_parser("bar \x1dfoo\x1d", Tag("")("bar ", tags.i("foo")))
        self._test_parser("bar \x1dfoo\x1d baz", Tag("")("bar ", tags.i("foo"), " baz"))

    def test_simple_underline(self):
        self._test_parser("\x1ffoo", Tag("")(tags.u("foo")))
        self._test_parser("\x1ffoo\x1f", Tag("")(tags.u("foo")))
        self._test_parser("bar \x1ffoo", Tag("")("bar ", tags.u("foo")))
        self._test_parser("bar \x1ffoo\x1f", Tag("")("bar ", tags.u("foo")))
        self._test_parser("bar \x1ffoo\x1f baz", Tag("")("bar ", tags.u("foo"), " baz"))

    def test_simple_strike(self):
        self._test_parser("\x1efoo", Tag("")(Tag("del")("foo")))
        self._test_parser("\x1efoo\x1e", Tag("")(Tag("del")("foo")))
        self._test_parser("bar \x1efoo", Tag("")("bar ", Tag("del")("foo")))
        self._test_parser("bar \x1efoo\x1e", Tag("")("bar ", Tag("del")("foo")))
        self._test_parser("bar \x1efoo\x1e baz", Tag("")("bar ", Tag("del")("foo"), " baz"))

    def test_simple_color(self):
        self._test_parser("\x0312foo",
                          Tag("")(tags.font("foo", color=ColorCodes("12"))))
        self._test_parser("\x0312foo\x03",
                          Tag("")(tags.font("foo", color=ColorCodes("12"))))
        self._test_parser("bar \x0312foo",
                          Tag("")("bar ", tags.font("foo", color=ColorCodes("12"))))
        self._test_parser("bar \x0312foo\x03",
                          Tag("")("bar ", tags.font("foo", color=ColorCodes("12"))))
        self._test_parser("bar \x0312foo\x03 baz",
                          Tag("")("bar ", tags.font("foo", color=ColorCodes("12")),
                                  " baz"))
        self._test_parser("\x0312,04foo",
                          Tag("")(tags.font("foo", **{"color": ColorCodes("12"),
                                                      "background-color": ColorCodes("04")})))

    def test_simple_reset_all(self):
        self._test_parser("\x02foo\x0f bar", Tag("")(tags.b("foo"), " bar"))
        self._test_parser("\x02foo\x1dbaz\x0f bar",
                          Tag("")(tags.b("foo", tags.i("baz")), " bar"))

    def test_nested_formatting(self):
        self._test_parser("\x02foo\x1fbar\x02baz",
                          Tag("")(tags.b("foo", tags.u("bar")), tags.u("baz")))
        self._test_parser("\x02foo\x1fbar\x1fbaz",
                          Tag("")(tags.b("foo", tags.u("bar"), "baz")))

    def test_nested_color(self):
        self._test_parser("\x0312foo\x0304bar",
                          Tag("")(tags.font("foo", color=ColorCodes("12")),
                                  tags.font("bar", color=ColorCodes("04"))))
        self._test_parser("\x0312,01foo\x0304bar",
                          Tag("")(tags.font("foo", **{"color": ColorCodes("12"),
                                                      "background-color": ColorCodes("01")}),
                                  tags.font("bar", **{"color": ColorCodes("04"),
                                                      "background-color": ColorCodes("01")})))
        self._test_parser("\x0312,01foo\x0304,12bar",
                          Tag("")(tags.font("foo", **{"color": ColorCodes("12"),
                                                      "background-color": ColorCodes("01")}),
                                  tags.font("bar", **{"color": ColorCodes("04"),
                                                      "background-color": ColorCodes("12")})))

    def test_automatic_links(self):
        self._test_parser("foo http://example.com bar",
                          Tag("")("foo ",
                                  tags.a("http://example.com", href="http://example.com"),
                                  " bar"))
        self._test_parser("\x02foo \x02http://example.com bar",
                          Tag("")(tags.b("foo "),
                                  tags.a("http://example.com", href="http://example.com"),
                                  " bar"))
        self._test_parser("\x02foo http://example.com\x02 bar",
                          Tag("")(tags.b("foo ",
                                         tags.a("http://example.com",
                                                href="http://example.com")),
                                  " bar"))

