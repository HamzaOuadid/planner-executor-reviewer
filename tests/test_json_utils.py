import pytest

from peer_loop.exceptions import MalformedResponseError
from peer_loop.json_utils import extract_json


def test_extract_plain_json():
    assert extract_json('{"a": 1, "b": "two"}') == {"a": 1, "b": "two"}


def test_extract_json_with_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_extract_json_with_plain_fence_no_language_tag():
    text = '```\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_extract_json_strips_surrounding_whitespace():
    assert extract_json('\n\n  {"a": 1}  \n') == {"a": 1}


def test_malformed_json_raises_typed_error_not_bare_exception():
    with pytest.raises(MalformedResponseError):
        extract_json("this is not json at all {{{")


def test_empty_string_raises_malformed_error():
    with pytest.raises(MalformedResponseError):
        extract_json("")


def test_none_raises_malformed_error():
    with pytest.raises(MalformedResponseError):
        extract_json(None)  # type: ignore[arg-type]


def test_json_array_at_top_level_raises_malformed_error():
    with pytest.raises(MalformedResponseError):
        extract_json("[1, 2, 3]")


def test_error_message_includes_snippet_of_raw_text():
    with pytest.raises(MalformedResponseError, match="garbage"):
        extract_json("total garbage, not json")
