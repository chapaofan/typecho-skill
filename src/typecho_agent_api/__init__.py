"""
Typecho Agent API — 让 LLM Agent 直接控制 Typecho 博客。
"""
from .agent_tools import TOOL_SCHEMAS, ToolDispatcher
from .auth import is_valid_key
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
from .cos_uploader import (
    delete as cos_delete,
    upload_base64,
    upload_bytes,
    upload_file,
)

__all__ = [
    "TOOL_SCHEMAS",
    "ToolDispatcher",
    "is_valid_key",
    "PostCreate",
    "PostUpdate",
    "create_post",
    "update_post",
    "delete_post",
    "get_post",
    "find_post_by_slug",
    "list_posts",
    "upload_base64",
    "upload_bytes",
    "upload_file",
    "cos_delete",
]

__version__ = "1.0.0"
