"""Minimal JSONL tracing without recording hidden model reasoning."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable


class TraceLogger:
    def __init__(
        self,
        path: Path | None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.path = path
        self.event_sink = event_sink

    def write(self, event: str, **data: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if self.event_sink is not None:
            self.event_sink(record)
