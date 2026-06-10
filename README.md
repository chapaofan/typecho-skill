# Typecho Agent API

> 给 LLM Agent 用的 Typecho 博客控制平面 —— 增删改文章 + 腾讯云 COS 图片上传。

本项目把 Typecho 后台的文章 / 分类 / 标签管理能力封装成 Python 函数 + OpenAI Function-Calling 格式的工具描述 + 一组 HTTP API，并以 **API Key** 做鉴权。任何能跑 Python 的 Agent 都可以直接 `pip install` 后调用，也可以用任何语言通过 HTTP 接入。

## 部署模型

```
┌────────────────────┐   HTTP + X-API-Key    ┌─────────────────────────────┐
│  Agent（openclaw/  │ ─────────────────────▶ │  Typecho 服务器（本项目）    │
│  hermes 等）       │ ◀─────────────────────  │  跑 uvicorn + 直读 typecho_ │
│  - 配 2 个环境变量  │                        │  MySQL + 调腾讯云 COS       │
│  - 不装任何 Python  │                        │                             │
└────────────────────┘                        └─────────────────────────────┘
```

- **服务端**（本仓库代码）部署在用户的 Typecho 服务器上，**不需要** agent 装任何东西
- **Agent** 只配 `TYPECHO_API_BASE_URL` + `TYPECHO_API_KEY` 两个环境变量，按 [skills/typecho-blog/SKILL.md](skills/typecho-blog/SKILL.md) 调用即可

---

## 功能

| 类别 | 工具（tool） | 说明 |
|---|---|---|
| 文章 | `create_post` | 新增文章（含分类、标签、自定义字段） |
| 文章 | `update_post` | 编辑文章（局部更新） |
| 文章 | `delete_post` | 删除文章（同步清理评论/标签计数/字段） |
| 文章 | `get_post` / `find_post_by_slug` / `list_posts` | 读取 |
| 分类 | `list_categories` / `create_category` / `delete_meta` | 分类管理 |
| 标签 | `list_tags` / `create_tag` / `delete_meta` | 标签管理 |
| 图片 | `upload_image_from_base64` / `upload_image_from_file` | 上传图片到腾讯云 COS，返回 URL |
| 图片 | `delete_cos_object` | 删除 COS 上的图片 |

