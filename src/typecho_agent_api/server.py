"""
Flask 服务。
所有写接口要求  X-API-Key  头。Agent 可以通过 HTTP 调用各种工具。

启动：
    pip install -e .
    cp .env.example .env  # 改成你的配置
    python run.py
    # 或者 gunicorn: gunicorn 'typecho_agent_api.server:app'
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

from .agent_tools import ToolDispatcher
from .auth import is_valid_key
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
from .cos_uploader import delete as cos_delete, upload_base64

logger = logging.getLogger("typecho_agent_api")
logging.basicConfig(
    level=logging.DEBUG if CONFIG.http_debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = Flask(__name__)
dispatcher = ToolDispatcher()


# ============================================================
# API Key 鉴权 —— before_request hook
# ============================================================
@app.before_request
def _check_api_key():
    # /healthz 免鉴权
    if request.path == "/healthz":
        return None

    if not CONFIG.api_keys:
        return jsonify({"ok": False, "error": "server not configured with any API key"}), 503

    api_key = request.headers.get("X-API-Key")
    if not is_valid_key(api_key):
        return jsonify({"ok": False, "error": "invalid or missing X-API-Key"}), 401
    return None


# ============================================================
# 健康检查
# ============================================================
@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


# ============================================================
# Tool Discovery
# ============================================================
@app.route("/v1/tools")
def list_tools():
    return jsonify({"tools": dispatcher.schemas})


# ============================================================
# 通用 Tool Call
# ============================================================
@app.route("/v1/tools/call", methods=["POST"])
def call_tool():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(dispatcher.call(body.get("name"), body.get("arguments") or {}))


class _OpenAIToolCallAdapter:
    """把 dict 形态的 tool_call 适配成 dispatcher 期待的接口。"""
    def __init__(self, d: Dict[str, Any]) -> None:
        self.id = d.get("id", "")
        fn = d.get("function", {}) or {}
        self.function = type("_FN", (), {
            "name": fn.get("name", ""),
            "arguments": fn.get("arguments", "{}"),
        })()


@app.route("/v1/tools/call_openai", methods=["POST"])
def call_tool_openai():
    body = request.get_json(force=True, silent=True) or {}
    tcs = [_OpenAIToolCallAdapter(d) for d in body.get("tool_calls", [])]
    return jsonify(dispatcher.handle_openai_tool_calls(tcs))


# ============================================================
# 文章 REST
# ============================================================
@app.route("/v1/posts", methods=["POST"])
def api_create_post():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(create_post(PostCreate(**body)))


@app.route("/v1/posts", methods=["GET"])
def api_list_posts():
    def _int_arg(name: str, default: int) -> int:
        raw = request.args.get(name)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{name} must be an integer, got {raw!r}")

    try:
        page = _int_arg("page", 1)
        page_size = _int_arg("page_size", 20)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    return jsonify(list_posts(
        status=request.args.get("status"),
        keyword=request.args.get("keyword"),
        page=page,
        page_size=page_size,
    ))


@app.route("/v1/posts/<int:cid>", methods=["GET"])
def api_get_post(cid: int):
    try:
        return jsonify(get_post(cid))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.route("/v1/posts/<int:cid>", methods=["PATCH"])
def api_update_post(cid: int):
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(update_post(cid, PostUpdate(**body)))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.route("/v1/posts/<int:cid>", methods=["DELETE"])
def api_delete_post(cid: int):
    ok = delete_post(cid)
    if not ok:
        return jsonify({"ok": False, "error": f"post not found: {cid}"}), 404
    return jsonify({"cid": cid, "deleted": True})


@app.route("/v1/posts/by-slug/<slug>", methods=["GET"])
def api_find_post_by_slug(slug: str):
    post = find_post_by_slug(slug)
    if not post:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(post)


# ============================================================
# COS 图片上传
# ============================================================
@app.route("/v1/images/upload", methods=["POST"])
def api_upload_image():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "no file"}), 400
    data = f.read()
    return jsonify(upload_base64(
        b64=base64.b64encode(data).decode(),
        filename=f.filename or "image.png",
        content_type=f.content_type,
    ))


@app.route("/v1/images/upload_base64", methods=["POST"])
def api_upload_image_base64():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(upload_base64(
        b64=body.get("base64_data", ""),
        filename=body.get("filename", "image.png"),
    ))


@app.route("/v1/images/<path:key>", methods=["DELETE"])
def api_delete_image(key: str):
    ok = cos_delete(key)
    return jsonify({"key": key, "deleted": ok})


# ============================================================
# 全局错误兜底
# ============================================================
@app.errorhandler(Exception)
def _on_exception(e: Exception):
    # 完整 traceback 写日志，HTTP 响应里不返内部细节（表名/路径/SQL）。
    # 调试时（HTTP_DEBUG=true）才把异常原文返出来方便排查。
    logger.exception("unhandled error: %s %s", request.method, request.path)
    if CONFIG.http_debug:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500
    return jsonify({"ok": False, "error": "internal server error"}), 500


def main() -> None:
    """Flask 内置开发服务器。生产建议：gunicorn typecho_agent_api.server:app -w 2 -b 0.0.0.0:8000"""
    app.run(
        host=CONFIG.http_host,
        port=CONFIG.http_port,
        debug=CONFIG.http_debug,
        use_reloader=CONFIG.http_debug,
    )


if __name__ == "__main__":
    main()
