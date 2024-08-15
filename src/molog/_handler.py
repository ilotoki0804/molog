import contextlib
import io
import os
import sys
import threading
import traceback
import weakref
from types import GenericAlias

from . import _level
from ._base import _lock, _register_at_fork_reinit_lock, raiseExceptions
from ._filter import Filterer
from ._formatter import _defaultFormatter
from ._record import LogRecord

_handlers = weakref.WeakValueDictionary()  # map of handler names to handlers
_handlerList = []  # added to allow handlers to be removed in reverse of order initialized


def _removeHandlerRef(wr):
    """
    Remove a handler reference from the internal cleanup list.
    """
    # This function can be called during module teardown, when globals are
    # set to None. It can also be called from another thread. So we need to
    # preemptively grab the necessary globals and check if they're None,
    # to prevent race conditions and failures during interpreter shutdown.
    handlers, lock = _handlerList, _lock
    if lock and handlers:
        with lock, contextlib.suppress(ValueError):
            handlers.remove(wr)


def _addHandlerRef(handler):
    """
    Add a handler to the internal cleanup list using a weak reference.
    """
    with _lock:
        _handlerList.append(weakref.ref(handler, _removeHandlerRef))


def getHandlerByName(name):
    """
    Get a handler with the specified *name*, or None if there isn't one with
    that name.
    """
    return _handlers.get(name)


def getHandlerNames():
    """
    Return all known handler names as an immutable set.
    """
    return frozenset(_handlers)


class Handler(Filterer):
    """
    Handler instances dispatch logging events to specific destinations.

    The base handler class. Acts as a placeholder which defines the Handler
    interface. Handlers can optionally use Formatter instances to format
    records as desired. By default, no formatter is specified; in this case,
    the 'raw' message as determined by record.message is logged.
    """
    def __init__(self, level=_level.NOTSET):
        """
        Initializes the instance - basically setting the formatter to None
        and the filter list to empty.
        """
        Filterer.__init__(self)
        self._name = None
        self.level = _level.normalizeLevel(level)
        self.formatter = None
        self._closed = False
        # Add the handler to the global _handlerList (for cleanup on shutdown)
        _addHandlerRef(self)
        self.createLock()

    def get_name(self):
        return self._name

    def set_name(self, name):
        with _lock:
            if self._name in _handlers:
                del _handlers[self._name]
            self._name = name
            if name:
                _handlers[name] = self

    name = property(get_name, set_name)

    def createLock(self):
        """
        Acquire a thread lock for serializing access to the underlying I/O.
        """
        self.lock = threading.RLock()
        _register_at_fork_reinit_lock(self)

    def _at_fork_reinit(self):
        self.lock._at_fork_reinit()  # type: ignore

    def acquire(self):
        """
        Acquire the I/O thread lock.
        """
        if self.lock:
            self.lock.acquire()

    def release(self):
        """
        Release the I/O thread lock.
        """
        if self.lock:
            self.lock.release()

    def setLevel(self, level):
        """
        Set the logging level of this handler.  level must be an int or a str.
        """
        self.level = _level.normalizeLevel(level)

    def format(self, record):
        """
        Format the specified record.

        If a formatter is set, use it. Otherwise, use the default formatter
        for the module.
        """
        fmt = self.formatter if self.formatter else _defaultFormatter
        return fmt.format(record)

    def emit(self, record):
        """
        Do whatever it takes to actually log the specified logging record.

        This version is intended to be implemented by subclasses and so
        raises a NotImplementedError.
        """
        raise NotImplementedError('emit must be implemented '
                                  'by Handler subclasses')

    def handle(self, record):
        """
        Conditionally emit the specified logging record.

        Emission depends on filters which may have been added to the handler.
        Wrap the actual emission of the record with acquisition/release of
        the I/O thread lock.

        Returns an instance of the log record that was emitted
        if it passed all filters, otherwise a false value is returned.
        """
        rv = self.filter(record)
        if isinstance(rv, LogRecord):
            record = rv
        if rv:
            with self.lock:
                self.emit(record)
        return rv

    def setFormatter(self, fmt):
        """
        Set the formatter for this handler.
        """
        self.formatter = fmt

    def flush(self):
        """
        Ensure all logging output has been flushed.

        This version does nothing and is intended to be implemented by
        subclasses.
        """

    def close(self):
        """
        Tidy up any resources used by the handler.

        This version removes the handler from an internal map of handlers,
        _handlers, which is used for handler lookup by name. Subclasses
        should ensure that this gets called from overridden close()
        methods.
        """
        # get the module data lock, as we're updating a shared structure.
        with _lock:
            self._closed = True
            if self._name and self._name in _handlers:
                del _handlers[self._name]

    def handleError(self, record):
        """
        Handle errors which occur during an emit() call.

        This method should be called from handlers when an exception is
        encountered during an emit() call. If raiseExceptions is false,
        exceptions get silently ignored. This is what is mostly wanted
        for a logging system - most users will not care about errors in
        the logging system, they are more interested in application errors.
        You could, however, replace this with a custom handler if you wish.
        The record which was being processed is passed in to this method.
        """
        if raiseExceptions and sys.stderr:  # see issue 13807
            exc = sys.exception()
            try:
                sys.stderr.write('--- Logging error ---\n')
                traceback.print_exception(exc, limit=None, file=sys.stderr)
                sys.stderr.write('Call stack:\n')
                assert exc is not None
                # Walk the stack frame up until we're out of logging,
                # so as to print the calling context.
                frame = exc.__traceback__.tb_frame  # type: ignore
                import molog
                path = molog.__path__[0].removesuffix("/") + "/logging.py"  # type: ignore
                while frame and os.path.dirname(frame.f_code.co_filename) == path:
                    frame = frame.f_back
                if frame:
                    traceback.print_stack(frame, file=sys.stderr)
                else:
                    # couldn't find the right stack frame, for some reason
                    sys.stderr.write(f'Logged from file {record.filename}, line {record.lineno}\n')
                # Issue 18671: output logging message and arguments
                try:
                    sys.stderr.write(f'Message: {record.msg!r}\n'
                                     f'Arguments: {record.args}\n')
                except RecursionError:  # See issue 36272
                    raise
                except Exception:
                    sys.stderr.write('Unable to print the message and arguments'
                                     ' - possible formatting error.\nUse the'
                                     ' traceback above to help find the error.\n'
                                    )
            except OSError:  # pragma: no cover
                pass    # see issue 5971
            finally:
                del exc

    def __repr__(self):
        level = _level.getLevelName(self.level)
        return f'<{self.__class__.__name__} ({level})>'


