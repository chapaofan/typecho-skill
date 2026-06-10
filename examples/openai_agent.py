"""
完整示例：用 OpenAI 官方 SDK 让 LLM 自主决定调用本项目的工具。

依赖：pip install -e .   （先在项目根目录安装本 package）
      pip install openai
运行：
    export OPENAI_API_KEY=sk-...
    python examples/openai_agent.py
"""
import json
import os

from typecho_agent_api import ToolDispatcher
from typecho_agent_api.config import CONFIG


def main():
    try:
        from openai import OpenAI
    except ImportError:
        print("请先 pip install openai")
        return

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    dispatcher = ToolDispatcher()

    system_prompt = (
        "你是一个博客运营 Agent。\n"
        "你可以使用列出的工具来：\n"
        "  - 在用户的 Typecho 博客上增删改文章\n"
        "  - 通过腾讯云 COS 上传图片\n"
        "调用工具后请用中文简短地告诉用户结果。"
    )

    user_input = "帮我发一篇关于 Python 装饰器的入门教程，标签加 Python、教程、装饰器。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    # 第一轮：让 LLM 决定调哪些工具
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=dispatcher.schemas,
        tool_choice="auto",
    )
    msg = response.choices[0].message
    messages.append(msg)

    if not msg.tool_calls:
        print("LLM 没调用工具:", msg.content)
        return

    # 第二轮：执行工具
    tool_msgs = dispatcher.handle_openai_tool_calls(msg.tool_calls)
    messages.extend(tool_msgs)

    # 第三轮：把工具结果回喂给 LLM 让它生成最终回复
    final = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=dispatcher.schemas,
    )
    print(final.choices[0].message.content)


if __name__ == "__main__":
    main()
