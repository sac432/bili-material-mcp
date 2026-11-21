"""Read-only, token-efficient Bilibili material source.

The core API lives in :mod:`bili_material.service` and returns plain dicts, so it
can be imported directly by pipeline nodes. :mod:`bili_material.mcp_server` is a
thin MCP shell that renders those dicts as compact text.

This package intentionally exposes no write operations (commenting, replying,
messaging, liking, uploading, following).
"""

from .service import BiliMaterial

__all__ = ["BiliMaterial"]
__version__ = "0.1.0"
