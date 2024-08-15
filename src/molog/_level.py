from ._base import _lock

CRITICAL = 50
ERROR = 40
WARNING = 30
NOTICE = 25
INFO = 20
DEBUG = 10
NOTSET = 0

_levelToName = {
    CRITICAL: 'CRITICAL',
    ERROR: 'ERROR',
    WARNING: 'WARNING',
    NOTICE: 'NOTICE',
    INFO: 'INFO',
    DEBUG: 'DEBUG',
    NOTSET: 'NOTSET',
}
_nameToLevel = {
    'CRITICAL': CRITICAL,
    'ERROR': ERROR,
    'WARNING': WARNING,
    'NOTICE': NOTICE,
    'INFO': INFO,
    'DEBUG': DEBUG,
    'NOTSET': NOTSET,
}


def normalizeLevel(level_or_name: int | str) -> int:
    if isinstance(level_or_name, int):
        level = level_or_name
    elif isinstance(level_or_name, str):
        if level_or_name not in _nameToLevel:
            raise ValueError(f"Unknown level: {level_or_name!r}")
        level = _nameToLevel[level_or_name]
    else:
        raise TypeError(f"Level not an integer or a registered level name: {level_or_name!r}")
    return level


def getLevelName(level: int) -> str:
    """
    Return the textual or numeric representation of logging level 'level'.

    If the level is one of the predefined levels (CRITICAL, ERROR, WARNING,
    INFO, DEBUG) then you get the corresponding string. If you have
    associated levels with names using addLevelName then the name you have
    associated with 'level' is returned.

    If a numeric value corresponding to one of the defined levels is passed
    in, the corresponding string representation is returned.

    If a string representation of the level is passed in, the corresponding
    numeric value is returned.

    If no matching numeric or string value is passed in, the string
    ``f'Level {level}'`` is returned.
    """
    if __debug__ and not isinstance(level, int):
        raise TypeError(f"Expect integer but got {type(level).__name__!r}")
    result = _levelToName.get(level)
    if result is not None:
        return result
    return f"Level {level}"


def addLevelName(level: int, levelName: str) -> None:
    """
    Associate 'levelName' with 'level'.

    This is used when converting levels to text during message formatting.
    """
    if __debug__:
        if not isinstance(level, int):
            raise TypeError(f"Expect integer for level but got {type(level).__name__}")
        if not isinstance(levelName, str):
            raise TypeError(f"Expect integer for level name but got {type(levelName).__name__}")

    with _lock:
        _levelToName[level] = levelName
        _nameToLevel[levelName] = level
