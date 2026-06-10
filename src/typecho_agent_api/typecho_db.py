"""
数据库连接 & 通用 CRUD 工具。

Typecho 的表结构要点（见 install/Mysql.sql）：
- typecho_contents : 文章/页面/附件主表
- typecho_metas    : 分类(category) + 标签(tag) 表
- typecho_relationships : contents <-> metas 多对多
- typecho_users    : 用户
- typecho_fields   : 文章自定义字段
- typecho_options  : 站点设置

由于我们要直接接管 PHP 后台的“新增/编辑/删除文章”逻辑，
最简单可靠的方式是直连 MySQL，按照 typecho 的规则写入。
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pymysql
from dbutils.pooled_db import PooledDB

from .config import CONFIG

logger = logging.getLogger(__name__)

# 全局连接池
_POOL: Optional[PooledDB] = None


def get_pool() -> PooledDB:
    global _POOL
    if _POOL is None:
        cfg = CONFIG.typecho
        _POOL = PooledDB(
            creator=pymysql,
            mincached=1,
            maxcached=5,
            maxconnections=10,
            blocking=True,
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        logger.info("MySQL pool initialized for %s@%s/%s", cfg.user, cfg.host, cfg.database)
    return _POOL


@contextmanager
def get_conn():
    """获取连接，with 退出时自动 commit/rollback。"""
    conn = get_pool().connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()  # 实际是归还到池


# ---------- 通用查询工具 ----------

def _format_in(seq: Sequence[Any]) -> str:
    return ",".join(["%s"] * len(seq))


def _q(name: str) -> str:
    """表名加反引号，例如 _q('contents') -> `typecho_contents`。"""
    return f"`{CONFIG.typecho.table(name)}`"


def insert(conn, table: str, rows: Dict[str, Any]) -> int:
    """INSERT 一行，返回自增 id。"""
    cols = list(rows.keys())
    sql = f"INSERT INTO {_q(table)} ({','.join('`'+c+'`' for c in cols)}) VALUES ({_format_in(cols)})"
    with conn.cursor() as cur:
        cur.execute(sql, [rows[c] for c in cols])
        return cur.lastrowid


def update(conn, table: str, rows: Dict[str, Any], where: str, where_args: Sequence[Any]) -> int:
    """UPDATE，返回受影响行数。"""
    if not rows:
        return 0
    set_sql = ",".join(f"`{k}`=%s" for k in rows.keys())
    sql = f"UPDATE {_q(table)} SET {set_sql} WHERE {where}"
    with conn.cursor() as cur:
        return cur.execute(sql, list(rows.values()) + list(where_args))


def delete(conn, table: str, where: str, where_args: Sequence[Any]) -> int:
    sql = f"DELETE FROM {_q(table)} WHERE {where}"
    with conn.cursor() as cur:
        return cur.execute(sql, list(where_args))


def select_one(conn, table: str, where: str, where_args: Sequence[Any]) -> Optional[Dict[str, Any]]:
    sql = f"SELECT * FROM {_q(table)} WHERE {where} LIMIT 1"
    with conn.cursor() as cur:
        cur.execute(sql, list(where_args))
        return cur.fetchone()


def select_all(conn, table: str, where: str = "1=1", where_args: Sequence[Any] = (),
               order_by: str = "", limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
    sql = f"SELECT * FROM {_q(table)} WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit > 0:
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    with conn.cursor() as cur:
        cur.execute(sql, list(where_args))
        return list(cur.fetchall())


def now_ts() -> int:
    return int(time.time())