> 实现细节与 Typecho 官方 PHP 代码保持一致（字段语义、状态机、计数更新、草稿逻辑等），见 [var/Widget/Contents/EditTrait.php](https://github.com/typecho/typecho) 的 `publish()` / `save()` / `setCategories()` / `setTags()`。

---

## 项目结构

```
typecho-agent-api/
├── README.md
├── pyproject.toml                # 可 pip install -e .
├── requirements.txt
├── .env.example                  # 复制为 .env 后修改
├── .gitignore
├── src/
│   └── typecho_agent_api/        # 真正的 Python package
│       ├── __init__.py           # 顶层 re-export
│       ├── __main__.py           # python -m typecho_agent_api
│       ├── config.py             # 从 .env 读配置
│       ├── auth.py               # API Key 鉴权
│       ├── typecho_db.py         # MySQL 连接池 + 通用 CRUD
│       ├── metas.py              # 分类 / 标签 / 关联
│       ├── contents.py           # 文章 CRUD（核心）
│       ├── cos_uploader.py       # 腾讯云 COS 上传
│       ├── agent_tools.py        # 工具 schema + dispatcher（核心）
│       └── server.py             # FastAPI HTTP 服务
├── examples/
│   ├── agent_usage.py            # 直接调用 dispatcher
│   ├── openai_agent.py           # 配合 OpenAI SDK 完整跑通
│   └── http_client.py            # 通过 HTTP 调用
├── tests/
│   └── test_smoke.py             # 烟雾测试（不连真实库）
└── skills/
    └── typecho-blog/
        └── SKILL.md              # 给远程 agent 用的 skill（HTTP-only）
```

---

## 安装与运行（服务端）

```bash
# 1) 克隆到 Typecho 服务器
cd /opt
git clone <your-repo> typecho-agent-api
cd typecho-agent-api

# 2) 建虚拟环境 + 装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3) 改配置
cp .env.example .env
vim .env      # 改 DB / COS / API_KEYS
```

`.env` 中**必须**改的三组配置：

```dotenv
# 1) Typecho 数据库（从博客根目录的 config.inc.php 复制）
TYPECHO_DB_HOST=localhost
TYPECHO_DB_PORT=3306
TYPECHO_DB_USER=xaomaozhou
TYPECHO_DB_PASSWORD=wdy1998101012
TYPECHO_DB_NAME=typecho
TYPECHO_TABLE_PREFIX=typecho_

# 2) 腾讯云 COS（https://console.cloud.tencent.com/cam/capi 申请）
COS_SECRET_ID=AKIDxxxxxxxx
COS_SECRET_KEY=xxxxxxxx
COS_REGION=ap-guangzhou
COS_BUCKET=example-1250000000
COS_CDN_DOMAIN=                          # 留空用 COS 默认域名

# 3) API Key（Agent 调用时需要带上）
API_KEYS=sk-please-change-me-1,sk-please-change-me-2
```

---

## 使用方式 1：作为 Python 库直接调用

> 适用场景：服务端跑在 Typecho 主机上，想用 Python 写自动化脚本（或自己也是个 LLM agent）。普通远程 agent 看 [使用方式 4](#使用方式-4给远程-agent-用-skill)。

```python
from typecho_agent_api import (
    ToolDispatcher, create_post, update_post, delete_post,
    get_post, list_posts, upload_base64,
)

dispatcher = ToolDispatcher()        # 给 LLM 用的工具集
tools = dispatcher.schemas           # OpenAI / Anthropic 通用格式

# 1) 直接调用
post = create_post({
    "title": "Python 装饰器入门",
    "content": "<p>...</p>",
    "tags": ["Python", "教程"],
    "status": "publish",
})
print(post["cid"], post["title"])

# 2) 上传图片
info = upload_base64(b64="iVBORw0KGgo...", filename="cover.png")
print(info["url"])
```

---

## 使用方式 2：配合 OpenAI Function Calling

见 [examples/openai_agent.py](examples/openai_agent.py)。要点：

```python
from openai import OpenAI
from typecho_agent_api import ToolDispatcher

client = OpenAI()
dispatcher = ToolDispatcher()

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "发一篇 Python 装饰器教程"}],
    tools=dispatcher.schemas,        # 注入工具
)
# 把 resp.choices[0].message.tool_calls 转发给 dispatcher
tool_msgs = dispatcher.handle_openai_tool_calls(resp.choices[0].message.tool_calls)
# 再用这些 tool_msgs 继续对话
```

同样的 schemas 也能直接喂给 Anthropic / Cohere / Qwen / DeepSeek / 任何兼容 OpenAI 协议的服务。

---

## 使用方式 3：作为 HTTP 服务

启动（任选其一，效果一致）：

```bash
# 推荐：装好包之后用 CLI 命令
typecho-server
# 等价：python -m typecho_agent_api
# 等价（要 cd 到 src/ 上一级）：uvicorn typecho_agent_api.server:app --host 0.0.0.0 --port 8000
```

`HTTP_HOST` / `HTTP_PORT` 在 `.env` 里配。

API 摘要（全部要求 `X-API-Key` 头）：

| Method | Path | 说明 |
|---|---|---|
| `GET`  | `/v1/tools` | 列出所有工具 schema |
| `POST` | `/v1/tools/call` | 调用任意工具 `{name, arguments}` |
| `POST` | `/v1/tools/call_openai` | 直接传 OpenAI 风格的 `tool_calls` 列表 |
| `POST` | `/v1/posts` | 新增文章 |
| `GET`  | `/v1/posts?page=1&page_size=20` | 列出文章 |
| `GET`  | `/v1/posts/{cid}` | 获取文章 |
| `GET`  | `/v1/posts/by-slug/{slug}` | 按 slug 查找 |
| `PATCH` | `/v1/posts/{cid}` | 更新文章 |
| `DELETE` | `/v1/posts/{cid}` | 删除文章 |
| `POST` | `/v1/images/upload` | multipart 上传图片 |
| `POST` | `/v1/images/upload_base64` | base64 上传图片 |
| `DELETE` | `/v1/images/{key:path}` | 删除图片 |

启动后访问 `http://localhost:8000/docs` 看到完整 Swagger UI。

调用示例（curl）：

```bash
curl -X POST http://localhost:8000/v1/posts \
  -H "X-API-Key: sk-please-change-me-1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试文章",
    "content": "<p>正文</p>",
    "tags": ["测试", "Agent"],
    "category_ids": [1],
    "status": "publish"
  }'

# 上传图片（base64）
curl -X POST http://localhost:8000/v1/images/upload_base64 \
  -H "X-API-Key: sk-please-change-me-1" \
  -H "Content-Type: application/json" \
  -d '{"base64_data":"iVBOR...","filename":"cover.png"}'
```

---

## 使用方式 4：给远程 Agent 用（skill）

如果消费方是**远程 LLM Agent**（openclaw / hermes / 任何能发 HTTP 的 agent 框架），**不需要安装本项目**，只需加载 [skills/typecho-blog/SKILL.md](skills/typecho-blog/SKILL.md) 并设两个环境变量：

```bash
export TYPECHO_API_BASE_URL="https://blog.example.com"
export TYPECHO_API_KEY="sk-xxxxxx"
```

SKILL.md 包含：
- 14 个工具的完整 OpenAI function-calling JSON 清单
- curl / Python `requests` / OpenAI 工具调用三套调用示例
- 字段约定、错误处理、安全注意事项

详见 [skills/typecho-blog/SKILL.md](skills/typecho-blog/SKILL.md)。

---

## 数据库结构对照

代码里的字段定义与 Typecho 原生表完全一致：

```
typecho_contents
├── cid (PK)
├── title / slug / text
├── created / modified     -- unix ts
├── authorId               -- → typecho_users.uid
├── type                   -- 'post' / 'page' / 'post_draft' / 'attachment'
├── status                 -- 'publish' / 'hidden' / 'private' / 'waiting'
├── password               -- 仅 status=password 时使用
├── allowComment / allowPing / allowFeed
└── parent

typecho_metas
├── mid (PK)
├── name / slug
├── type                   -- 'category' / 'tag'
└── count                  -- 文章数

typecho_relationships      -- contents <-> metas 多对多

typecho_fields             -- {cid, name, type, str_value, int_value, float_value}
```

`create_post()` 写入 `typecho_contents` 的同时，会：
- 在 `typecho_relationships` 中建立 cid ↔ 分类/标签的关联
- 维护 `typecho_metas.count`
- 在 `typecho_fields` 中存自定义字段

`delete_post()` 同步删除评论、关联、字段，并把对应分类/标签的 `count` 减 1（如果文章本来是 `publish`）。

---

## 安全建议

1. **改 API Key**：`API_KEYS` 不要用默认值。
2. **网络隔离**：建议把 `uvicorn` 绑在内网或加 nginx 反代 + HTTPS，对外只暴露必要的 `/v1/...` 端点。
3. **限流**：生产环境再加一个限流中间件（如 `slowapi`），本项目未内置。
4. **最小权限**：给 Typecho 数据库单独建一个账号，只授予 `SELECT/INSERT/UPDATE/DELETE` 四张表，不给 `DROP/GRANT`。
5. **审计**：写操作可以加一层审计日志（建议接到 `langfuse` / 自家 ELK）。
6. **签名校验**：`auth.py` 中预留了 `verify_signature()` 方法，目前未启用，可在反代侧启用 `X-Signature` 校验。

---

## 常见问题

**Q1: 为什么不通过 Typecho 的 PHP 后台接口来写？**
A: 直接写 MySQL 是最可靠、最快、最少依赖的方式。Typecho 没有公开的 REST API，自己造一遍字段映射容易出错，不如直接对齐官方表结构。

**Q2: 跟 Typecho 缓存兼容吗？**
A: 兼容。Typecho 自身没有数据缓存层（页面缓存是 HTML 级别），写完数据库立刻就能在前台看到。

**Q3: 怎么接入 Anthropic / Claude？**
A: 同样的 `TOOL_SCHEMAS` 可以直接转成 Anthropic 的 `tools=[{"name":..., "description":..., "input_schema":...}]`，schema 写法是兼容的（`type:object / properties / required` 是 JSON Schema 子集）。`ToolDispatcher.call()` 返回值放进 Anthropic 的 `tool_use_result` 即可。

**Q4: COS 报错 `SignatureDoesNotMatch`？**
A: 90% 是 `COS_SECRET_ID` / `COS_SECRET_KEY` 复制多了空格，或子账号没有 `cos:PutObject` 权限。

---

## License

MIT
