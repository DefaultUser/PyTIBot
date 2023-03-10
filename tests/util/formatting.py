from twisted.trial import unittest

from typing import Any

from twisted.web.template import Tag, tags, slot

from util.formatting import ColorCodes
from util.formatting import html as htmlformatting
from util.formatting import irc as ircformatting


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

def _compare_styled_string(testcase: unittest.TestCase, l1: list[Tag|str],
                           l2: list[Tag|str]):
    testcase.assertEqual(len(l1), len(l2))
    for item1, item2 in zip(l1, l2):
        _compare_tags(testcase, item1, item2)


class HTMLParserTestCase(unittest.TestCase):
    def _test_parser(self, input_value, expected_outcome):
        parse_result = htmlformatting.parse_html(input_value)
        _compare_tags(self, parse_result, expected_outcome)

    def _test_parser_with_slots(self, input_value, expected_outcome):
        parse_result = htmlformatting.parse_html(input_value, allow_slots=True)
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
        self.assertRaises(htmlformatting.HTMLParseError,
                          htmlformatting.parse_html,
                          '<font color="red">foo')


class IRCParserTestCase(unittest.TestCase):
    def _test_parser(self, input_value, expected_outcome):
        parse_result = ircformatting.parse_irc(input_value)
        _compare_tags(self, parse_result, expected_outcome)

    def test_simple_string(self):
        self._test_parser("foo", Tag("")("foo"))

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

