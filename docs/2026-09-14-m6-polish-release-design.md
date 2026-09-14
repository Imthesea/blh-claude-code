# blh-claude-code M6:打磨与发布 设计文档

- **日期**:2026-09-14
- **状态**:已实施
- **来源**:主设计文档 §7 里程碑 M6

---

## 1. 目标

对前 5 个里程碑已可运行的产品做发布前打磨,交付一个可被 `pipx` / `pip` 干净安装并配置使用的 CLI:

1. **配置体系**:支持「默认值 < 配置文件 < 环境变量 < CLI 参数」四层优先级。
2. **错误恢复完善**:429 读取 `Retry-After`,退避加抖动。
3. **README**:安装、配置、用法说明。
4. **打包发布**:补齐 pyproject 元数据,验证 `uv build` 产物可安装。

M6 验收:`pipx install .`(或 `uv build` + 本地 wheel 安装)后 `blh` 命令可用。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 配置文件格式 | YAML(复用现有 `PyYAML` 依赖,`yaml.safe_load` 读取) |
| 配置文件位置 | 项目级 `./.blh.yaml` + 用户级 `~/.config/blh/config.yaml`,两处都读、项目级覆盖用户级 |
| 优先级 | 内置默认 < 配置文件 < 环境变量 < CLI 参数 |
| 配置项 | `model` / `base_url` / `api_key` / `workdir` / `bash_timeout` / `max_output_chars` |
| 环境变量 | 保留 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `BLH_MODEL`,新增 `BLH_BASH_TIMEOUT` / `BLH_MAX_OUTPUT_CHARS` |
| CLI 参数 | `--model` / `--base-url` / `--workdir` / `--bash-timeout` / `--max-output-chars`;`--api-key` 不提供(敏感,走 env) |
| Retry-After | 仅 429 读取;`Retry-After` 优先,缺失则指数退避 + 抖动 |
| 抖动 | 乘法抖动 `base * uniform(0.5, 1.5)`,封顶 32s |
| 发布动作 | 本里程碑只「打包验证 + 元数据补齐」,不执行真实 `twine upload`(由用户手动发布) |

## 3. 配置体系

### 3.1 Config 数据类扩展

`Config` 保持不变(字段已齐),新增默认值来源分层:

```
api_key / base_url / model / workdir / bash_timeout / max_output_chars
```

### 3.2 加载流程 `load_config(workdir=None, cli=None)`

1. 解析 CLI 参数,得 `cli` 覆盖字典(只含用户显式传入的键)。
2. 定位 `.env`(沿用 `_find_dotenv`,从 cwd 向上),`load_dotenv`(已存在环境变量优先)。
3. 读配置文件:
   - `_find_config(start)` 按「低优先级在前」返回 `[用户级 ~/.config/blh/config.yaml, 项目级 ./.blh.yaml]`(仅含存在的文件)。
   - 依次 `yaml.safe_load`,后读(项目级)覆盖先读(用户级),合并进 `file_values`。
4. 按优先级合成最终值:`defaults → file_values → env → cli`。
5. `api_key` 最终为空则 `SystemExit("OPENAI_API_KEY is not set")`(现有语义保留)。

### 3.3 配置键名映射

| Config 字段 | 文件键 | 环境变量 | CLI |
|---|---|---|---|
| api_key | `api_key` | `OPENAI_API_KEY` | — |
| base_url | `base_url` | `OPENAI_BASE_URL` | `--base-url` |
| model | `model` | `BLH_MODEL` | `--model` |
| workdir | `workdir` | — | `--workdir` |
| bash_timeout | `bash_timeout` | `BLH_BASH_TIMEOUT` | `--bash-timeout` |
| max_output_chars | `max_output_chars` | `BLH_MAX_OUTPUT_CHARS` | `--max-output-chars` |

### 3.4 类型转换

- 文件与 env 的 `bash_timeout` / `max_output_chars` 为字符串,统一 `int()` 转换;转换失败抛 `ConfigError`(新异常,提示哪个来源哪个键)。
- `base_url` / `model` / `api_key` / `workdir` 直接取字符串。

## 4. 错误恢复完善

改 `providers/retry.py`,不改 `OpenAIProvider.chat` 调用方签名:

- `retry_after_seconds(error) -> float | None`:读 `error.response.headers.get("Retry-After")`,尝试 `float` 解析;无效返回 None。异常对象无 `.response` 时返回 None。
- `retry_delay(attempt, error=None) -> float`:
  - 若 `retry_after_seconds(error)` 有值且 > 0,返回该值(不封顶,尊重服务端)。
  - 否则 `base = min(2 ** attempt, 32)` 返回 `base * random.uniform(0.5, 1.5)`。
- `with_retry` 捕获异常后 `time.sleep(retry_delay(state.attempts, e))`,保持 `max_attempts` 语义不变。

## 5. README

新建 `README.md`,内容:

- 一句话定位(OpenAI 兼容 Agent CLI)。
- 安装:`pipx install blh-claude-code` / `uv tool install` / `pip install`。
- 快速开始:配置 `.env` 或 `.blh.toml`,`blh` 交互、`blh -p "..."` 一次性。
- 配置说明:四层优先级、全部键、示例 TOML。
- 功能概览:里程碑 M0–M6 简要清单。
- 开发:`uv sync --dev`、`uv run pytest`、`uv run ruff check`。

## 6. 打包发布

- `pyproject.toml` 补齐:`readme = "README.md"`、`license`(若已存在 LICENSE 文件)、`classifiers`、`keywords`、`authors`(按仓库现状填,不虚构)。
- 验证:`uv build` 产出 sdist + wheel;`pipx install .` 或安装 wheel 后 `blh --help` 可运行。

## 7. 测试策略

- `tests/core/test_config.py`:四层优先级、文件发现、TOML 解析、类型转换失败、缺失 api_key、CLI 覆盖。
- `tests/providers/test_retry.py`:Retry-After 优先、无 Retry-After 走指数+抖动(monkeypatch random)、封顶、`retry_after_seconds` 解析失败。
- README / 打包无单测,以 `uv build` + 手动 `pipx install` 冒烟验收。
