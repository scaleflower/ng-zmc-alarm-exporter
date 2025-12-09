"""
API 路由模块
"""

from app.api import health, metrics, sync, admin

__all__ = ["health", "metrics", "sync", "admin"]
