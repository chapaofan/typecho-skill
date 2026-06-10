"""
宝塔面板 / 通用 Python 部署入口脚本。

宝塔面板"基础版"的 Python 项目管理器没有 uvicorn 选项，所以走最稳的
`启动方式 = python` + `运行文件 = run.py` 路线：本脚本在 __main__ 分支
里直接启 uvicorn 加载 typecho_agent_api.server:app。

如果以后宝塔版本支持 uvicorn 启动方式，或者想切到 gunicorn + uvicorn worker，
本脚本顶层导出的 `app` 也可以直接被 `uvicorn run:app` 或
`gunicorn -k uvicorn.workers.UvicornWorker run:app` 使用。

使用：
    # 部署前先安装（推荐 editable，方便改代码后重启生效）
    pip install -e .

    # 手动起一次确认无误
    python run.py

    # 宝塔里就这样填：
    #   框架     = python
    #   启动方式 = python
    #   运行文件 = run.py
    #   端口     = .env 里的 HTTP_PORT（默认 8000）
"""
from __future__ import annotations

import uvicorn

from typecho_agent_api.config import CONFIG
from typecho_agent_api.server import app  # 暴露给 uvicorn/gunicorn run:app 用

__all__ = ["app"]


def main() -> None:
    uvicorn.run(
        "typecho_agent_api.server:app",
        host=CONFIG.http_host,
        port=CONFIG.http_port,
        reload=CONFIG.http_debug,
    )


if __name__ == "__main__":
    main()
