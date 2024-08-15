import collections.abc
import contextlib
import os
import sys
import threading
import time

from ._base import _startTime, logAsyncioTasks, logMultiprocessing, logProcesses, logThreads
from ._level import getLevelName


class LogRecord:
    """
    A LogRecord instance represents an event being logged.

    LogRecord instances are created every time something is logged. They
    contain all the information pertinent to the event being logged. The
    main information passed in is in msg and args, which are combined
    using str(msg) % args to create the message field of the record. The
    record also includes information such as when the record was created,
    the source line where the logging call was made, and any exception
    information to be logged.
    """
    def __init__(self, name, level, pathname, lineno,
                 msg, args, exc_info, func=None, sinfo=None, **kwargs):
        """
        Initialize a logging record with interesting information.
        """
        ct = time.time_ns()
        self.name = name
        self.msg = msg

        if args and len(args) == 1 and isinstance(args[0], collections.abc.Mapping) and args[0]:
            args = args[0]
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
        self.exc_text = None      # used to cache the traceback text
        self.stack_info = sinfo
        self.lineno = lineno
        self.funcName = func
        self.created = ct / 1e9  # ns to float seconds
        # Get the number of whole milliseconds (0-999) in the fractional part of seconds.
        # Eg: 1_677_903_920_999_998_503 ns --> 999_998_503 ns--> 999 ms
        # Convert to float by adding 0.0 for historical reasons. See gh-89047
        self.msecs = (ct % 1_000_000_000) // 1_000_000 + 0.0
        if self.msecs == 999.0 and int(self.created) != ct // 1_000_000_000:
            # ns -> sec conversion can round up, e.g:
            # 1_677_903_920_999_999_900 ns --> 1_677_903_921.0 sec
            self.msecs = 0.0

        self.relativeCreated = (ct - _startTime) / 1e6
        if logThreads:
            self.thread = threading.get_ident()
            self.threadName = threading.current_thread().name
        else:  # pragma: no cover
            self.thread = None
            self.threadName = None
        if not logMultiprocessing:  # pragma: no cover
            self.processName = None
        else:
            self.processName = 'MainProcess'
            mp = sys.modules.get('multiprocessing')
            if mp is not None:
                # Errors may occur if multiprocessing has not finished loading
                # yet - e.g. if a custom import hook causes third-party code
                # to run when multiprocessing calls import. See issue 8200
                # for an example
                with contextlib.suppress(Exception):
                    self.processName = mp.current_process().name
        if logProcesses and hasattr(os, 'getpid'):
            self.process = os.getpid()
        else:
            self.process = None

        self.taskName = None
        if logAsyncioTasks:
            asyncio = sys.modules.get('asyncio')
            if asyncio:
                with contextlib.suppress(Exception):
                    self.taskName = asyncio.current_task().get_name()

    def __repr__(self):
        return f'<LogRecord: {self.name}, {self.levelno}, {self.pathname}, {self.lineno}, "{self.msg}">'

    def getMessage(self):
        """
        Return the message for this LogRecord.

        Return the message for this LogRecord after merging any user-supplied
        arguments with the message.
        """
        msg = str(self.msg)
        if self.args:
            msg = msg % self.args
        return msg


_logRecordFactory = LogRecord


def setLogRecordFactory(factory):
    """
    Set the factory to be used when instantiating a log record.

    :param factory: A callable which will be called to instantiate
    a log record.
    """
    global _logRecordFactory
    _logRecordFactory = factory


def getLogRecordFactory():
    """
    Return the factory to be used when instantiating a log record.
    """

    return _logRecordFactory


def makeLogRecord(dict):
    """
    Make a LogRecord whose attributes are defined by the specified dictionary,
    This function is useful for converting a logging event received over
    a socket connection (which is sent as a dictionary) into a LogRecord
    instance.
    """
    rv = _logRecordFactory(None, None, "", 0, "", (), None, None)
    rv.__dict__.update(dict)
    return rv
