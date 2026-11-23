from crowd_demo.auth import Auth

ENV = {"CROWD_ADMIN_USER": "quantri", "CROWD_ADMIN_PASSWORD": "mk-dai-123",
       "CROWD_VIEWER_USER": "vanhanh", "CROWD_VIEWER_PASSWORD": "xem-456", "CROWD_SECRET": "s3cret"}


def test_check_credentials_and_roles():
    a = Auth(ENV)
    assert a.check("quantri", "mk-dai-123").role == "admin"
    assert a.check("vanhanh", "xem-456").role == "viewer"
    assert a.check("quantri", "sai") is None and a.check("ai_do", "mk-dai-123") is None
    assert not a.using_default


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
    assert a.using_default and a.check("admin", "admin").role == "admin"
    assert a.check("viewer", "") is None                             # không khai báo thì không có tài khoản chỉ xem
