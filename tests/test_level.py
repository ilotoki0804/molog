import pytest
from molog import _level


def test_normalize_level():
    for level, level_name in _level._levelToName.items():
        assert _level.normalizeLevel(level) == level
        assert _level.normalizeLevel(level_name) == level

    assert _level.normalizeLevel(345) == 345
    with pytest.raises(TypeError):
        _level.normalizeLevel(12.3)  # type: ignore
    with pytest.raises(TypeError):
        _level.normalizeLevel([])  # type: ignore


def test_get_level_name():
    for level, level_name in _level._levelToName.items():
        assert _level.getLevelName(level) == level_name

    assert _level.getLevelName(34) == "Level 34"

    with pytest.raises(TypeError):
        _level.getLevelName("hello")  # type: ignore
    with pytest.raises(TypeError):
        _level.getLevelName("ERROR")  # type: ignore
    with pytest.raises(TypeError):
        _level.getLevelName(2.3)  # type: ignore
    with pytest.raises(TypeError):
        _level.getLevelName([])  # type: ignore


def test_add_level_name():
    _level.addLevelName(234, "HELLO")
    assert _level.getLevelName(234) == "HELLO"
    assert _level.normalizeLevel(234) == 234
    assert _level.normalizeLevel("HELLO") == 234

    with pytest.raises(TypeError):
        _level.addLevelName([], "HELLO")  # type: ignore
    with pytest.raises(TypeError):
        _level.addLevelName(123, [])  # type: ignore

    del _level._levelToName[234]
    del _level._nameToLevel["HELLO"]
