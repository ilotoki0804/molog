import collections.abc
import contextlib
import logging
import os
import sys
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any

from ._level import getLevelName

_SysExcInfoType = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
_ArgsType = tuple[object, ...] | collections.abc.Mapping[str, object]


class LogRecord:
    args: _ArgsType | None
    asctime: str
    created: float
    exc_info: _SysExcInfoType | None
    exc_text: str | None
    """used to cache the traceback text"""
    filename: str
    funcName: str | None
    levelname: str
    levelno: int
    lineno: int
    module: str
    msecs: float
    # Only created when logging.Formatter.format is called.
    message: str
    msg: str
    name: str
    pathname: str
    process: int | None
    processName: str | None
    relativeCreated: float
    stack_info: str | None
    thread: int | None
    threadName: str | None
    taskName: str | None

    _startTime = time.time_ns()
    """_startTime is used as the base when calculating the relative time of events"""
    logThreads = True
    """If you don't want threading information in the log, set this to False"""
    logMultiprocessing = True
    """If you don't want multiprocessing information in the log, set this to False"""
    logProcesses = True
    """If you don't want process information in the log, set this to False"""
    logAsyncioTasks = True
    """If you don't want asyncio task information in the log, set this to False"""

    def __init__(
        self,
        name: str,
        level: int,
        pathname: str,
        lineno: int,
        msg: str,
        args: _ArgsType | None,
        exc_info: _SysExcInfoType | None,
        func: str | None = None,
        sinfo: str | None = None,
    ) -> None:
        ct = time.time_ns()
        self.name = name
        self.msg = msg
        self.args = args
        self.levelname = getLevelName(level)
        self.levelno = level
        self.pathname = pathname
        try:
            self.filename = os.path.basename(pathname)
            self.module = os.path.splitext(self.filename)[0]
        except (TypeError, ValueError, AttributeError):
            self.filename = pathname
            self.module = "Unknown module"
        self.exc_info = exc_info
        self.exc_text = None
        self.stack_info = sinfo
        self.lineno = lineno
        self.funcName = func
        self.created = ct / 1e9
        self.msecs = (ct % 1_000_000_000) // 1_000_000 + 0.0
        if self.msecs == 999.0 and int(self.created) != ct // 1_000_000_000:
            self.msecs = 0.0

        self.relativeCreated = (ct - self._startTime) / 1e6
        if self.logThreads:
            self.thread = threading.get_ident()
            self.threadName = threading.current_thread().name
        else:  # pragma: no cover
            self.thread = None
            self.threadName = None
        if not self.logMultiprocessing:  # pragma: no cover
            self.processName = None
        else:
            self.processName = 'MainProcess'
            multiprocessing = sys.modules.get('multiprocessing')
            if multiprocessing is not None:
                with contextlib.suppress(Exception):
                    self.processName = multiprocessing.current_process().name
        self.process = os.getpid() if self.logProcesses and hasattr(os, 'getpid') else None
        self.taskName = None
        if self.logAsyncioTasks and (asyncio := sys.modules.get('asyncio')):
            with contextlib.suppress(Exception):
                self.taskName = asyncio.current_task().get_name()

    def __repr__(self):
        return f'<LogRecord: {self.name}, {self.levelno}, {self.pathname}, {self.lineno}, "{self.msg}">'

    if TYPE_CHECKING:
        def __setattr__(self, name: str, value: Any, /) -> None: ...


class LogRecordCompatibleLayer(LogRecord, logging.LogRecord):
    msg: str | Any

    def __init__(
        self,
        name: str,
        level: int,
        pathname: str,
        lineno: int,
        msg: str | Any,
        args: _ArgsType | None,
        exc_info: _SysExcInfoType | None,
        func: str | None = None,
        sinfo: str | None = None,
    ) -> None:
        if args and len(args) == 1:
            arg, = args
            if isinstance(arg, collections.abc.Mapping) and arg:
                args = arg
        super().__init__(name, level, pathname, lineno, msg, args, exc_info, func, sinfo)
