import pytest

from blh.core.config import load_config


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("BLH_MODEL", "test-model")
    cfg = load_config(workdir=str(tmp_path))
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "http://localhost:9999/v1"
    assert cfg.model == "test-model"
    assert cfg.workdir == str(tmp_path)
    assert cfg.bash_timeout == 120
    assert cfg.max_output_chars == 30000


def test_load_config_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_base_url_defaults_to_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert load_config().base_url is None