class StreamHandler(Handler):
    """
    A handler class which writes logging records, appropriately formatted,
    to a stream. Note that this class does not close the stream, as
    sys.stdout or sys.stderr may be used.
    """

    terminator = '\n'

    def __init__(self, stream=None):
        """
        Initialize the handler.

        If stream is not specified, sys.stderr is used.
        """
        Handler.__init__(self)
        if stream is None:
            stream = sys.stderr
        self.stream = stream

    def flush(self):
        """
        Flushes the stream.
        """
        with self.lock:
            if self.stream and hasattr(self.stream, "flush"):
                self.stream.flush()

    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        The record is then written to the stream with a trailing newline.  If
        exception information is present, it is formatted using
        traceback.print_exception and appended to the stream.  If the stream
        has an 'encoding' attribute, it is used to determine how to do the
        output to the stream.
        """
        try:
            msg = self.format(record)
            stream = self.stream
            # issue 35046: merged two stream.writes into one.
            stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)

    def setStream(self, stream):
        """
        Sets the StreamHandler's stream to the specified value,
        if it is different.

        Returns the old stream, if the stream was changed, or None
        if it wasn't.
        """
        if stream is self.stream:
            result = None
        else:
            result = self.stream
            with self.lock:
                self.flush()
                self.stream = stream
        return result

    def __repr__(self):
        level = _level.getLevelName(self.level)
        name = getattr(self.stream, 'name', '')
        #  bpo-36015: name can be an int
        name = str(name)
        if name:
            name += ' '
        return f'<{self.__class__.__name__} {name}({level})>'

    __class_getitem__ = classmethod(GenericAlias)


class FileHandler(StreamHandler):
    """
    A handler class which writes formatted logging records to disk files.
    """
    def __init__(self, filename, mode='a', encoding=None, delay=False, errors=None):
        """
        Open the specified file and use it as the stream for logging.
        """
        # Issue #27493: add support for Path objects to be passed in
        filename = os.fspath(filename)
        # keep the absolute path, otherwise derived classes which use this
        # may come a cropper when the current directory changes
        self.baseFilename = os.path.abspath(filename)
        self.mode = mode
        self.encoding = encoding
        if "b" not in mode:
            self.encoding = io.text_encoding(encoding)
        self.errors = errors
        self.delay = delay
        # bpo-26789: FileHandler keeps a reference to the builtin open()
        # function to be able to open or reopen the file during Python
        # finalization.
        self._builtin_open = open
        if delay:
            # We don't open the stream, but we still need to call the
            # Handler constructor to set level, formatter, lock etc.
            Handler.__init__(self)
            self.stream = None
        else:
            StreamHandler.__init__(self, self._open())

    def close(self):
        """
        Closes the stream.
        """
        with self.lock:
            try:
                if self.stream:
                    try:
                        self.flush()
                    finally:
                        stream = self.stream
                        self.stream = None
                        if hasattr(stream, "close"):
                            stream.close()
            finally:
                # Issue #19523: call unconditionally to
                # prevent a handler leak when delay is set
                # Also see Issue #42378: we also rely on
                # self._closed being set to True there
                StreamHandler.close(self)

    def _open(self):
        """
        Open the current base file with the (original) mode and encoding.
        Return the resulting stream.
        """
        open_func = self._builtin_open
        return open_func(self.baseFilename, self.mode,
                         encoding=self.encoding, errors=self.errors)

    def emit(self, record):
        """
        Emit a record.

        If the stream was not opened because 'delay' was specified in the
        constructor, open it before calling the superclass's emit.

        If stream is not open, current mode is 'w' and `_closed=True`, record
        will not be emitted (see Issue #42378).
        """
        if self.stream is None and (self.mode != 'w' or not self._closed):
            self.stream = self._open()
        if self.stream:
            StreamHandler.emit(self, record)

    def __repr__(self):
        level = _level.getLevelName(self.level)
        return f'<{self.__class__.__name__} {self.baseFilename} ({level})>'


class _StderrHandler(StreamHandler):
    """
    This class is like a StreamHandler using sys.stderr, but always uses
    whatever sys.stderr is currently set to rather than the value of
    sys.stderr at handler construction time.
    """
    def __init__(self, level=_level.NOTSET):
        """
        Initialize the handler.
        """
        Handler.__init__(self, level)

    @property
    def stream(self):
        return sys.stderr


_defaultLastResort = _StderrHandler(_level.WARNING)
lastResort = _defaultLastResort


class NullHandler(Handler):
    """
    This handler does nothing. It's intended to be used to avoid the
    "No handlers could be found for logger XXX" one-off warning. This is
    important for library code, which may contain code to log events. If a user
    of the library does not configure logging, the one-off warning might be
    produced; to avoid this, the library developer simply needs to instantiate
    a NullHandler and add it to the top-level logger of the library module or
    package.
    """
    def handle(self, record):
        pass

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None

    def _at_fork_reinit(self):
        pass
