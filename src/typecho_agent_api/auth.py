"""
API Key 鉴权。

设计：
- API_KEYS 是一组预共享的 key（来自 .env）。
- Agent 在请求头中带上  X-API-Key: <key>  即可通过鉴权。
- key 之间使用常量时间比较，避免被计时攻击。
- 还提供一个可选的轻量级签名方案：X-Signature = sha256( timestamp + method + path + body )，
  用于在 key 泄漏后仍能保留一定追溯能力（不是必须启用）。
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from .config import CONFIG


@dataclass
class AuthContext:
    api_key: str
    request_id: str


def is_valid_key(api_key: Optional[str]) -> bool:
    if not api_key:
        return False
    valid = CONFIG.api_keys
    return any(hmac.compare_digest(api_key, k) for k in valid if k)


def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    """
    FastAPI 依赖：要求请求头中带合法的 API Key。
    """
    if not CONFIG.api_keys:
        # 未配置 key 时直接拒绝，避免误开放
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="server not configured with any API key",
        )
    if not is_valid_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
    return AuthContext(api_key=x_api_key, request_id=hashlib.md5(
        f"{x_api_key}-{time.time_ns()}".encode()
    ).hexdigest()[:12])


# 可选签名校验（默认未启用）
def verify_signature(
    method: str,
    path: str,
    body: bytes,
    timestamp: str,
    signature: str,
    api_key: str,
    tolerance_seconds: int = 300,
) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False
    payload = f"{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    digest = hmac.new(api_key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)
