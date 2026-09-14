import pytest

from blh.core.config import ConfigError, load_config


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


def test_load_config_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_base_url_defaults_to_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert load_config().base_url is None


def test_load_config_reads_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-from-dotenv\nOPENAI_BASE_URL=http://dotenv:1/v1\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.api_key == "sk-from-dotenv"
    assert cfg.base_url == "http://dotenv:1/v1"


def test_env_vars_take_precedence_over_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-dotenv\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.chdir(tmp_path)
    assert load_config().api_key == "sk-from-env"


def test_file_overrides_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("BLH_MODEL", raising=False)
    (tmp_path / ".blh.yaml").write_text(
        "model: file-model\nmax_output_chars: 123\n", encoding="utf-8")
    cfg = load_config()
    assert cfg.model == "file-model"
    assert cfg.max_output_chars == 123


def test_env_overrides_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_MODEL", "env-model")
    (tmp_path / ".blh.yaml").write_text("model: file-model\n", encoding="utf-8")
    cfg = load_config()
    assert cfg.model == "env-model"


def test_cli_overrides_all(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_MODEL", "env-model")
    (tmp_path / ".blh.yaml").write_text("model: file-model\n", encoding="utf-8")
    cfg = load_config(cli={"model": "cli-model"})
    assert cfg.model == "cli-model"


def test_invalid_int_raises_config_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_BASH_TIMEOUT", "abc")
    with pytest.raises(ConfigError):
        load_config()

