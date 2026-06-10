"""
部署入口脚本。

宝塔里：
    框架     = python  （或 Flask —— Flask 是 WSGI，gunicorn 也能跑）
    启动方式 = python
    运行文件 = run.py

本脚本同时把 app 暴露在模块层，方便以后切到 gunicorn：
    gunicorn -w 2 -b 0.0.0.0:8000 run:app
"""
from typecho_agent_api.config import CONFIG
from typecho_agent_api.server import app  # 暴露给 gunicorn run:app 用

__all__ = ["app"]


if __name__ == "__main__":
    app.run(
        host=CONFIG.http_host,
        port=CONFIG.http_port,
        debug=CONFIG.http_debug,
        use_reloader=CONFIG.http_debug,
    )
