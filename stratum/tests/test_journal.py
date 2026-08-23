from pathlib import Path

from stratum.events import TASK_CREATED, EventFactory, RuntimeEvent
from stratum.journal import FileEventJournal, JournalPublisher
from stratum.ids import execution_id, task_id


def _make_event(seq: int) -> RuntimeEvent:
    f = EventFactory(task_id(), execution_id())
    for _ in range(seq - 1):
        f.emit(TASK_CREATED, {})
    return f.emit(TASK_CREATED, {"n": seq})


def test_journal_roundtrip(tmp_path: Path):
    journal = FileEventJournal(tmp_path / "events.ndjson")
    e1, e2 = _make_event(1), _make_event(2)
    publisher = JournalPublisher(journal)

    import asyncio

    asyncio.run(publisher.publish(e1))
    asyncio.run(publisher.publish(e2))

    events = journal.read_all()
    assert [e.event_id for e in events] == [e1.event_id, e2.event_id]
    assert events[1].payload["n"] == 2


def test_journal_torn_final_line_is_ignored(tmp_path: Path):
    path = tmp_path / "events.ndjson"
    good = _make_event(1)
    path.write_text(good.to_json().decode() + "\n" + '{"event_id": "torn', encoding="utf-8")
    journal = FileEventJournal(path)
    events = journal.read_all()
    assert len(events) == 1
    assert events[0].event_id == good.event_id


def test_journal_read_execution_filters(tmp_path: Path):
    journal = FileEventJournal(tmp_path / "events.ndjson")
    import asyncio

    pub = JournalPublisher(journal)
    keep = _make_event(1)
    other = _make_event(1)  # different random execution id
    asyncio.run(pub.publish(keep))
    asyncio.run(pub.publish(other))
    assert [e.execution_id for e in journal.read_execution(keep.execution_id)] == [
        keep.execution_id
    ]
