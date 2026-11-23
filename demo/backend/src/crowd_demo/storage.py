"""Cơ sở dữ liệu SQLite chung cho mọi camera.

Bảng:
- `cameras`: danh sách camera và cấu hình (mô hình, vùng, luật) dạng JSON.
- `samples`: số liệu thô mỗi lần phân tích; tự dọn sau vài ngày.
- `minutes`: số liệu gom theo phút ngay khi ghi, dùng cho thống kê dài hạn.
- `events`: cảnh báo kèm ảnh, clip, trạng thái xử lý.
- `audit`: nhật ký thao tác của người dùng.

`Store` là "góc nhìn" của một camera, giữ nguyên giao diện mà pipeline và bộ ghi bằng chứng đang dùng.
"""
import json
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .anomaly import Reading
from .domain import Alert, DensityStats, MotionStats

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, tz TEXT NOT NULL,
    autostart INTEGER NOT NULL DEFAULT 0, config TEXT NOT NULL DEFAULT '{}',
    created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS samples (
    camera_id INTEGER NOT NULL, t REAL NOT NULL,
    total REAL, roi REAL, excluded REAL, max_cell REAL,
    speed REAL, entropy REAL, counterflow REAL, anomaly REAL, anomaly_limit REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_cam_t ON samples(camera_id, t);
CREATE TABLE IF NOT EXISTS minutes (
    camera_id INTEGER NOT NULL, minute INTEGER NOT NULL,
    n INTEGER NOT NULL, roi_sum REAL NOT NULL, roi_max REAL NOT NULL, total_sum REAL NOT NULL,
    anomaly_max REAL,
    PRIMARY KEY (camera_id, minute)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL, t REAL NOT NULL, source TEXT NOT NULL, rule TEXT NOT NULL,
    value REAL, threshold REAL, message TEXT, snapshot TEXT, clip TEXT,
    status TEXT NOT NULL DEFAULT 'new', ack_by TEXT, ack_at REAL, note TEXT,
    purged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_t ON events(t);
CREATE INDEX IF NOT EXISTS idx_events_cam_t ON events(camera_id, t);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL NOT NULL, user TEXT NOT NULL, action TEXT NOT NULL, detail TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _q(self, sql: str, args=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _x(self, sql: str, args=()) -> int:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return int(cur.lastrowid or cur.rowcount)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def store(self, camera_id: int) -> "Store":
        return Store(self, camera_id)

    # ---------------------------------------------------------------- camera
    @staticmethod
    def _camera(row: dict) -> dict:
        return {**row, "autostart": bool(row["autostart"]), "config": json.loads(row["config"] or "{}")}

    def list_cameras(self) -> list[dict]:
        return [self._camera(r) for r in self._q("SELECT * FROM cameras ORDER BY id")]

    def get_camera(self, camera_id: int) -> dict | None:
        rows = self._q("SELECT * FROM cameras WHERE id = ?", (camera_id,))
        return self._camera(rows[0]) if rows else None

    def create_camera(self, name: str, kind: str, source: str, tz: str, autostart: bool = False,
                      config: dict | None = None) -> int:
        now = time.time()
        return self._x("INSERT INTO cameras (name, kind, source, tz, autostart, config, created, updated) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (name, kind, source, tz, int(autostart), json.dumps(config or {}, ensure_ascii=False), now, now))

    def update_camera(self, camera_id: int, **fields) -> None:
        allowed = {"name", "kind", "source", "tz", "autostart", "config"}
        sets, args = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise KeyError(k)
            sets.append(f"{k} = ?")
            args.append(json.dumps(v, ensure_ascii=False) if k == "config" else int(v) if k == "autostart" else v)
        sets.append("updated = ?")
        args += [time.time(), camera_id]
        self._x(f"UPDATE cameras SET {', '.join(sets)} WHERE id = ?", args)

    def delete_camera(self, camera_id: int) -> None:
        """Xóa camera khỏi danh sách. Lịch sử cảnh báo và thống kê vẫn giữ (sự kiện còn tên nguồn)."""
        self._x("DELETE FROM cameras WHERE id = ?", (camera_id,))

    # ---------------------------------------------------------------- số liệu
    def add_sample(self, camera_id: int, t: float, d: DensityStats, m: MotionStats, a: Reading | None) -> None:
        score = None if a is None else a.score
        with self._lock:
            self._db.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (camera_id, t, d.total, d.roi, d.excluded, d.max_cell, m.speed, m.entropy,
                              m.counterflow, score, None if a is None else a.limit))
            self._db.execute(
                "INSERT INTO minutes VALUES (?,?,1,?,?,?,?) ON CONFLICT(camera_id, minute) DO UPDATE SET "
                "n = n + 1, roi_sum = roi_sum + excluded.roi_sum, roi_max = max(roi_max, excluded.roi_max), "
                "total_sum = total_sum + excluded.total_sum, "
                "anomaly_max = CASE WHEN excluded.anomaly_max IS NULL THEN anomaly_max "
                "                   WHEN anomaly_max IS NULL THEN excluded.anomaly_max "
                "                   ELSE max(anomaly_max, excluded.anomaly_max) END",
                (camera_id, int(t // 60), d.roi, d.roi, d.total, score))
            self._db.commit()

    def series(self, camera_id: int, since_t: float, until_t: float | None = None) -> list[dict]:
        until_t = float("inf") if until_t is None else until_t
        return self._q("SELECT t, total, roi, excluded, max_cell, speed, entropy, counterflow, anomaly, anomaly_limit "
                       "FROM samples WHERE camera_id = ? AND t >= ? AND t <= ? ORDER BY t", (camera_id, since_t, until_t))

    def stats_series(self, camera_id: int, t0: float, t1: float, bucket_s: int) -> list[dict]:
        """Số người trung bình / cao nhất và điểm bất thường cao nhất theo từng khoảng `bucket_s` giây."""
        b = max(60, int(bucket_s)) // 60
        rows = self._q(
            "SELECT (minute / ?) * ? * 60 AS t, sum(roi_sum) / sum(n) AS roi_avg, max(roi_max) AS roi_max, "
            "max(anomaly_max) AS anomaly_max, sum(n) AS n FROM minutes "
            "WHERE camera_id = ? AND minute >= ? AND minute <= ? GROUP BY minute / ? ORDER BY t",
            (b, b, camera_id, int(t0 // 60), int(t1 // 60), b))
        return [{**r, "t": float(r["t"])} for r in rows]

    def summary(self, camera_id: int | None, t0: float, t1: float) -> dict:
        cam_sql, cam_arg = ("AND camera_id = ?", (camera_id,)) if camera_id is not None else ("", ())
        agg = self._q(f"SELECT sum(roi_sum) AS s, sum(n) AS n FROM minutes WHERE minute >= ? AND minute <= ? {cam_sql}",
                      (int(t0 // 60), int(t1 // 60), *cam_arg))[0]
        peak = self._q(f"SELECT roi, t FROM samples WHERE t >= ? AND t <= ? {cam_sql} ORDER BY roi DESC LIMIT 1",
                       (t0, t1, *cam_arg))
        if not peak:   # số liệu thô đã dọn: lấy đỉnh theo phút
            peak = [{"roi": r["roi_max"], "t": r["minute"] * 60.0} for r in self._q(
                f"SELECT roi_max, minute FROM minutes WHERE minute >= ? AND minute <= ? {cam_sql} "
                "ORDER BY roi_max DESC LIMIT 1", (int(t0 // 60), int(t1 // 60), *cam_arg))]
        ev = self._q(f"SELECT rule, count(*) AS n, sum(status = 'ack') AS acked FROM events "
                     f"WHERE t >= ? AND t <= ? {cam_sql} GROUP BY rule", (t0, t1, *cam_arg))
        return {"roi_avg": agg["s"] / agg["n"] if agg["n"] else None,
                "roi_max": peak[0]["roi"] if peak else None, "roi_max_t": peak[0]["t"] if peak else None,
                "events": {r["rule"]: r["n"] for r in ev}, "acked": sum(r["acked"] or 0 for r in ev)}

    def heatmap(self, camera_id: int | None, t0: float, t1: float, tz: str) -> list[dict]:
        """Số người trung bình theo (thứ trong tuần, giờ) theo giờ địa phương của camera. Thứ Hai = 0."""
        cam_sql, cam_arg = ("AND camera_id = ?", (camera_id,)) if camera_id is not None else ("", ())
        z = ZoneInfo(tz)
        acc: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0])
        for r in self._q(f"SELECT minute, roi_sum, n FROM minutes WHERE minute >= ? AND minute <= ? {cam_sql}",
                         (int(t0 // 60), int(t1 // 60), *cam_arg)):
            local = datetime.fromtimestamp(r["minute"] * 60, z)
            cell = acc[(local.weekday(), local.hour)]
            cell[0] += r["roi_sum"]
            cell[1] += r["n"]
        return [{"weekday": w, "hour": h, "roi_avg": s / n} for (w, h), (s, n) in sorted(acc.items())]

    # ---------------------------------------------------------------- cảnh báo
    def add_event(self, camera_id: int, alert: Alert, source: str, snapshot: str) -> int:
        return self._x("INSERT INTO events (camera_id, t, source, rule, value, threshold, message, snapshot) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (camera_id, alert.t, source, alert.rule, alert.value, alert.threshold, alert.message, snapshot))

    def set_clip(self, event_id: int, clip: str) -> None:
        self._x("UPDATE events SET clip = ? WHERE id = ?", (clip, event_id))

    def get_event(self, event_id: int) -> dict | None:
        rows = self._q("SELECT * FROM events WHERE id = ?", (event_id,))
        return rows[0] if rows else None

    def query_events(self, camera_id: int | None = None, rule: str | None = None, status: str | None = None,
                     t0: float | None = None, t1: float | None = None, limit: int = 50,
                     offset: int = 0) -> tuple[list[dict], int]:
        where, args = [], []
        for col, op, v in (("camera_id", "=", camera_id), ("rule", "=", rule), ("status", "=", status),
                           ("t", ">=", t0), ("t", "<=", t1)):
            if v is not None:
                where.append(f"{col} {op} ?")
                args.append(v)
        w = f"WHERE {' AND '.join(where)}" if where else ""
        total = self._q(f"SELECT count(*) AS n FROM events {w}", args)[0]["n"]
        rows = self._q(f"SELECT * FROM events {w} ORDER BY t DESC, id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
        return rows, total

    def ack_event(self, event_id: int, user: str, note: str) -> bool:
        return self._x("UPDATE events SET status = 'ack', ack_by = ?, ack_at = ?, note = ? WHERE id = ?",
                       (user, time.time(), note, event_id)) > 0

    def unacked_count(self) -> int:
        return self._q("SELECT count(*) AS n FROM events WHERE status = 'new'")[0]["n"]

    def events_by_day(self, camera_id: int | None, t0: float, t1: float, tz: str) -> list[dict]:
        cam_sql, cam_arg = ("AND camera_id = ?", (camera_id,)) if camera_id is not None else ("", ())
        z = ZoneInfo(tz)
        acc: dict[tuple[str, str], int] = defaultdict(int)
        for r in self._q(f"SELECT t, rule FROM events WHERE t >= ? AND t <= ? {cam_sql}", (t0, t1, *cam_arg)):
            acc[(datetime.fromtimestamp(r["t"], z).strftime("%Y-%m-%d"), r["rule"])] += 1
        return [{"day": d, "rule": rule, "n": n} for (d, rule), n in sorted(acc.items())]

    # ---------------------------------------------------------------- nhật ký
    def audit(self, user: str, action: str, detail: str = "") -> None:
        self._x("INSERT INTO audit (t, user, action, detail) VALUES (?,?,?,?)", (time.time(), user, action, detail))

    def list_audit(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._q("SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))

    # ---------------------------------------------------------------- dọn dữ liệu
    def purge(self, now: float, raw_days: float, clip_days: float, evidence_root: Path) -> dict:
        """Xóa số liệu thô quá `raw_days` ngày; xóa file ảnh và clip của cảnh báo quá `clip_days` ngày
        (bản ghi cảnh báo vẫn giữ, đánh dấu `purged`). Thống kê theo phút không bị xóa."""
        n_samples = self._x("DELETE FROM samples WHERE t < ?", (now - raw_days * 86400,))
        old = self._q("SELECT id, snapshot, clip FROM events WHERE t < ? AND purged = 0", (now - clip_days * 86400,))
        for e in old:
            for url in (e["snapshot"], e["clip"]):
                path = _evidence_path(url, evidence_root)
                if path is not None and path.exists():
                    path.unlink()
            self._x("UPDATE events SET purged = 1 WHERE id = ?", (e["id"],))
        return {"samples": n_samples, "clips": len(old)}


def _evidence_path(url: str | None, root: Path) -> Path | None:
    """'/evidence/3/x.mp4' → <root>/3/x.mp4, chặn đường dẫn thoát ra ngoài thư mục bằng chứng."""
    if not url or not url.startswith("/evidence/"):
        return None
    path = (root / url.removeprefix("/evidence/")).resolve()
    return path if path.is_relative_to(root.resolve()) else None


class Store:
    """Số liệu và cảnh báo của một camera (giao diện cũ của pipeline và bộ ghi bằng chứng)."""

    def __init__(self, db: Database, camera_id: int):
        self.db, self.camera_id = db, camera_id

    def add_sample(self, t: float, source: str, d: DensityStats, m: MotionStats, a: Reading | None = None) -> None:
        self.db.add_sample(self.camera_id, t, d, m, a)

    def add_event(self, alert: Alert, source: str, snapshot: str) -> int:
        return self.db.add_event(self.camera_id, alert, source, snapshot)

    def set_clip(self, event_id: int, clip: str) -> None:
        self.db.set_clip(event_id, clip)

    def series(self, since_t: float) -> list[dict]:
        return self.db.series(self.camera_id, since_t)

    def events(self, limit: int = 50) -> list[dict]:
        return self.db.query_events(camera_id=self.camera_id, limit=limit)[0]

    def close(self) -> None:
        """Cơ sở dữ liệu dùng chung; đóng ở cấp ứng dụng."""
