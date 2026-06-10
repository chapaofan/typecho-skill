---
name: typecho-blog
description: 通过 HTTP API 管理自建 Typecho 博客 —— 新增/编辑/删除文章、查询文章、管理分类与标签、上传图片到腾讯云 COS 并在文章中引用 CDN URL。Agent 通过 TYPECHO_API_BASE_URL + TYPECHO_API_KEY 两个环境变量调用远程服务，**不直接读写本机任何文件或数据库**。适用于 openclaw、hermes 等远程 agent，也兼容任何能发 HTTP 请求的 LLM Agent 框架。
allowed-tools: Bash, Read, WebFetch
---

# Typecho Blog — 远程 Agent Skill

这是一份**纯 HTTP 调用**说明。Agent 加载本 skill 后，只通过 `TYPECHO_API_BASE_URL`（远程 Typecho 服务器上的 typecho-agent-api 服务）+ `TYPECHO_API_KEY`（预共享密钥）调用 REST 接口，**不安装任何 Python 包、不读本机任何文件、不直接连数据库**。

服务端是独立部署的 [typecho-agent-api](https://github.com/chapaofan/typecho-server-and-skill) —— 跑在用户的 Typecho 服务器上，直接读写 typecho_* MySQL 表 + 调腾讯云 COS。本 skill 与服务端代码完全解耦。

## 何时使用

用户出现以下意图时使用：
- "发一篇...", "写一篇...", "在博客上发布..."
- "修改这篇文章...", "改一下标题/正文..."
- "删掉文章 cid=..."
- "上传图片到博客", "把图传到腾讯云"
- "列一下我的文章/分类/标签"
- "查一下 cid=N 的文章"
- "slug 是 xxx 的文章改一下..."
- "列出所有已发布的教程文章"

## 前置配置（必读）

调用前确保 agent 运行环境里**两个环境变量都已设置**：

| 变量 | 说明 | 示例 |
|---|---|---|
| `TYPECHO_API_BASE_URL` | 服务端 base URL（末尾**不要**带斜杠） | `https://blog.example.com` |
| `TYPECHO_API_KEY` | 服务端配置的预共享 key 之一 | `sk-xxxxxx` |

如果不确定，先做一次**健康检查**：

```bash
curl -fsS "$TYPECHO_API_BASE_URL/healthz"
# 期望返回：{"status":"ok"}
```

如果不通，向用户报错**而不是**去猜配置 —— 这通常是服务端未启动、域名未解析、或反代配置错误。

## 14 个可用工具（HTTP 端点）

| 类别 | Method + Path | 必填参数 | 说明 |
|---|---|---|---|
| 文章 | `POST /v1/posts` | `title`, `content` | 新增文章 |
| 文章 | `GET /v1/posts/{cid}` | - | 获取文章完整信息 |
| 文章 | `PATCH /v1/posts/{cid}` | `cid` | 局部更新（只传要改的字段） |
| 文章 | `DELETE /v1/posts/{cid}` | `cid` | 删除文章 + 清理关联 |
| 文章 | `GET /v1/posts?page=1&page_size=20` | - | 分页列表，可选 `status` / `keyword` |
| 文章 | `GET /v1/posts/by-slug/{slug}` | - | 按 URL 缩略名查找 |
| 分类 | `GET /v1/tools/call` `{name:"list_categories"}` | - | 列出所有分类 |
| 标签 | `GET /v1/tools/call` `{name:"list_tags"}` | - | 列出所有标签 |
| 分类 | `GET /v1/tools/call` `{name:"create_category",arguments:{name:...}}` | `name` | 新建分类 |
| 标签 | `GET /v1/tools/call` `{name:"create_tag",arguments:{name:...}}` | `name` | 新建标签 |
| 元数据 | `GET /v1/tools/call` `{name:"delete_meta",arguments:{mid:N}}` | `mid` | 删除分类/标签（同时解绑所有文章） |
| 图片 | `POST /v1/images/upload_base64` | `base64_data` | 上传 base64 图片到 COS |
| 图片 | `POST /v1/images/upload`（multipart） | `file` | 上传本地图片到 COS |
| 图片 | `DELETE /v1/images/{key:path}` | - | 删除 COS 上的图片 |

> 通用调度：`POST /v1/tools/call` body = `{"name": "<tool_name>", "arguments": {...}}` 可调任意上面未单独列 REST 端点的工具。返回统一是 `{"ok": true, "result": ...}` 或 `{"ok": false, "error": "..."}`。
>
> 想看完整清单可调 `GET /v1/tools` —— 实时从服务端拉。

## 工具 JSON 清单（OpenAI function-calling 格式）

> 这份清单和 `GET $TYPECHO_API_BASE_URL/v1/tools` 实时返回的格式一致，agent 框架可直接 parse 当作 tool 定义。

```json
[
  {"type":"function","function":{"name":"create_post","description":"在 Typecho 博客上新增一篇文章。返回文章 cid 及完整信息。","parameters":{"type":"object","properties":{"title":{"type":"string","description":"文章标题，1-200 字符"},"content":{"type":"string","description":"正文（HTML 或 markdown）"},"markdown":{"type":"boolean","default":false,"description":"content 是否为 markdown"},"slug":{"type":"string","description":"URL 缩略名，留空自动生成"},"status":{"type":"string","enum":["publish","hidden","password","private","waiting"],"default":"publish"},"password":{"type":"string","description":"status=password 时的访问密码"},"created_at":{"type":"integer","description":"发布时间（unix 秒）"},"tags":{"type":"array","items":{"type":"string"}},"category_ids":{"type":"array","items":{"type":"integer"}},"allow_comment":{"type":"boolean","default":true},"allow_ping":{"type":"boolean","default":true},"allow_feed":{"type":"boolean","default":true},"fields":{"type":"object","description":"自定义字段 {字段名:值}"}},"required":["title","content"]}}},
  {"type":"function","function":{"name":"update_post","description":"编辑一篇文章。所有字段都可选，未传则保留原值。","parameters":{"type":"object","properties":{"cid":{"type":"integer"},"title":{"type":"string"},"content":{"type":"string"},"markdown":{"type":"boolean"},"slug":{"type":"string"},"status":{"type":"string","enum":["publish","hidden","password","private","waiting"]},"password":{"type":"string"},"created_at":{"type":"integer"},"tags":{"type":"array","items":{"type":"string"}},"category_ids":{"type":"array","items":{"type":"integer"}},"allow_comment":{"type":"boolean"},"allow_ping":{"type":"boolean"},"allow_feed":{"type":"boolean"},"fields":{"type":"object"}},"required":["cid"]}}},
  {"type":"function","function":{"name":"delete_post","description":"删除一篇文章。同步删除评论、关联的分类/标签关系和自定义字段。","parameters":{"type":"object","properties":{"cid":{"type":"integer"}},"required":["cid"]}}},
  {"type":"function","function":{"name":"get_post","description":"获取一篇文章完整信息（含正文、分类、标签、自定义字段）。","parameters":{"type":"object","properties":{"cid":{"type":"integer"}},"required":["cid"]}}},
  {"type":"function","function":{"name":"find_post_by_slug","description":"通过 slug 查找一篇文章。","parameters":{"type":"object","properties":{"slug":{"type":"string"}},"required":["slug"]}}},
  {"type":"function","function":{"name":"list_posts","description":"分页列出文章，支持按状态、关键词过滤。","parameters":{"type":"object","properties":{"status":{"type":"string","enum":["publish","hidden","private","waiting"]},"keyword":{"type":"string"},"page":{"type":"integer","default":1},"page_size":{"type":"integer","default":20,"maximum":100}}}}},
  {"type":"function","function":{"name":"list_categories","description":"列出所有分类。","parameters":{"type":"object","properties":{}}}},
  {"type":"function","function":{"name":"list_tags","description":"列出所有标签。","parameters":{"type":"object","properties":{}}}},
  {"type":"function","function":{"name":"create_category","description":"新增一个分类。","parameters":{"type":"object","properties":{"name":{"type":"string"},"slug":{"type":"string"},"description":{"type":"string","default":""},"parent":{"type":"integer","default":0}},"required":["name"]}}},
  {"type":"function","function":{"name":"create_tag","description":"新增一个标签。","parameters":{"type":"object","properties":{"name":{"type":"string"},"slug":{"type":"string"}},"required":["name"]}}},
  {"type":"function","function":{"name":"delete_meta","description":"删除一个分类或标签（同时解除其与所有文章的关联）。","parameters":{"type":"object","properties":{"mid":{"type":"integer"}},"required":["mid"]}}},
  {"type":"function","function":{"name":"upload_image_from_base64","description":"上传 base64 编码的图片到腾讯云 COS，返回图片 URL。","parameters":{"type":"object","properties":{"base64_data":{"type":"string","description":"图片 base64（可带 data:image/png;base64, 前缀）"},"filename":{"type":"string","default":"image.png"}},"required":["base64_data"]}}},
  {"type":"function","function":{"name":"upload_image_from_file","description":"上传一张本地图片（服务端所在机器）到腾讯云 COS，返回图片 URL。","parameters":{"type":"object","properties":{"local_path":{"type":"string","description":"服务端机器上的绝对路径"}},"required":["local_path"]}}},
  {"type":"function","function":{"name":"delete_cos_object","description":"删除 COS 上的一个文件。","parameters":{"type":"object","properties":{"key":{"type":"string"}},"required":["key"]}}}
]
```

## 调用示例

### 示例 1：curl 发文章

```bash
curl -X POST "$TYPECHO_API_BASE_URL/v1/posts" \
  -H "X-API-Key: $TYPECHO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python 装饰器入门",
    "content": "<p>这是一篇教程...</p>",
    "tags": ["Python", "教程"],
    "status": "publish"
  }'
```

返回示例：
```json
{"cid": 123, "title": "Python 装饰器入门", "slug": "python-decorator-intro", "status": "publish", ...}
```

### 示例 2：curl 上传图片（base64）

```bash
curl -X POST "$TYPECHO_API_BASE_URL/v1/images/upload_base64" \
  -H "X-API-Key: $TYPECHO_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"base64_data\":\"$B64\",\"filename\":\"cover.png\"}"
```

返回示例：
```json
{"key": "blog/2025/06/abc12345__cover.png", "url": "https://cdn.example.com/blog/2025/06/abc12345__cover.png", "size": 12345}
```

拿到 `url` 后嵌进文章 HTML 即可：
```html
<p><img src="https://cdn.example.com/blog/2025/06/abc12345__cover.png" alt="cover"></p>
```

### 示例 3：Python `requests`

```python
import os, requests

BASE = os.environ["TYPECHO_API_BASE_URL"].rstrip("/")
KEY = os.environ["TYPECHO_API_KEY"]
H = {"X-API-Key": KEY, "Content-Type": "application/json"}

# 列文章
r = requests.get(f"{BASE}/v1/posts", headers=H, params={"page": 1, "page_size": 10})
r.raise_for_status()
for p in r.json()["items"]:
    print(p["cid"], p["title"])

# 发文章
r = requests.post(f"{BASE}/v1/posts", headers=H, json={
    "title": "测试", "content": "<p>正文</p>", "tags": ["测试"], "status": "publish"
})
r.raise_for_status()
print(r.json()["cid"])
```

### 示例 4：配合 LLM function-calling

如果 agent 用 LLM（OpenAI / Anthropic / 任何兼容 OpenAI 协议的服务），流程是：

```python
import os, json, requests
from openai import OpenAI

BASE = os.environ["TYPECHO_API_BASE_URL"].rstrip("/")
KEY = os.environ["TYPECHO_API_KEY"]

# 1) 实时从服务端拉 tool 清单（首选 —— 永远跟服务端一致）
tools = requests.get(f"{BASE}/v1/tools", headers={"X-API-Key": KEY}).json()["tools"]
# 也可以直接用本 skill 上面内嵌的 JSON 块，离线场景

# 2) 让 LLM 决定调什么工具
client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role":"user","content":"发一篇 Python 装饰器教程"}],
    tools=tools,
    tool_choice="auto",
)
msg = resp.choices[0].message

# 3) 把 LLM 的 tool_calls 整批转发给服务端执行
if msg.tool_calls:
    r = requests.post(
        f"{BASE}/v1/tools/call_openai",
        headers={"X-API-Key": KEY, "Content-Type": "application/json"},
        json={"tool_calls": [
            {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]},
    )
    tool_msgs = r.json()  # 直接拿回 messages 用的 tool 消息序列
```

## 关键字段约定

`create_post` / `update_post` 通用字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | str | 1-200 字符 |
| `content` | str | HTML 或 markdown |
| `markdown` | bool | true 时会自动加 `<!--markdown-->` 前缀 |
| `slug` | str | 留空自动生成 |
| `status` | enum | `publish` / `hidden` / `password` / `private` / `waiting` |
| `password` | str | `status=password` 时必填 |
| `created_at` | int | unix 时间戳（秒），缺省 = 当前时间 |
| `tags` | list[str] | 也接受 `"a,b,c"` 字符串（自动拆分） |
| `category_ids` | list[int] | 分类的 mid（先调 `list_categories` 拿） |
| `allow_comment` / `allow_ping` / `allow_feed` | bool | 权限 |
| `fields` | dict | 自定义字段 `{name: value}`，值会按类型自动推断 str/int/float |

## 标准工作流

### 发一篇带配图的文章

```python
import os, requests
BASE = os.environ["TYPECHO_API_BASE_URL"].rstrip("/")
H = {"X-API-Key": os.environ["TYPECHO_API_KEY"], "Content-Type": "application/json"}

# 步骤 1：确认分类存在
cats = requests.get(f"{BASE}/v1/tools/call", headers=H,
                    json={"name": "list_categories", "arguments": {}}).json()["result"]["items"]

# 步骤 2：上传配图（base64）
img = requests.post(f"{BASE}/v1/images/upload_base64", headers=H, json={
    "base64_data": "<B64>",
    "filename": "cover.png",
}).json()

# 步骤 3：把 img["url"] 插入正文，发文
html = f'<p>正文...</p><p><img src="{img["url"]}" alt="cover"></p>'
post = requests.post(f"{BASE}/v1/posts", headers=H, json={
    "title": "标题",
    "content": html,
    "tags": ["标签1", "标签2"],
    "category_ids": [cats[0]["mid"]],
    "status": "publish",
}).json()
print(post["cid"])
```

### 编辑现有文章

```python
# 步骤 1：找到文章
post = requests.get(f"{BASE}/v1/posts/{cid}", headers=H).json()

# 步骤 2：局部更新（只改要改的字段，其它保持原样）
updated = requests.patch(f"{BASE}/v1/posts/{cid}", headers=H, json={
    "title": "新标题",
    "tags": ["新标签1", "新标签2"],
}).json()
```

### 删除文章（要确认！）

```python
# 删之前先 GET 出来给用户看一眼
post = requests.get(f"{BASE}/v1/posts/{cid}", headers=H).json()
# → 让用户确认 → 调 DELETE
ok = requests.delete(f"{BASE}/v1/posts/{cid}", headers=H).json()
```

## 错误处理

服务端统一返回结构：

| HTTP | body | 含义 |
|---|---|---|
| 401 | `{"detail": "invalid or missing X-API-Key"}` | key 错 / 漏带 |
| 404 | `{"detail": "post not found: cid=..."}` | 资源不存在 |
| 422 | FastAPI 默认 validation error | 请求参数不合法（看 `detail` 数组） |
| 500 | `{"ok": false, "error": "TypeName: msg"}` | 服务端异常（可能 DB/COS 故障） |

`POST /v1/tools/call` 和 `POST /v1/tools/call_openai` 的业务错误**不会**抛 HTTP 4xx，而是返回 `{"ok": false, "error": "..."}` 写在 body 里 —— agent 应该检查 `ok` 字段。

写操作前若不确定 `cid` / `mid` 是否存在，**先读再写**。用户说"删掉那篇讲 Python 的文章"时，**不要直接删** —— 先用 `list_posts(keyword="Python")` 列出候选，让用户确认 cid。

## 安全注意

1. **永远不要**把 `TYPECHO_API_KEY` echo 到日志、聊天、git 提交里。配置文件里也尽量从环境变量读。
2. **不要**调 `upload_image_from_file(local_path=...)` 传 agent 自己的本机路径 —— 该路径在**服务端**机器上解析，agent 本机的文件服务端读不到。传图片请用 `upload_image_from_base64`。
3. `created_at` 是 unix 时间戳（秒），不是字符串。
4. `delete_post` 是物理删除 —— Typecho 自身的回收站机制不会生效。如果需要"软删"，把 `status` 改成 `hidden`。
5. 图片上传走 COS，**不会**写入 Typecho 的 `attachments` 表 —— 这是有意为之的，文章里直接用 COS 返回的 CDN URL 即可（更省服务器空间、CDN 加速）。
6. 如果服务端配了 HTTPS（推荐），`TYPECHO_API_BASE_URL` 用 `https://`，key 走 TLS 加密；不要用 `http://` 走公网。

## 部署模型回顾

```
┌────────────────────┐   HTTP + X-API-Key    ┌─────────────────────────────┐
│  本 agent          │ ─────────────────────▶ │  $TYPECHO_API_BASE_URL       │
│  - 配 2 个环境变量  │ ◀─────────────────────  │  typecho-agent-api 服务      │
│  - 不装任何 Python  │                        │  - 直读 typecho_* MySQL      │
│  - 不碰本机文件     │                        │  - 调腾讯云 COS              │
└────────────────────┘                        └─────────────────────────────┘
```

服务端代码与本 skill 完全独立 —— 服务端在 [typecho-server-and-skill 仓库](https://github.com/chapaofan/typecho-server-and-skill) 维护，本 skill 只是给 agent 用的"使用说明书"。
