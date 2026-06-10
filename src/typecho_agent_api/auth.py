"""
API Key 鉴权。

设计：API_KEYS 是一组预共享的 key（来自 .env）。
Agent 在请求头中带上  X-API-Key: <key>  即可通过鉴权。
key 之间使用常量时间比较，避免被计时攻击。
"""
from __future__ import annotations

import hmac
from typing import Optional

from .config import CONFIG


def is_valid_key(api_key: Optional[str]) -> bool:
    if not api_key:
        return False
    valid = CONFIG.api_keys
    return any(hmac.compare_digest(api_key, k) for k in valid if k)
