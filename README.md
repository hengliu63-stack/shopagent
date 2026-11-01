# ShopAgent — 一句话 AI 购物 Agent（PayPal AI Hackathon 2026）

> Say it. Agent shops. PayPal pays.

用户说一句话（"帮我买一本 200 块以内的 Python 书"），agent 自主完成：
自然语言意图解析 → 商品搜索与比价决策 → 建单 → 买家批准（合规环节）→
扣款 → 付款回执。全过程在聊天界面里可见，每一步都落审计日志。

目标奖项：**Best Use of Agentic Commerce**（PayPal AI Hackathon 2026）。

## 当前完成度（据实）

- ✅ 端到端离线流程已跑通：聊天界面 / CLI demo 输入一句话 → 比价 → 建单 →
  等批准 → 扣款 → 收据，状态机 10 个状态全程有 JSONL 审计轨迹。
- ✅ 测试：34 个 pytest 全过（全部离线、零 key 可跑）。
- ⚠️ **支付目前是离线演示桩**（`pay/stub.py`）：订单号以 `STUB-` 开头、
  收据带 `"stub": true` 标注，**不是**真实 PayPal 交易。
  真实链路代码已就绪（`pay/client.py`，官方 `paypal-server-sdk` +
  Orders API v2，环境写死 Sandbox、非 sandbox 拒绝启动），
  只差 PayPal Sandbox 的 Client ID / Secret 到位后跑冒烟出第一张真实收据。
- ⚠️ 商品数据是本地 demo 池（7 件 USD 商品）；Channel3 API 尚未接入
  （无 key），`catalog/search.py` 已预留接入点、失败自动降级 demo 池。

## 架构概览

```
ui/            聊天界面（标准库 http.server，零额外依赖）
               输入指令 · 比价候选表 · 状态轨迹 · 待批准卡片 · 收据卡片
      │  ui/service.py 把引擎输出包装成视图模型（JSON）
orchestrator/  agent 编排状态机
               IDLE→PARSED→SEARCHED→COMPARED→ORDER_CREATED→APPROVED
               →CAPTURED→DONE（异常→FAILED；超预算/等批准→SUSPENDED 可 resume）
               每步写 JSONL 执行日志（seq + elapsed_ms），即"自主决策"的审计证据
      ├── nlu/        自然语言 → 结构化意图 {query, budget_max, currency,
      │               quantity, preferences}；LLM 优先、规则版兜底
      ├── catalog/    搜索 + 比价排序 rank()：预算按总价=单价×数量判定，
      │               策略 honoring 偏好（便宜/口碑/热门优先）
      └── pay/        PayPal 付款：client.py（真实，Sandbox）
                      stub.py（离线演示桩，明确标注 stub）
```

核心叙事："一次授权，全程自主" —— 人只做一次自然语言授权和一次付款
批准（PayPal 合规必需），比价、下单、扣款、记账全由 agent 完成。

## 本地运行

环境：Python 3.11+。先建虚拟环境并装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # 界面本身只用标准库，
                                            # 依赖主要是 PayPal SDK 与 pytest
```

### 1) 聊天界面（离线 demo，支付为 stub 桩）

```bash
.venv/bin/python -m ui.app        # 打开 http://127.0.0.1:8765
# 端口可改：SHOPAGENT_UI_PORT=9000 .venv/bin/python -m ui.app
```

页面里输入一句话（或点示例），依次看到：意图解析 → 比价候选 →
状态轨迹/执行日志 → 订单卡 → 待批准卡片（点「批准」后 stub 桩扣款）→
收据卡片。超预算的指令会挂起为「超预算待确认」，可改预算续跑或取消。

### 2) CLI 端到端 demo

```bash
.venv/bin/python demo.py                                   # 3 条内置示例
.venv/bin/python demo.py "帮我买两本 100 块以内便宜点的 Python 书"
```

### 3) 测试

```bash
.venv/bin/python -m pytest tests/ -q     # 34 个，全离线
```

### 4) 真实 PayPal Sandbox 冒烟（需凭证，未到位前会优雅报错）

```bash
cp .env.example .env        # 填 Sandbox 的 PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET
.venv/bin/python -m pay.sandbox_smoke   # 建单 $1.00 → 批准链接 → capture → 收据
```

## Built With

- **PayPal** — Orders API v2 via the official **paypal-server-sdk** (Python);
  Sandbox environment only, hard-guarded against live money.
- **AI / LLM layer** — natural-language understanding through any
  OpenAI-compatible LLM endpoint (configured via `SHOPAGENT_LLM_API_KEY /
  SHOPAGENT_LLM_BASE_URL / SHOPAGENT_LLM_MODEL`), with a deterministic
  rule-based parser as automatic fallback; autonomous price-comparison
  ranking and a state-machine orchestrator with a full audit log.
- **Python 3.12 standard library** — the chat UI server (no web framework).
- **pytest** — 34 offline tests.
- Catalog data: bundled local demo pool for now; **Channel3** product API
  integration is planned (sponsor API, key pending) with the demo pool as
  fallback.

## 已知限制

| 事项 | 状态 |
|---|---|
| 真实 PayPal Sandbox 收据 | 待 Sandbox 凭证；现为离线 stub 轨迹（已如实标注） |
| 商品数据 | 本地 demo 池 7 件；Channel3 未接入 |
| LLM 解析 | 无 key 时自动降级规则版（功能完整，语义理解较弱） |
| 批准环节 | 必须买家人工批准一次（PayPal 合规要求，非技术限制） |
| 公开仓库 / Devpost 提交 | 已推送至本公开仓库；Devpost 提交待演示视频就绪后完成（早检目标 2026-11-05） |

## 目录结构

```
nlu/           自然语言 → 结构化购物意图（LLM + 规则兜底）
catalog/       商品搜索与比价（demo 池，Channel3 接入点已预留）
pay/           PayPal 付款：client（真实 Sandbox）/ stub（离线桩）
orchestrator/  agent 编排状态机 + JSONL 执行日志
ui/            聊天界面：service.py（服务层）+ app.py（标准库 HTTP）+ static/
demo.py        CLI 端到端演示
tests/         pytest 测试（34 个）
SUBMISSION.md  Devpost 提交文案草稿
```

## License

MIT
