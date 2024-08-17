import logging

import pytest
from molog import _record


def test_compatible_status():
    class OldLogRecord(logging.LogRecord):
        pass

    log_record = OldLogRecord("", 10, "", 10, "", (), None)
    assert log_record.processName == "MainProcess"
    assert log_record.msg == ""
    _record.LogRecord.logMultiprocessing = False
    CompatibleLogRecord = _record.LogRecord.buildCompatible(OldLogRecord)
    log_record = CompatibleLogRecord("", 10, "", 10, "", (), None)
    assert log_record.processName is None
    assert log_record.msg == ""
    assert log_record.logThreads
