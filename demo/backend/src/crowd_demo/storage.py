"""Cơ sở dữ liệu SQLite: chuỗi số liệu theo thời gian và các sự kiện cảnh báo."""
import sqlite3
import threading
from pathlib import Path

from .domain import Alert, DensityStats, MotionStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    t REAL NOT NULL, source TEXT NOT NULL,
    total REAL, roi REAL, excluded REAL, max_cell REAL,
    speed REAL, entropy REAL, counterflow REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_t ON samples(t);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    t REAL NOT NULL, source TEXT NOT NULL, rule TEXT NOT NULL,
    value REAL, threshold REAL, message TEXT,
    snapshot TEXT, clip TEXT
);
"""


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def add_sample(self, t: float, source: str, d: DensityStats, m: MotionStats) -> None:
        with self._lock:
            self._db.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?)",
                             (t, source, d.total, d.roi, d.excluded, d.max_cell, m.speed, m.entropy, m.counterflow))
            self._db.commit()

    def add_event(self, alert: Alert, source: str, snapshot: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (t, source, rule, value, threshold, message, snapshot) VALUES (?,?,?,?,?,?,?)",
                (alert.t, source, alert.rule, alert.value, alert.threshold, alert.message, snapshot))
            self._db.commit()
            return int(cur.lastrowid)

    def set_clip(self, event_id: int, clip: str) -> None:
        with self._lock:
            self._db.execute("UPDATE events SET clip = ? WHERE id = ?", (clip, event_id))
            self._db.commit()

    def series(self, since_t: float) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM samples WHERE t >= ? ORDER BY t", (since_t,)).fetchall()
        return [dict(r) for r in rows]

    def events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
