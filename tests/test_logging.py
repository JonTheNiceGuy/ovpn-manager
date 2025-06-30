import logging
from server import HealthCheckFilter

def test_health_check_filter():
    """
    Unit tests the HealthCheckFilter directly.
    """
    log_filter = HealthCheckFilter()

    # 1. Create a fake log record for a health check and assert it's filtered out
    healthz_record = logging.LogRecord(
        name='werkzeug',
        level=logging.INFO,
        pathname='dummy_pathname',
        lineno=10,
        msg='"GET /healthz HTTP/1.1" 200 -',
        args=(),
        exc_info=None
    )
    assert not log_filter.filter(healthz_record) # filter() should return False

    # 2. Create a fake log record for a normal page and assert it's allowed
    index_record = logging.LogRecord(
        name='werkzeug',
        level=logging.INFO,
        pathname='dummy_pathname',
        lineno=10,
        msg='"GET / HTTP/1.1" 200 -',
        args=(),
        exc_info=None
    )
    assert log_filter.filter(index_record) # filter() should return True