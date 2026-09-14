# blh-claude-code

一个基于 OpenAI 兼容接口的编码 Agent CLI,命令名 `blh`。

把 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 教程中 s01–s17 的 17 个机制整合为一个可实际使用的命令行工具,通过 `python-dotenv` 加载密钥、`openai` SDK 接入任意 OpenAI 兼容模型。

## 安装

要求 Python 3.11+。

```bash
# 推荐:pipx 全局安装,blh 命令随处可用
pipx install blh-claude-code

# 或安装进当前 Python 环境
pip install blh-claude-code

# 或源码开发模式
uv sync --dev
uv run blh --help
```

## 快速开始

`blh` 需要一个 OpenAI 兼容服务的 API key。最小配置只需设置一个环境变量:

```bash
export OPENAI_API_KEY=sk-xxx
```

然后启动交互式会话:

```bash
blh
```

或一次性提问并打印回复:

```bash
blh -p "解释这个仓库的结构"
```

## 配置

配置采用四层优先级,后者覆盖前者:

```
内置默认值 < 配置文件 < 环境变量 < CLI 参数
```

### 配置文件

支持两级 YAML 配置文件,就近的项目级覆盖用户级:

- 用户级:`~/.config/blh/config.yaml`
- 项目级:`./.blh.yaml`

示例 `.blh.yaml`:

```yaml
model: gpt-4o-mini
base_url: https://api.openai.com/v1
bash_timeout: 120
max_output_chars: 30000
```

> 建议把 `api_key` 放在环境变量或 `.env` 里,不要写进配置文件。

### 环境变量

| 变量 | 含义 | 默认 |
|---|---|---|
| `OPENAI_API_KEY` | 必填,API key | — |
| `OPENAI_BASE_URL` | 兼容服务的 base URL | 无(用 SDK 默认) |
| `BLH_MODEL` | 模型名 | `gpt-4o-mini` |
| `BLH_BASH_TIMEOUT` | bash 工具超时(秒) | `120` |
| `BLH_MAX_OUTPUT_CHARS` | 工具输出截断字符数 | `30000` |

也支持在项目根目录放 `.env` 文件(已存在的环境变量优先,不会被覆盖)。

### CLI 参数

```bash
blh --model <model> --base-url <url> --workdir <dir> \
    --bash-timeout <seconds> --max-output-chars <n>
```

## 功能概览

| 里程碑 | 能力 |
|---|---|
| M0 | 骨架、provider、agent loop、hook 总线、内置工具、权限审批、REPL |
| M1 | 上下文压缩、todo/任务图、长期记忆 |
| M2 | 后台任务、cron 调度 |
| M3 | subagent、多智能体团队 |
| M4 | skills 加载、MCP 客户端 |
| M5 | 工作流编排(journal 断点恢复)、目标循环 |
| M6 | 配置体系、错误恢复、打包发布 |

## 开发

```bash
uv sync --dev
uv run pytest            # 全量测试(默认跳过 live)
uv run ruff check src/blh tests
uv build                 # 产出 wheel + sdist
```
