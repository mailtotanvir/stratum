from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RuntimeEventRecord(Base):
    __tablename__ = "runtime_events"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, index=True)
    severity: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)


class RuntimeExecutionRecord(Base):
    __tablename__ = "runtime_executions"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ReflectionRequestRecord(Base):
    __tablename__ = "reflection_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    reasons_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterruptRequestRecord(Base):
    __tablename__ = "interrupt_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StopRequestRecord(Base):
    __tablename__ = "stop_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalRecord(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(Text)
