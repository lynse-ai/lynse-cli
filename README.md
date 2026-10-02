# 灵光记 (Lynse CLI)

<div align="center">

**🎯 智能会议管理命令行工具**

[![npm version](https://badge.fury.io/js/%40lynse.ai%2Flynse-cli.svg)](https://www.npmjs.org/package/@lynse.ai/lynse-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

</div>

## ✨ 功能特色

- 📋 **会议管理** - 查询、搜索、整理会议记录
- 🤖 **AI 总结** - 智能会议总结和转写
- 📁 **智能整理** - 自动分类会议到文件夹
- ✅ **待办管理** - 管理和清理待办事项
- 📱 **设备管理** - 管理绑定设备
- 🔌 **MCP 服务** - 已拆分到独立仓库 [lynse-mcp](https://github.com/lynse-ai/lynse-mcp)

## 🚀 快速开始

### 安装

```bash
# 推荐使用 npx 一键安装
npx -y @lynse.ai/lynse-cli@latest

# AI 助手环境添加 skill（OpenClaw 等）
npx skills add lynse-ai/lynse-cli

# 或全局安装
npm install -g @lynse.ai/lynse-cli

# Python 项目复用同一 API 客户端
python3 -m pip install "git+https://github.com/lynse-ai/lynse-cli.git@v1.8.5"
```

**正式 API 地址**: `https://api.lynse.cn`（默认使用；自定义地址须为 HTTPS）

### 在 Codex 中使用（推荐插件方式）

按照 [OpenAI 插件打包规范](https://developers.openai.com/plugins/build/plugins)，
本项目提供只包含 skill 和 Python CLI 的插件，同时兼容普通 skill 安装。

在仓库根目录构建并添加本地 marketplace：

```bash
python3 scripts/build_skill_package.py --codex
codex plugin marketplace add ./dist/codex
```

构建产物：

- `dist/lynse-cli-codex-plugin.zip`：包含完整运行文件的插件 ZIP。
- `dist/codex/`：可直接添加的本地 marketplace，保留此目录供后续刷新。

在桌面端 Plugins Directory 选择 **Lynse Local Plugins** 来源并安装 **灵光记 Lynse CLI**。
支持命令行安装的 Codex 版本也可运行：

```bash
codex plugin add lynse-cli@lynse-local
```

插件不自带 Python、依赖或凭据。需要 Python 3.11+；复用已有 Python 环境，
或在可写工作目录创建虚拟环境。以下是 macOS / Linux 的首次配置示例：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r dist/codex/plugins/lynse-cli/skills/lynse-cli/requirements.txt
.venv/bin/python dist/codex/plugins/lynse-cli/skills/lynse-cli/lynse.py auth login
```

`auth login` 会在用户自己的终端私下读取密钥并保存到 `~/.lynse/config.json`。
已配置的账号可直接复用；不需要把密钥贴进聊天或写入插件目录。
Windows 的 Python、虚拟环境及路径说明见
[平台与安装参考](references/platform-paths.md)。

安装后在新聊天中输入：

```text
使用 $lynse-cli 查询我最近七天的灵光记会议，并汇总已有总结和待办。
```

插件模式可从 skill 选择器选择 `lynse-cli`；宿主可能显示 `lynse-cli:lynse-cli`
这样的插件命名空间。自然语言提到 Lynse / 灵光记也可以触发。
Codex 会从实际加载的 skill 路径定位 CLI，不依赖当前工作目录。

若只需要普通 skill，运行 `python3 scripts/build_skill_package.py`，将生成的
`dist/lynse-cli-skill.zip` 解压到 `~/.agents/skills/lynse-cli/` 或项目的
`.agents/skills/lynse-cli/`。插件和普通 skill 选择一种启用，避免同名副本重复出现。
源文件改动后需重新构建并刷新插件；不要在插件缓存内运行 CLI 的 `update`。

### 配置

```bash
# 配置 API 密钥
lynse auth login

# 查看个人信息
lynse me
```

## 💻 基本使用

```bash
# 查看最近的会议
lynse meetings list

# 获取会议总结
lynse meetings summary <会议ID>            # 默认返回第一篇；--all 返回全部总结

# 整理会议到文件夹
lynse meetings organize --execute

# 管理待办事项
lynse todos list
```

## 📖 详细文档

- 📋 [命令参考](references/commands.md) - 完整命令列表
- 🤖 [Skill 工作流](SKILL.md) - Codex 调用方式、认证和授权边界
- 🔄 [更新日志](CHANGELOG.md) - 版本更新记录
- 🔌 [MCP 服务仓库](https://github.com/lynse-ai/lynse-mcp) - 独立的 MCP 服务项目

## 🌟 主要功能

### 1. 会议查询
```bash
lynse meetings list --days 7          # 最近7天会议
lynse meetings month 2026-04           # 指定月份会议
lynse meetings search 关键词          # 搜索会议
lynse meetings search 关键词 --from 2026-04-01 --to 2026-04-30
```

### 2. AI 智能功能
```bash
lynse meetings summary <ID>            # 获取第一篇 AI 总结（--all 获取全部）
lynse meetings outline <ID>           # 获取会议大纲
lynse meetings transcript <ID>        # 获取完整转写
lynse meetings transcript <ID> -o transcript.txt # 保存带时间戳的文本
lynse meetings audio <ID>             # 获取音频下载信息
lynse meetings summary <ID> -o summary.md # 保存 Markdown 正文
```

### 3. 自动整理
```bash
lynse meetings organize                # 预览整理计划
lynse meetings organize --execute      # 执行整理
```

### 4. 待办管理
```bash
lynse todos list                       # 查看待办
lynse todos clear                      # 清理已完成
lynse todos reschedule <ID> 2026-08-15 # 调整截止时间
```

## 🔧 系统要求

- Python 3.11 或更高版本
- Windows / macOS / Linux
- 网络连接

## ❓ 获取帮助

```bash
lynse --help                          # 查看帮助
lynse version                         # 查看版本
lynse update --check                  # 检查 npm 上的最新版本
lynse update                          # 自动更新到最新版（含 SKILL.md 与参考文档）
lynse doctor                         # 系统诊断
```

## 📞 支持与反馈

- 🐛 [问题反馈](https://github.com/lynse-ai/lynse-cli/issues)
- 🌐 [官方网站](https://www.lynse.ai)
- 📧 邮箱: support@lynse.ai

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

<div align="center">

**[灵光记 Lynse](https://www.lynse.ai)** - 让会议管理更智能

Made with ❤️ by lynse.ai

</div>
