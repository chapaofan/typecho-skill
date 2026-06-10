"""
给 LLM Agent 用的工具（tool）层。

提供：
- TOOL_SCHEMAS : OpenAI / Anthropic / 通用 OpenAI-compatible 格式的工具描述
- ToolDispatcher: 根据 tool name 调度实际 handler，handler 返回的 dict 就是 tool 调用的结果
- 一个可选的 HTTP / Anthropic 风格 tool_use wrapper

调用关系：
    LLM ──► tool_call(name, args) ──► ToolDispatcher.call(name, args) ──► handler()
                ▲                                                              │
                └────────────── 把 handler 的 dict 返回给 LLM ◄─────────────────┘

handler 抛出异常时会被捕获并以 {"error": "..."} 形式返回给 LLM，避免破坏对话流程。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .contents import (
    PostCreate,
    PostUpdate,
    create_post,
    delete_post,
    find_post_by_slug,
    get_post,
    list_posts,
    update_post,
)
from .metas import (
    create_meta,
    delete_meta,
    get_meta_by_name,
    get_meta_by_slug,
    list_categories,
    list_tags,
)
from .cos_uploader import upload_base64, upload_bytes, upload_file, delete as cos_delete

logger = logging.getLogger(__name__)


# ============================================================
# Tool Schemas — OpenAI / Anthropic 通用格式
# ============================================================
# 每个 schema 描述一个 tool，对应 LLM 的 function_call / tool_use。
# 字段说明：
#   type: "function"        —— OpenAI 标准
#   function.name          —— 工具名（agent 调用的 key）
#   function.description   —— 自然语言描述
#   function.parameters    —— JSON Schema
# ============================================================

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    # ---------- 文章 ----------
    {
        "type": "function",
        "function": {
            "name": "create_post",
            "description": "在 Typecho 博客上新增一篇文章。返回文章 cid 及完整信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "文章标题，1-200 字符"},
                    "content": {"type": "string", "description": "正文（HTML 或 markdown）"},
                    "markdown": {"type": "boolean", "default": False,
                                 "description": "content 是否为 markdown，true 时会在前加 <!--markdown--> 标记"},
                    "slug": {"type": "string", "description": "URL 缩略名，留空自动生成"},
                    "status": {"type": "string", "enum": ["publish", "hidden", "password", "private", "waiting"],
                               "default": "publish", "description": "文章公开度"},
                    "password": {"type": "string", "description": "当 status=password 时的访问密码"},
                    "created_at": {"type": "integer", "description": "发布时间（unix 秒），默认当前时间"},
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "标签列表，例如 ['Python','教程']"},
                    "category_ids": {"type": "array", "items": {"type": "integer"},
                                     "description": "分类 mid 列表，可通过 list_categories 查到"},
                    "allow_comment": {"type": "boolean", "default": True},
                    "allow_ping": {"type": "boolean", "default": True},
                    "allow_feed": {"type": "boolean", "default": True},
                    "fields": {"type": "object",
                               "description": "自定义字段 {字段名: 值}，值会按类型自动推断 str/int/float"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_post",
            "description": "编辑一篇文章。所有字段都可选，未传则保留原值。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cid": {"type": "integer", "description": "文章 cid"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "markdown": {"type": "boolean"},
                    "slug": {"type": "string"},
                    "status": {"type": "string", "enum": ["publish", "hidden", "password", "private", "waiting"]},
                    "password": {"type": "string"},
                    "created_at": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "category_ids": {"type": "array", "items": {"type": "integer"}},
                    "allow_comment": {"type": "boolean"},
                    "allow_ping": {"type": "boolean"},
                    "allow_feed": {"type": "boolean"},
                    "fields": {"type": "object"},
                },
                "required": ["cid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_post",
            "description": "删除一篇文章。会同步删除该文章的评论、关联的分类/标签关系和自定义字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cid": {"type": "integer", "description": "要删除的文章 cid"},
                },
                "required": ["cid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_post",
            "description": "获取一篇文章的完整信息（含正文、分类、标签、自定义字段）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cid": {"type": "integer", "description": "文章 cid"},
                },
                "required": ["cid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_post_by_slug",
            "description": "通过 URL 缩略名（slug）查找一篇文章。",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "URL 缩略名"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_posts",
            "description": "分页列出文章，支持按状态、关键词过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["publish", "hidden", "private", "waiting"],
                               "description": "按状态过滤，不传则全部"},
                    "keyword": {"type": "string", "description": "标题或正文中包含的关键词"},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20, "maximum": 100},
                },
            },
        },
    },
    # ---------- 分类 / 标签 ----------
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "列出所有分类。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": "列出所有标签。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_category",
            "description": "新增一个分类。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "分类名"},
                    "slug": {"type": "string", "description": "URL 缩略名，留空自动生成"},
                    "description": {"type": "string", "default": ""},
                    "parent": {"type": "integer", "default": 0, "description": "父分类 mid"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tag",
            "description": "新增一个标签。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meta",
            "description": "删除一个分类或标签（同时解除其与所有文章的关联）。",
            "parameters": {
                "type": "object",
                "properties": {"mid": {"type": "integer"}},
                "required": ["mid"],
            },
        },
    },
    # ---------- 图片上传（腾讯云 COS）----------
    {
        "type": "function",
        "function": {
            "name": "upload_image_from_base64",
            "description": "上传 base64 编码的图片到腾讯云 COS，返回图片 URL。"
                           "可被 Agent 用于把 DALL·E/Stable Diffusion 等生成的图片或截图发布到博客。",
            "parameters": {
                "type": "object",
                "properties": {
                    "base64_data": {"type": "string",
                                    "description": "图片的 base64 编码（可带 data:image/png;base64, 前缀）"},
                    "filename": {"type": "string", "default": "image.png",
                                  "description": "保存的文件名（影响 key 扩展名）"},
                },
                "required": ["base64_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_image_from_file",
            "description": "上传一张本地图片（服务器侧）到腾讯云 COS，返回图片 URL。",
            "parameters": {
                "type": "object",
                "properties": {
                    "local_path": {"type": "string", "description": "本地文件绝对路径"},
                },
                "required": ["local_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_cos_object",
            "description": "删除 COS 上的一个文件。",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "对象 key"}},
                "required": ["key"],
            },
        },
    },
]


# ============================================================
# Handlers — 真实执行逻辑
# ============================================================

def _h_create_post(args: Dict[str, Any]) -> Dict[str, Any]:
    payload = PostCreate(**args)
    return create_post(payload)


def _h_update_post(args: Dict[str, Any]) -> Dict[str, Any]:
    cid = args["cid"]
    payload = PostUpdate(**{k: v for k, v in args.items() if k != "cid"})
    return update_post(cid, payload)


def _h_delete_post(args: Dict[str, Any]) -> Dict[str, Any]:
    ok = delete_post(args["cid"])
    return {"cid": args["cid"], "deleted": ok}


def _h_get_post(args: Dict[str, Any]) -> Dict[str, Any]:
    return get_post(args["cid"])


def _h_find_post_by_slug(args: Dict[str, Any]) -> Dict[str, Any]:
    post = find_post_by_slug(args["slug"])
    if not post:
        return {"found": False, "slug": args["slug"]}
    return {"found": True, "post": post}


def _h_list_posts(args: Dict[str, Any]) -> Dict[str, Any]:
    return list_posts(
        status=args.get("status"),
        keyword=args.get("keyword"),
        page=args.get("page", 1),
        page_size=args.get("page_size", 20),
    )


def _h_list_categories(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"items": list_categories()}


def _h_list_tags(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"items": list_tags()}


def _h_create_category(args: Dict[str, Any]) -> Dict[str, Any]:
    mid = create_meta(
        name=args["name"],
        mtype="category",
        slug=args.get("slug"),
        description=args.get("description", ""),
        parent=args.get("parent", 0),
    )
    return {"mid": mid, "name": args["name"]}


def _h_create_tag(args: Dict[str, Any]) -> Dict[str, Any]:
    mid = create_meta(name=args["name"], mtype="tag", slug=args.get("slug"))
    return {"mid": mid, "name": args["name"]}


def _h_delete_meta(args: Dict[str, Any]) -> Dict[str, Any]:
    ok = delete_meta(args["mid"])
    return {"mid": args["mid"], "deleted": ok}


def _h_upload_image_from_base64(args: Dict[str, Any]) -> Dict[str, Any]:
    return upload_base64(
        b64=args["base64_data"],
        filename=args.get("filename", "image.png"),
    )


def _h_upload_image_from_file(args: Dict[str, Any]) -> Dict[str, Any]:
    return upload_file(local_path=args["local_path"])


def _h_delete_cos_object(args: Dict[str, Any]) -> Dict[str, Any]:
    ok = cos_delete(args["key"])
    return {"key": args["key"], "deleted": ok}


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "create_post": _h_create_post,
    "update_post": _h_update_post,
    "delete_post": _h_delete_post,
    "get_post": _h_get_post,
    "find_post_by_slug": _h_find_post_by_slug,
    "list_posts": _h_list_posts,
    "list_categories": _h_list_categories,
    "list_tags": _h_list_tags,
    "create_category": _h_create_category,
    "create_tag": _h_create_tag,
    "delete_meta": _h_delete_meta,
    "upload_image_from_base64": _h_upload_image_from_base64,
    "upload_image_from_file": _h_upload_image_from_file,
    "delete_cos_object": _h_delete_cos_object,
}


# ============================================================
# Dispatcher
# ============================================================

class ToolDispatcher:
    """
    注册 + 调用工具。
    推荐用法：
        dispatcher = ToolDispatcher()
        tools_for_llm = dispatcher.schemas            # 喂给 LLM
        result = dispatcher.call("create_post", {...})  # 拿到 LLM 的 tool_call 后调用
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = dict(HANDLERS)

    def register(self, name: str, handler: Callable, schema: Optional[Dict[str, Any]] = None) -> None:
        self._handlers[name] = handler
        if schema is not None:
            TOOL_SCHEMAS.append(schema)

    @property
    def schemas(self) -> List[Dict[str, Any]]:
        return list(TOOL_SCHEMAS)

    def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._handlers:
            return {"error": f"unknown tool: {name}"}
        try:
            result = self._handlers[name](arguments or {})
            return {"ok": True, "result": result}
        except Exception as e:  # noqa: BLE001
            logger.exception("tool %s failed", name)
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # 兼容 OpenAI ChatCompletion 的 tool_calls 列表
    def handle_openai_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """
        接收 OpenAI ChatCompletion 返回的 message.tool_calls（类型为 list[ChoiceDeltaToolCall]），
        返回 messages 用的 tool 消息序列：
            [{"role": "tool", "tool_call_id": ..., "name": ..., "content": json.dumps(result)}]
        """
        out = []
        for tc in tool_calls:
            import json
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = self.call(tc.function.name, args)
            out.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
        return out
