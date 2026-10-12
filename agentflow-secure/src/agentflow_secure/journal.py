"""Minimal run journal: one JSONL file, one record per event.

The hash chain (for log integrity) is left for a later defence stage.
"""
import json
from datetime import datetime, timezone


class Journal:
    def __init__(self, path):
        self.path = path
        self._file = open(path, "x", encoding="utf-8")  # never overwrite a previous run's journal

    def write(self, event, **fields):
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self):
        self._file.close()
