from ._base import _lock
from ._level import _checkLevel

Logger = None


def _is_logger(obj: type):
    global Logger
    if not Logger:
        from ._logger import Logger

    return isinstance(obj, Logger)


def _is_derived_logger(cls: type):
    global Logger
    if not Logger:
        from ._logger import Logger

    return cls is not Logger and issubclass(cls, Logger)


class PlaceHolder:
    """
    PlaceHolder instances are used in the Manager logger hierarchy to take
    the place of nodes for which no loggers have been defined. This class is
    intended for internal use only and not as part of the public API.
    """
    def __init__(self, alogger):
        """
        Initialize with the specified logger being a child of this placeholder.
        """
        self.loggerMap = {alogger: None}

    def append(self, alogger):
        """
        Add the specified logger as a child of this placeholder.
        """
        if alogger not in self.loggerMap:
            self.loggerMap[alogger] = None


#   Determine which class to use when instantiating loggers.


def setLoggerClass(cls):
    """
    Set the class to be used when instantiating a logger. The class should
    define __init__() such that only a name argument is required, and the
    __init__() should call Logger.__init__()
    """
    if _is_derived_logger(cls):
        raise TypeError(f"logger not derived from logging.Logger: {cls.__name__}")
    global _loggerClass
    _loggerClass = cls


def getLoggerClass():
    """
    Return the class to be used when instantiating a logger.
    """
    return _loggerClass


class Manager:
    """
    There is [under normal circumstances] just one Manager instance, which
    holds the hierarchy of loggers.
    """
    def __init__(self, rootnode):
        """
        Initialize the manager with the root node of the logger hierarchy.
        """
        self.root = rootnode
        self.disable = 0
        self.emittedNoHandlerWarning = False
        self.loggerDict = {}
        self.loggerClass = None
        self.logRecordFactory = None

    @property
    def disable(self):
        return self._disable

    @disable.setter
    def disable(self, value):
        self._disable = _checkLevel(value)

    def getLogger(self, name):
        """
        Get a logger with the specified name (channel name), creating it
        if it doesn't yet exist. This name is a dot-separated hierarchical
        name, such as "a", "a.b", "a.b.c" or similar.

        If a PlaceHolder existed for the specified name [i.e. the logger
        didn't exist but a child of it did], replace it with the created
        logger and fix up the parent/child references which pointed to the
        placeholder to now point to the logger.
        """
        rv = None
        if not isinstance(name, str):
            raise TypeError('A logger name must be a string')
        with _lock:
            if name in self.loggerDict:
                rv = self.loggerDict[name]
                if isinstance(rv, PlaceHolder):
                    ph = rv
                    rv = (self.loggerClass or _loggerClass)(name)
                    rv.manager = self
                    self.loggerDict[name] = rv
                    self._fixupChildren(ph, rv)
                    self._fixupParents(rv)
            else:
                rv = (self.loggerClass or _loggerClass)(name)
                rv.manager = self
                self.loggerDict[name] = rv
                self._fixupParents(rv)
        return rv

    def setLoggerClass(self, cls):
        """
        Set the class to be used when instantiating a logger with this Manager.
        """
        if _is_derived_logger(cls):
            raise TypeError(f"logger not derived from logging.Logger: {cls.__name__}")
        self.loggerClass = cls

    def setLogRecordFactory(self, factory):
        """
        Set the factory to be used when instantiating a log record with this
        Manager.
        """
        self.logRecordFactory = factory

    def _fixupParents(self, alogger):
        """
        Ensure that there are either loggers or placeholders all the way
        from the specified logger to the root of the logger hierarchy.
        """
        name = alogger.name
        i = name.rfind(".")
        rv = None
        while (i > 0) and not rv:
            substr = name[:i]
            if substr not in self.loggerDict:
                self.loggerDict[substr] = PlaceHolder(alogger)
            else:
                obj = self.loggerDict[substr]
                if _is_logger(obj):
                    rv = obj
                else:
                    assert isinstance(obj, PlaceHolder)
                    obj.append(alogger)
            i = name.rfind(".", 0, i - 1)
        if not rv:
            rv = self.root
        alogger.parent = rv

    def _fixupChildren(self, ph, alogger):
        """
        Ensure that children of the placeholder ph are connected to the
        specified logger.
        """
        name = alogger.name
        for c in ph.loggerMap:
            if not c.parent.name.startswith(name):
                alogger.parent = c.parent
                c.parent = alogger

    def _clear_cache(self):
        """
        Clear the cache for all loggers in loggerDict
        Called when level changes are made
        """

        with _lock:
            for logger in self.loggerDict.values():
                if _is_logger(logger):
                    logger._cache.clear()
            self.root._cache.clear()
