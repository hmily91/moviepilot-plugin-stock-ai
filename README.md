# moviepilot-plugin-stock-ai

一个 **MoviePilot V3 插件源仓库**，内含插件 **「股票AI分析助手」**（插件 id：`stockai`）。

本仓库符合 MoviePilot V3 插件源规范：仓库根为全局市场索引 `package.v3.json`，插件代码位于 `plugins.v3/stockai/`。可整体作为「插件仓库地址」加入 MoviePilot 的插件市场，或在本地以目录方式安装。

---

## 插件简介：股票AI分析助手

获取沪深 A 股实时行情与近 5 日 K 线，复用系统「智能助手」或自定义 LLM 接口进行**技术面 / 短期走势 / 风险提示**分析，并定时推送早盘预判与收盘分析报告；插件详情页内置「历史分析」页面。

- 行情：东方财富公开接口，无需密钥，支持沪深 A 股（含创业板）。
- LLM：默认复用系统「智能助手」的 LLM 配置，也可在配置页自定义 OpenAI 兼容接口。
- 定时：早盘预判（默认 09:00）/ 收盘分析（默认 15:30），时间可配。
- 推送：复用 MoviePilot 全局消息通道（微信 / 钉钉 / Telegram 等）。
- 历史：详情页回看每次分析结果，支持筛选与清空。

完整功能、配置项、API 与联调说明见 [`plugins.v3/stockai/README.md`](plugins.v3/stockai/README.md)。

---

## 安装到 MoviePilot

### 方式 A：作为插件源加入插件市场（推荐）

1. MoviePilot → **插件** → **插件市场设置**（或「添加第三方仓库」）。
2. 在「插件仓库地址」加入本仓库地址（多源用逗号分隔）：
   ```
   https://github.com/hmily91/moviepilot-plugin-stock-ai
   ```
   也可通过环境变量 `PLUGIN_MARKET` 配置（Docker 写在 `docker-compose.yml` 的 environment）。
3. 同步插件源（或重启 MoviePilot），在市场中搜索「股票AI分析助手」并安装启用。

### 方式 B：本地目录安装

将本仓库的 `plugins.v3/stockai/` 目录整体复制到 MoviePilot 的 `plugins.v3/stockai/` 下，重启并启用。

---

## 仓库结构

```text
moviepilot-plugin-stock-ai/
├── package.v3.json      # 全局插件市场索引（id -> 元数据）
├── README.md            # 本说明（插件源仓库）
├── icons/stockai.png    # 插件图标
├── push_to_github.py    # 创建/推送本仓库到 GitHub（Token 从环境变量读取）
├── gen_icon.py          # 生成图标脚本（仅开发用）
└── plugins.v3/
    └── stockai/         # 插件目录（id = stockai）
        ├── plugin.json / main.py / __init__.py / package.v3.json
        ├── README.md    # 插件详细文档
        └── tests/       # 本地联调集成测试
```

---

## 免责声明

本插件所有 AI 分析结论均明确标注「仅为技术分析参考，不构成投资建议」。插件不对任何投资决策负责，使用者需自行承担风险。
