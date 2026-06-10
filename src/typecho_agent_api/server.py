"""
FastAPI 服务。
所有写操作要求  X-API-Key  头。Agent 可以通过 HTTP 调用各种工具。

启动：
    pip install -r requirements.txt
    cp .env.example .env  # 改成你的配置
    uvicorn server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .agent_tools import ToolDispatcher
from .auth import AuthContext, require_api_key
from .config import CONFIG
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
from .cos_uploader import delete as cos_delete, upload_base64, upload_file

logger = logging.getLogger("typecho_agent_api")
logging.basicConfig(
    level=logging.DEBUG if CONFIG.http_debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Typecho Agent API",
    description="为 LLM Agent 提供 Typecho 博客增删改文章 + 腾讯云 COS 图片上传能力",
    version="1.0.0",
)
dispatcher = ToolDispatcher()


@app.get("/healthz", include_in_schema=False)
def healthz() -> Dict[str, Any]:
    return {"status": "ok"}


# ============================================================
# Tool Discovery — 列出所有可用工具
# ============================================================
@app.get("/v1/tools", summary="列出所有可用工具（OpenAI function 格式）")
def list_tools(_: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    return {"tools": dispatcher.schemas}


# ============================================================
# Generic Tool Call — Agent 把 tool_call 转发过来
# ============================================================
class ToolCallBody(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


@app.post("/v1/tools/call", summary="调用任意工具")
def call_tool(body: ToolCallBody, _: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    return dispatcher.call(body.name, body.arguments)


# 兼容 OpenAI ChatCompletion 风格的 tool_calls
class OpenAIToolCallsBody(BaseModel):
    tool_calls: List[Dict[str, Any]]


@app.post("/v1/tools/call_openai", summary="调用 OpenAI 风格的 tool_calls 列表")
def call_tool_openai(
    body: OpenAIToolCallsBody,
    _: AuthContext = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    # 把 dict 转成有 .function / .id 属性的对象（仅取所需字段）
    class _TC:
        def __init__(self, d: Dict[str, Any]) -> None:
            self.id = d.get("id", "")
            fn = d.get("function", {}) or {}
            self.function = type("_FN", (), {
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "{}"),
            })()
    tcs = [_TC(d) for d in body.tool_calls]
    return dispatcher.handle_openai_tool_calls(tcs)


# ============================================================
# REST 接口 —— 显式语义，方便非 LLM 调用
# ============================================================
@app.post("/v1/posts", summary="新增文章")
def api_create_post(
    body: PostCreate,
    _: AuthContext = Depends(require_api_key),
) -> Dict[str, Any]:
    return create_post(body)


@app.get("/v1/posts/{cid}", summary="获取文章")
def api_get_post(cid: int, _: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    try:
        return get_post(cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch("/v1/posts/{cid}", summary="更新文章")
def api_update_post(
    cid: int,
    body: PostUpdate,
    _: AuthContext = Depends(require_api_key),
) -> Dict[str, Any]:
    try:
        return update_post(cid, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/v1/posts/{cid}", summary="删除文章")
def api_delete_post(cid: int, _: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    ok = delete_post(cid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"post not found: {cid}")
    return {"cid": cid, "deleted": True}


@app.get("/v1/posts", summary="列出文章")
def api_list_posts(
    status_: Optional[str] = Query(default=None, alias="status"),
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    _: AuthContext = Depends(require_api_key),
) -> Dict[str, Any]:
    return list_posts(status=status_, keyword=keyword, page=page, page_size=page_size)


@app.get("/v1/posts/by-slug/{slug}", summary="按 slug 查找文章")
def api_find_post_by_slug(slug: str, _: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    post = find_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="not found")
    return post


# ============================================================
# COS 图片上传
# ============================================================
@app.post("/v1/images/upload", summary="上传图片（multipart）")
async def api_upload_image(
    file: UploadFile = File(...),
    _: AuthContext = Depends(require_api_key),
) -> Dict[str, Any]:
    data = await file.read()
    return upload_base64(
        b64=__import__("base64").b64encode(data).decode(),
        filename=file.filename or "image.png",
        content_type=file.content_type,
    )


class Base64UploadBody(BaseModel):
    base64_data: str
    filename: str = "image.png"


@app.post("/v1/images/upload_base64", summary="上传图片（base64）")
def api_upload_image_base64(
    body: Base64UploadBody,
    _: AuthContext = Depends(require_api_key),
) -> Dict[str, Any]:
    return upload_base64(b64=body.base64_data, filename=body.filename)


@app.delete("/v1/images/{key:path}", summary="删除 COS 对象")
def api_delete_image(key: str, _: AuthContext = Depends(require_api_key)) -> Dict[str, Any]:
    ok = cos_delete(key)
    return {"key": key, "deleted": ok}


# ============================================================
# 错误处理
# ============================================================
@app.exception_handler(Exception)
def _on_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"ok": False, "error": f"{type(exc).__name__}: {exc}"},
    )


def main() -> None:
    import uvicorn
    uvicorn.run(
        "typecho_agent_api.server:app",
        host=CONFIG.http_host,
        port=CONFIG.http_port,
        reload=CONFIG.http_debug,
    )


if __name__ == "__main__":
    main()
