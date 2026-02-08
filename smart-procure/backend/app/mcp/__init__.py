"""
MCP (Model Context Protocol) 服务模块

提供与外部 MCP 服务器的集成能力，包括浏览器自动化等功能。
"""

from .client import MCPClient
from .browser import (
    BrowserMCPManager,
    get_browser_manager,
    browser_create_session,
    browser_close_session,
    browser_navigate,
    browser_click,
    browser_type,
    browser_snapshot,
    browser_scroll,
    browser_back,
)

__all__ = [
    "MCPClient",
    "BrowserMCPManager",
    "get_browser_manager",
    "browser_create_session",
    "browser_close_session",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_snapshot",
    "browser_scroll",
    "browser_back",
]
