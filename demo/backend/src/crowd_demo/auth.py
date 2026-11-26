"""Đăng nhập cơ bản: tài khoản lấy từ biến môi trường, phiên đăng nhập là cookie ký HMAC.

- CROWD_ADMIN_USER / CROWD_ADMIN_PASSWORD: quản trị (mọi quyền). Thiếu thì dùng admin/admin. Tài khoản được seed vào SQLite (bảng users) khi khởi động.
- CROWD_VIEWER_USER / CROWD_VIEWER_PASSWORD: chỉ xem (không bắt buộc). Được xác nhận cảnh báo, không sửa cấu hình.
- CROWD_SECRET: khóa ký phiên. Thiếu thì sinh ngẫu nhiên mỗi lần chạy (khởi động lại phải đăng nhập lại).
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass

COOKIE = "crowd_session"
SESSION_TTL_S = 12 * 3600


@dataclass(frozen=True)
class User:
    name: str
    role: str            # "admin" | "viewer"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


class Auth:
    _db = None

    def __init__(self, env: Mapping[str, str], ttl_s: float = SESSION_TTL_S):
        admin_user, admin_pw = env.get("CROWD_ADMIN_USER"), env.get("CROWD_ADMIN_PASSWORD")
        self.using_default = not (admin_user and admin_pw)
        self._users: dict[str, tuple[str, str]] = {}
        self._users[admin_user or "admin"] = (admin_pw or "admin", "admin")
        if env.get("CROWD_VIEWER_USER") and env.get("CROWD_VIEWER_PASSWORD"):
            self._users.setdefault(env["CROWD_VIEWER_USER"], (env["CROWD_VIEWER_PASSWORD"], "viewer"))
        self._secret = (env.get("CROWD_SECRET") or secrets.token_hex(32)).encode()
        self.ttl_s = ttl_s

    def attach(self, db) -> None:
        """Dùng bảng users trong SQLite làm nguồn tài khoản; seed tài khoản từ .env (hoặc admin/admin) nếu chưa có."""
        self._db = db
        for name, (pw, role) in self._users.items():
            salt = secrets.token_hex(8)
            db.add_user_if_missing(name, salt, _hash(pw, salt), role)

    def check(self, username: str, password: str) -> User | None:
        # So sánh thời gian hằng cả khi tên sai, để không lộ tên đăng nhập nào tồn tại
        if self._db is not None:
            row = self._db.get_user(username)
            salt, expected, role = (row["salt"], row["hash"], row["role"]) if row else ("", secrets.token_hex(32), "")
            ok = hmac.compare_digest(_hash(password, salt), expected)
            return User(username, role) if row and ok else None
        entry = self._users.get(username)
        expected = entry[0] if entry else secrets.token_hex(16)
        ok = hmac.compare_digest(password.encode(), expected.encode())
        return User(username, entry[1]) if entry and ok else None

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())

    def issue(self, user: User, now: float | None = None) -> str:
        now = time.time() if now is None else now
        body = _b64(json.dumps({"u": user.name, "r": user.role, "exp": now + self.ttl_s}).encode())
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str | None, now: float | None = None) -> User | None:
        if not token or token.count(".") != 1:
            return None
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, self._sign(body)):
            return None
        try:
            data = json.loads(_unb64(body))
        except ValueError:
            return None
        if (time.time() if now is None else now) > data.get("exp", 0):
            return None
        user = User(data["u"], data["r"])
        # tài khoản đã bị bỏ khỏi biến môi trường thì phiên cũ hết hiệu lực
        return user if self._users.get(user.name, (None, None))[1] == user.role else None
