"""Append-only, hash-chained call log.

Every entry carries the hash of the entry before it, so editing, deleting or
reordering any earlier line breaks the chain and verify() reports it.

Honest limit: this is tamper-EVIDENT, not tamper-PROOF. A plain file can be
edited by anyone with access to the machine; the chain makes that visible, it
does not prevent it. (The brief's database-enforced write-once log is later
work.)

If an entry cannot be written, append() raises. The server treats that as
"refuse the call" -- nothing runs without being logged.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

GENESIS = "0" * 64


def _entry_hash(entry_without_hash):
    canonical = json.dumps(entry_without_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CallLog:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def _last(self):
        """Return (seq, hash) of the last entry, or (0, GENESIS)."""
        if not os.path.exists(self.path):
            return 0, GENESIS
        last_line = None
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if last_line is None:
            return 0, GENESIS
        entry = json.loads(last_line)
        return entry["seq"], entry["hash"]

    def append(self, event, **fields):
        with self._lock:
            seq, prev_hash = self._last()
            entry = {
                "seq": seq + 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "prev_hash": prev_hash,
            }
            entry.update(fields)
            entry["hash"] = _entry_hash(entry)
            # "a" = append only. The log is never opened for rewrite.
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return entry

    def entries(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def verify(path):
    """Check the whole chain. Returns (ok, problem_or_None)."""
    prev = GENESIS
    expected_seq = 1
    if not os.path.exists(path):
        return True, None
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                return False, f"line {lineno}: not valid JSON"
            stored = entry.pop("hash", None)
            if entry.get("seq") != expected_seq:
                return False, f"line {lineno}: sequence break (expected {expected_seq})"
            if entry.get("prev_hash") != prev:
                return False, f"line {lineno}: chain break (prev_hash mismatch)"
            if _entry_hash(entry) != stored:
                return False, f"line {lineno}: entry was altered (hash mismatch)"
            prev = stored
            expected_seq += 1
    return True, None
