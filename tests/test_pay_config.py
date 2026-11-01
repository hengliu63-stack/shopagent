"""pay 配置测试：缺凭证 / 非法环境必须明确报错（不静默失败）。"""
import os

from pay.config import PayConfig, PayConfigError


def _clean_env():
    for k in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_ENV"):
        os.environ.pop(k, None)


def test_missing_creds_raises():
    _clean_env()
    try:
        PayConfig.from_env()
    except PayConfigError as exc:
        assert "PAYPAL_CLIENT_ID" in str(exc)
        return
    raise AssertionError("缺凭证应抛 PayConfigError")


def test_production_env_rejected():
    _clean_env()
    os.environ["PAYPAL_CLIENT_ID"] = "x"
    os.environ["PAYPAL_CLIENT_SECRET"] = "y"
    os.environ["PAYPAL_ENV"] = "live"
    try:
        PayConfig.from_env()
    except PayConfigError as exc:
        assert "sandbox" in str(exc).lower()
        return
    finally:
        _clean_env()
    raise AssertionError("生产环境必须被拒绝")
