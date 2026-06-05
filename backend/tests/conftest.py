import pytest

from app.services.event_service import event_service
from app.services.interrupt_service import interrupt_service
from app.services.reflection_service import reflection_service
from app.services.runtime_execution_service import runtime_execution_service
from app.services.stop_service import stop_service
from app.services.trace_service import TraceService


@pytest.fixture(autouse=True)
def use_temp_trace_store(tmp_path):
    event_service.set_trace_store(TraceService(tmp_path / "stratum.db"))
    interrupt_service.set_db_path(tmp_path / "interrupts.db")
    reflection_service.set_db_path(tmp_path / "reflections.db")
    runtime_execution_service.set_db_path(tmp_path / "runtime.db")
    stop_service.set_db_path(tmp_path / "stops.db")
