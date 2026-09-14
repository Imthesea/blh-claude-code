from blh.memory.text import extract_json_array, message_text


def test_message_text_str_and_none():
    assert message_text({"content": "hi"}) == "hi"
    assert message_text({"content": None}) == ""
    assert message_text({}) == ""


def test_extract_json_array_simple():
    assert extract_json_array("[0, 2]") == [0, 2]
    assert extract_json_array("here: [1, 3] and more") == [1, 3]


def test_extract_json_array_malformed():
    assert extract_json_array("no array") == []
    assert extract_json_array("[unclosed") == []


def test_extract_json_array_ignores_non_list():
    assert extract_json_array('{"a": 1}') == []
