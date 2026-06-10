"""
示例：通过 HTTP 调用本项目提供的 FastAPI 服务。

启动服务：
    uvicorn server:app --host 0.0.0.0 --port 8000

运行：
    export TYPECHO_API_BASE=http://localhost:8000
    export TYPECHO_API_KEY=sk-please-change-me-1
    python examples/http_client.py
"""
import json
import os
import sys
import urllib.request
import urllib.error


def _request(method: str, path: str, body=None):
    base = os.environ.get("TYPECHO_API_BASE", "http://localhost:8000")
    key = os.environ.get("TYPECHO_API_KEY", "sk-please-change-me-1")
    url = base.rstrip("/") + path
    data = None
    headers = {"X-API-Key": key}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    # 列出工具
    code, body = _request("GET", "/v1/tools")
    print("list tools:", code, json.dumps(body, ensure_ascii=False)[:200])

    # 创建一篇文章
    code, body = _request("POST", "/v1/posts", {
        "title": "HTTP 客户端测试文章",
        "content": "<p>这是通过 HTTP 客户端创建的文章。</p>",
        "tags": ["测试", "HTTP"],
        "status": "publish",
    })
    print("create post:", code, json.dumps(body, ensure_ascii=False)[:300])

    # 列出文章
    code, body = _request("GET", "/v1/posts?page=1&page_size=5")
    print("list posts:", code, json.dumps(body, ensure_ascii=False)[:200])


if __name__ == "__main__":
    main()
