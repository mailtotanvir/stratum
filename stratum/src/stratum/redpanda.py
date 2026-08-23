"""Redpanda / Kafka event transport.

The authoritative runtime event stream lives here. All broker interaction is
confined to this module; the rest of the runtime only knows the
EventPublisher protocol.

Partitioning: events are keyed by execution_id so the full history of one
execution is totally ordered within a single partition.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterator

from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import (
    KafkaError,
    NoBrokersAvailable,
    TopicAlreadyExistsError,
)

from .errors import StratumError
from .events import DEFAULT_TOPIC, RuntimeEvent

logger = logging.getLogger(__name__)

CONSUME_IDLE_TIMEOUT_MS = 4_000


class BrokerUnavailable(StratumError):
    pass


def _encode_value(event: RuntimeEvent) -> bytes:
    return event.to_json()


def _decode_value(raw: bytes | None) -> RuntimeEvent:
    return RuntimeEvent.from_json(raw or b"{}")


class RedpandaEventPublisher:
    """Publishes RuntimeEvents to a Kafka-compatible broker (Redpanda)."""

    def __init__(
        self,
        *,
        brokers: list[str],
        topic: str = DEFAULT_TOPIC,
        ensure_topic: bool = True,
    ) -> None:
        self.brokers = list(brokers)
        self.topic = topic
        self._producer = KafkaProducer(
            bootstrap_servers=self.brokers,
            acks="all",
            linger_ms=5,
            value_serializer=_encode_value,
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        if ensure_topic:
            self._ensure_topic()

    def _ensure_topic(self) -> None:
        try:
            admin = KafkaAdminClient(bootstrap_servers=self.brokers)
            try:
                admin.create_topics(
                    [NewTopic(name=self.topic, num_partitions=1, replication_factor=1)]
                )
            except TopicAlreadyExistsError:
                pass
            finally:
                admin.close()
        except (NoBrokersAvailable, KafkaError) as exc:
            # Auto-create may be enabled on the broker; publish errors will
            # surface loudly if the topic genuinely cannot be written.
            logger.debug("topic pre-create skipped: %s", exc)

    async def publish(self, event: RuntimeEvent) -> None:
        await asyncio.to_thread(self._send_sync, event)

    def _send_sync(self, event: RuntimeEvent) -> None:
        try:
            future = self._producer.send(
                self.topic, value=event, key=event.execution_id
            )
            future.get(timeout=15)
        except KafkaError as exc:
            raise BrokerUnavailable(f"failed to publish event {event.event_id}: {exc}") from exc

    async def close(self) -> None:
        await asyncio.to_thread(self._producer.flush)
        await asyncio.to_thread(self._producer.close)


class RedpandaEventReader:
    """Reads events back off the broker for replay and live tracing."""

    def __init__(
        self,
        *,
        brokers: list[str],
        topic: str = DEFAULT_TOPIC,
        group_id: str | None = None,
    ) -> None:
        self.brokers = list(brokers)
        self.topic = topic
        self._group_id = group_id

    def _consumer(self, *, follow: bool) -> KafkaConsumer:
        try:
            return KafkaConsumer(
                self.topic,
                bootstrap_servers=self.brokers,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                group_id=self._group_id,
                consumer_timeout_ms=None if follow else CONSUME_IDLE_TIMEOUT_MS,
                value_deserializer=_decode_value,
            )
        except NoBrokersAvailable as exc:
            raise BrokerUnavailable(
                f"no reachable broker at {self.brokers}"
            ) from exc

    def iter_events(
        self,
        *,
        execution_id: str | None = None,
        follow: bool = False,
    ) -> Iterator[RuntimeEvent]:
        """Yield events from the beginning of the retained topic.

        Without ``follow``, iteration stops after the idle timeout elapses
        with no further messages (i.e. we reached the end of the log).
        """
        consumer = self._consumer(follow=follow)
        try:
            for message in consumer:
                event: RuntimeEvent = message.value
                if execution_id is not None and event.execution_id != execution_id:
                    continue
                yield event
        finally:
            consumer.close()

    def read_execution(self, execution_id: str) -> list[RuntimeEvent]:
        return list(self.iter_events(execution_id=execution_id, follow=False))
