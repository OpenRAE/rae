"""One shared RFC 6901 token implementation (issue #1710, ADR-118)."""

from __future__ import annotations

import pytest
from raes_contracts.json_pointer import escape_token, pointer_from_tokens, pointer_tokens, unescape_token

# RFC 6901 section 5: each pointer and the reference tokens it decodes to.
_RFC_6901_SECTION_5 = (
    ("", ()),
    ("/foo", ("foo",)),
    ("/foo/0", ("foo", "0")),
    ("/", ("",)),
    ("/a~1b", ("a/b",)),
    ("/c%d", ("c%d",)),
    ("/e^f", ("e^f",)),
    ("/g|h", ("g|h",)),
    ("/i\\j", ("i\\j",)),
    ('/k"l', ('k"l',)),
    ("/ ", (" ",)),
    ("/m~0n", ("m~n",)),
)


@pytest.mark.parametrize(("pointer", "tokens"), _RFC_6901_SECTION_5)
def test_rfc_6901_examples_decode_and_encode(pointer, tokens):
    assert pointer_tokens(pointer) == tokens
    assert pointer_from_tokens(tokens) == pointer


def test_escape_replaces_tilde_before_slash():
    assert escape_token("a~b/c") == "a~0b~1c"
    assert escape_token("~1") == "~01"
    assert escape_token("/~") == "~1~0"
    assert escape_token("") == ""
    assert escape_token("é/ü") == "é~1ü"


def test_unescape_replaces_tilde_one_before_tilde_zero():
    # RFC 6901 section 4: "~01" becomes "~1", never "/".
    assert unescape_token("~01") == "~1"
    assert unescape_token("a~0b~1c") == "a~b/c"
    assert unescape_token("~1~0") == "/~"


def test_unescape_keeps_tokens_that_are_not_escape_sequences():
    for token in ("~", "~2", "a~", "~~", "%2F", "é"):
        assert unescape_token(token) == token


@pytest.mark.parametrize("token", ["", "~", "/", "~0", "~1", "~01", "a/b~c", "//~~", "é~1/"])
def test_escape_and_unescape_are_inverse(token):
    assert unescape_token(escape_token(token)) == token


def test_empty_token_list_is_the_whole_document_pointer():
    assert pointer_from_tokens(()) == ""
    assert pointer_from_tokens([""]) == "/"
    assert pointer_from_tokens(token for token in ("a", "b/c")) == "/a/b~1c"


def test_pointer_tokens_keeps_empty_tokens_and_ignores_text_before_the_first_slash():
    assert pointer_tokens("//") == ("", "")
    assert pointer_tokens("/a//b") == ("a", "", "b")
    assert pointer_tokens("abc/def") == ("def",)
    assert pointer_tokens("abc") == ()
