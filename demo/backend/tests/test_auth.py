from crowd_demo.auth import Auth

ENV = {"CROWD_ADMIN_USER": "quantri", "CROWD_ADMIN_PASSWORD": "mk-dai-123",
       "CROWD_VIEWER_USER": "vanhanh", "CROWD_VIEWER_PASSWORD": "xem-456", "CROWD_SECRET": "s3cret"}


def test_check_credentials_and_roles():
    a = Auth(ENV)
    assert a.check("quantri", "mk-dai-123").role == "admin"
    assert a.check("vanhanh", "xem-456").role == "viewer"
    assert a.check("quantri", "sai") is None and a.check("ai_do", "mk-dai-123") is None


def test_token_roundtrip_expiry_and_tamper():
    a = Auth(ENV, ttl_s=60)
    tok = a.issue(a.check("quantri", "mk-dai-123"), now=1000.0)
    assert a.verify(tok, now=1030.0).name == "quantri"
    assert a.verify(tok, now=1061.0) is None                       # hết hạn
    body, sig = tok.split(".")
    assert a.verify(body + "." + sig[:-2] + "AA", now=1030.0) is None   # sửa chữ ký
    assert Auth({**ENV, "CROWD_SECRET": "khac"}).verify(tok, now=1030.0) is None
    assert a.verify("rac", now=1030.0) is None and a.verify(None) is None


def test_defaults_when_env_missing():
    a = Auth({})
    assert a.check("admin", "admin").role == "admin"
    assert a.check("viewer", "") is None                             # không khai báo thì không có tài khoản chỉ xem


def test_seeded_into_db_and_hashed(tmp_path):
    from crowd_demo.storage import Database
    db = Database(tmp_path / "t.db")
    a = Auth({})
    a.attach(db)
    row = db.get_user("admin")
    assert row["role"] == "admin" and "admin" not in (row["hash"], row["salt"])
    assert a.check("admin", "admin").role == "admin" and a.check("admin", "sai") is None
    assert a.check("ai_do", "x") is None
    Auth({"CROWD_ADMIN_USER": "admin", "CROWD_ADMIN_PASSWORD": "khac"}).attach(db)   # khởi động lại không ghi đè
    assert a.check("admin", "admin") is not None
