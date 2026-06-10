"""
示例：把本项目作为「工具库」直接给 Agent / LLM SDK 用。

依赖：pip install -e .   （先在项目根目录安装本 package）
      pip install openai
运行：python examples/agent_usage.py
"""
import json
import os

from typecho_agent_api import ToolDispatcher
from typecho_agent_api.config import CONFIG


def main():
    dispatcher = ToolDispatcher()
    tools = dispatcher.schemas
    print(f"已注册 {len(tools)} 个工具：")
    for t in tools:
        print(f"  - {t['function']['name']}")
    print()

    # 1) 直接调用工具
    print("=== demo 1: list_categories ===")
    res = dispatcher.call("list_categories", {})
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print()

    # 2) 模拟 OpenAI ChatCompletion 的工具调用
    print("=== demo 2: 模拟 OpenAI tool_calls ===")
    fake_tool_calls = [
        type("TC", (), {
            "id": "call_001",
            "function": type("FN", (), {
                "name": "create_post",
                "arguments": json.dumps({
                    "title": "测试文章 - Agent 创建",
                    "content": "<p>这是正文</p>",
                    "tags": ["测试", "Agent"],
                    "status": "publish",
                }),
            })(),
        })(),
    ]
    msgs = dispatcher.handle_openai_tool_calls(fake_tool_calls)
    for m in msgs:
        print(f"[{m['role']}] {m['name']} => {m['content'][:200]}")


if __name__ == "__main__":
    main()
