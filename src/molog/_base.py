import os
import sys
import threading
import time
import weakref

_startTime = time.time_ns()
"""_startTime is used as the base when calculating the relative time of events"""

raiseExceptions = True
"""raiseExceptions is used to see if exceptions during handling should be propagated"""

logThreads = True
"""If you don't want threading information in the log, set this to False"""

logMultiprocessing = True
"""If you don't want multiprocessing information in the log, set this to False"""

logProcesses = True
"""If you don't want process information in the log, set this to False"""

logAsyncioTasks = True
"""If you don't want asyncio task information in the log, set this to False"""


if hasattr(sys, "_getframe"):
    def currentframe():  # type: ignore
        return sys._getframe(1)
else:  # pragma: no cover
    def currentframe():
        """Return the frame object for the caller's stack frame."""
        try:
            raise Exception
        except Exception as exc:
            return exc.__traceback__.tb_frame.f_back  # type: ignore

_lock = threading.RLock()
"""_lock is used to serialize access to shared data structures in this module."""


def _prepareFork():
    """
    Prepare to fork a new child process by acquiring the module-level lock.

    This should be used in conjunction with _afterFork().
    """
    # Wrap the lock acquisition in a try-except to prevent the lock from being
    # abandoned in the event of an asynchronous exception. See gh-106238.
    try:
        _lock.acquire()
    except BaseException:
        _lock.release()
        raise


def _afterFork():
    """
    After a new child process has been forked, release the module-level lock.

    This should be used in conjunction with _prepareFork().
    """
    _lock.release()


# Prevent a held logging lock from blocking a child from logging.

if not hasattr(os, 'register_at_fork'):  # Windows and friends.
    def _register_at_fork_reinit_lock(instance):
        pass  # no-op when os.register_at_fork does not exist.
else:
    # A collection of instances with a _at_fork_reinit method (logging.Handler)
    # to be called in the child after forking.  The weakref avoids us keeping
    # discarded Handler instances alive.
    _at_fork_reinit_lock_weakset = weakref.WeakSet()

    def _register_at_fork_reinit_lock(instance):
        with _lock:
            _at_fork_reinit_lock_weakset.add(instance)

    def _after_at_fork_child_reinit_locks():
        for handler in _at_fork_reinit_lock_weakset:
            handler._at_fork_reinit()

        # _prepareFork() was called in the parent before forking.
        # The lock is reinitialized to unlocked state.
        _lock._at_fork_reinit()  # type: ignore

    os.register_at_fork(before=_prepareFork,
                        after_in_child=_after_at_fork_child_reinit_locks,
                        after_in_parent=_afterFork)
