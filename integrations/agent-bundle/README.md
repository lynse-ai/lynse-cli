# Lynse CLI 通用包

同一份 CLI 和 Skill 可在支持 Python 3.11+、Shell、HTTPS 和持久化用户目录的 Agent 中运行。凭据保存在执行 CLI 的环境中。远程运行时需要在该环境发起授权。

| 宿主 | 安装方式 |
| --- | --- |
| Codex | 将 `skills/lynse-cli/` 整个目录复制到项目的 `.agents/skills/`，或用户的 `~/.agents/skills/`。[Codex Skills](https://developers.openai.com/codex/skills) |
| Claude Code | 将同一个目录复制到项目的 `.claude/skills/`，或用户的 `~/.claude/skills/`。[Claude Code Skills](https://code.claude.com/docs/en/skills) |
| Muse Code | 解压后运行 `muse skills install ./skills/lynse-cli --scope user`。[Muse Code Skills](https://dev.meta.ai/docs/muse-code/extending) |
| WorkBuddy | 用包内的 `workbuddy/lynse-workbuddy-cli-connector.zip` 接入 CLI + Skill。连接器由宿主管理安装、授权和断开，要求 WorkBuddy 5.0.0 或以上。[WorkBuddy 接入规范](https://open.workbuddy.cn/docs/connector#CLI%20%2B%20Skill%20%E6%8E%A5%E5%85%A5) |
| 其他 Agent | 将 `skills/lynse-cli/` 放入宿主支持的 Skill 目录。支持 Shell 和 HTTPS 的宿主也可直接执行下方 CLI。只有网页聊天的宿主需要提供相应的工具运行能力，例如支持远程 MCP 时可连接 Lynse MCP。 |

## 独立 CLI

用所选 Python 环境安装包内 `wheel/` 目录下的 wheel。可用 `SHA256SUMS` 核对安装包。

```sh
python -m pip install ./wheel/LYNSE_WHEEL_FILENAME
lynse version --json
lynse auth login --device --profile default
lynse auth status --device --profile default --json
lynse --device-session default meetings list --days 7 --json
```

在安装命令中替换实际 wheel 文件名。也可以按 Skill 说明直接运行随附的 `lynse.py`，并在所用 Python 环境中安装 `requirements.txt`。

打开 CLI 输出的授权页，先确认账号，再输入六位设备码。设备码有效期为五分钟，授权期间保持命令运行。需要写权限时，登录命令可加 `--request-write`，然后在网页选择授权范围。

通过 `lynse auth logout --device --profile default --json` 断开。不同 Agent 可用不同 profile；查询、状态和断开时沿用对应名称。
