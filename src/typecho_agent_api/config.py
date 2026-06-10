"""
集中加载配置。所有模块都从这里读配置，禁止直接读 os.environ。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return val if val is not None and val != "" else default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_list(name: str, default: List[str] = None) -> List[str]:
    raw = _get(name)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class TypechoConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = "typecho"
    charset: str = "utf8mb4"
    table_prefix: str = "typecho_"
    default_author_id: int = 1
    default_category_id: int = 1

    def table(self, name: str) -> str:
        """返回带前缀的表名，例如 table('contents') -> 'typecho_contents'。"""
        return f"{self.table_prefix}{name}"


@dataclass
class CosConfig:
    secret_id: str = ""
    secret_key: str = ""
    region: str = "ap-guangzhou"
    bucket: str = ""
    scheme: str = "https"
    key_prefix: str = "blog/"
    cdn_domain: str = ""


@dataclass
class AppConfig:
    api_keys: List[str] = field(default_factory=list)
    allowed_origins: List[str] = field(default_factory=list)
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    http_debug: bool = False
    typecho: TypechoConfig = field(default_factory=TypechoConfig)
    cos: CosConfig = field(default_factory=CosConfig)


def load_config() -> AppConfig:
    return AppConfig(
        api_keys=_get_list("API_KEYS", []),
        allowed_origins=_get_list("ALLOWED_ORIGINS", ["*"]),
        http_host=_get("HTTP_HOST", "0.0.0.0"),
        http_port=_get_int("HTTP_PORT", 8000),
        http_debug=_get("HTTP_DEBUG", "false").lower() in ("1", "true", "yes"),
        typecho=TypechoConfig(
            host=_get("TYPECHO_DB_HOST", "localhost"),
            port=_get_int("TYPECHO_DB_PORT", 3306),
            user=_get("TYPECHO_DB_USER"),
            password=_get("TYPECHO_DB_PASSWORD"),
            database=_get("TYPECHO_DB_NAME", "typecho"),
            charset=_get("TYPECHO_DB_CHARSET", "utf8mb4"),
            table_prefix=_get("TYPECHO_TABLE_PREFIX", "typecho_"),
            default_author_id=_get_int("TYPECHO_DEFAULT_AUTHOR_ID", 1),
            default_category_id=_get_int("TYPECHO_DEFAULT_CATEGORY_ID", 1),
        ),
        cos=CosConfig(
            secret_id=_get("COS_SECRET_ID"),
            secret_key=_get("COS_SECRET_KEY"),
            region=_get("COS_REGION", "ap-guangzhou"),
            bucket=_get("COS_BUCKET"),
            scheme=_get("COS_SCHEME", "https"),
            key_prefix=_get("COS_KEY_PREFIX", "blog/"),
            cdn_domain=_get("COS_CDN_DOMAIN"),
        ),
    )


CONFIG: AppConfig = load_config()
