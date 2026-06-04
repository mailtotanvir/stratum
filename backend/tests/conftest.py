import pytest

from app.services.event_service import event_service
from app.services.trace_service import TraceService


@pytest.fixture(autouse=True)
def use_temp_trace_store(tmp_path):
    event_service.set_trace_store(TraceService(tmp_path / "stratum.db"))

