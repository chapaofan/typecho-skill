"""
最小烟雾测试 —— 不连接真实数据库 / COS，只验证：
1. 包能 import
2. ToolDispatcher 能实例化并暴露 14 个工具 schema
3. 14 个工具 schema 都是合法 JSON Schema 对象
"""
from __future__ import annotations

import pytest


def test_package_imports():
    """包级别的 re-export 应该都能 import 通。"""
    from typecho_agent_api import (
        TOOL_SCHEMAS,
        ToolDispatcher,
        create_post,
        delete_post,
        find_post_by_slug,
        get_post,
        is_valid_key,
        list_posts,
        update_post,
        upload_base64,
        upload_bytes,
        upload_file,
    )

    assert ToolDispatcher is not None
    assert callable(create_post)
    assert callable(is_valid_key)


def test_dispatcher_exposes_schemas():
    """ToolDispatcher 应当暴露 schemas 列表（OpenAI function-calling 格式）。"""
    from typecho_agent_api import ToolDispatcher

    d = ToolDispatcher()
    assert isinstance(d.schemas, list)
    # 14 个工具：5 文章 + 4 分类标签管理 + 3 元数据 + 3 图片（参见 README 表格）
    assert len(d.schemas) == 14, f"expected 14 tool schemas, got {len(d.schemas)}"

    # 每个 schema 都符合 OpenAI 风格
    for s in d.schemas:
        assert s.get("type") == "function"
        fn = s.get("function", {})
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"].get("type") == "object"


def test_expected_tool_names():
    """锁住工具名集合，未来加新工具时这里要更新。"""
    from typecho_agent_api import ToolDispatcher

    d = ToolDispatcher()
    names = {s["function"]["name"] for s in d.schemas}

    expected = {
        "create_post", "update_post", "delete_post",
        "get_post", "find_post_by_slug", "list_posts",
        "list_categories", "list_tags",
        "create_category", "create_tag",
        "delete_meta",
        "upload_image_from_base64", "upload_image_from_file",
        "delete_cos_object",
    }
    assert expected.issubset(names), f"missing tools: {expected - names}"


@pytest.mark.parametrize("bad_key", [None, "", "sk-wrong", "wrong-key"])
def test_is_valid_key_rejects_invalid(bad_key):
    """未配置 API_KEYS 时任何 key 都应被拒；这里只测空 config 场景下的兜底。"""
    from typecho_agent_api import is_valid_key
    from typecho_agent_api.config import CONFIG

    if not CONFIG.api_keys:
        assert is_valid_key(bad_key) is False
    # 若 config 里有真实 key，这里不强断言（不在 CI 里跑真实 key 校验）
