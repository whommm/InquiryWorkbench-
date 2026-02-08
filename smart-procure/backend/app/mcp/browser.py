"""
浏览器 MCP 客户端 - 支持迭代式浏览器自动化

提供会话管理和多步浏览器操作能力，让 Agent 能够像人类一样操作浏览器。
"""

import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .client import MCPClient

logger = logging.getLogger(__name__)

# 线程池用于同步调用
_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class BrowserSession:
    """浏览器会话，保持状态用于迭代操作"""
    session_id: str
    client: Optional[MCPClient] = None
    is_active: bool = False
    current_url: str = ""
    page_snapshot: str = ""
    created_at: float = field(default_factory=time.time)
    last_action_at: float = field(default_factory=time.time)


class BrowserMCPManager:
    """
    浏览器 MCP 管理器

    管理浏览器会话，支持迭代式操作。
    """

    # 会话超时时间（秒）
    SESSION_TIMEOUT = 300

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._available = False
        self._session_counter = 0
        self._check_availability()

    def _check_availability(self):
        """检查 MCP 服务器是否可用"""
        if shutil.which("npx"):
            self._available = True
            logger.info("Browser MCP: npx available")
        else:
            logger.warning("Browser MCP: npx not found")

    @property
    def available(self) -> bool:
        return self._available

    def _generate_session_id(self) -> str:
        """生成会话 ID"""
        self._session_counter += 1
        return f"browser_{self._session_counter}_{int(time.time())}"

    def _cleanup_expired_sessions(self):
        """清理过期会话"""
        now = time.time()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.last_action_at > self.SESSION_TIMEOUT
        ]
        for sid in expired:
            self.close_session(sid)

    def create_session(self) -> Dict[str, Any]:
        """创建新的浏览器会话"""
        if not self._available:
            return {"success": False, "error": "MCP not available"}

        self._cleanup_expired_sessions()

        try:
            session_id = self._generate_session_id()
            client = MCPClient(
                server_command=["npx", "@playwright/mcp@latest"],
                env={**os.environ, "PLAYWRIGHT_HEADLESS": "true"}
            )

            if not client.start():
                return {"success": False, "error": "Failed to start MCP server"}

            session = BrowserSession(
                session_id=session_id,
                client=client,
                is_active=True
            )
            self._sessions[session_id] = session

            logger.info(f"Browser session created: {session_id}")
            return {"success": True, "session_id": session_id}

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return {"success": False, "error": str(e)}

    def close_session(self, session_id: str) -> Dict[str, Any]:
        """关闭浏览器会话"""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}

        try:
            if session.client:
                session.client.stop()
            del self._sessions[session_id]
            logger.info(f"Browser session closed: {session_id}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_session(self, session_id: str) -> Optional[BrowserSession]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session and session.is_active:
            session.last_action_at = time.time()
            return session
        return None

    # ========== 浏览器操作方法 ==========

    def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        """导航到指定 URL"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_navigate", {"url": url})
            if result.success:
                session.current_url = url
                return {"success": True, "url": url, "message": f"已导航到 {url}"}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click(self, session_id: str, element: str) -> Dict[str, Any]:
        """点击页面元素"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_click", {"element": element})
            if result.success:
                return {"success": True, "message": f"已点击: {element}"}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type_text(self, session_id: str, element: str, text: str) -> Dict[str, Any]:
        """在元素中输入文本"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_type", {
                "element": element,
                "text": text
            })
            if result.success:
                return {"success": True, "message": f"已输入: {text}"}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        """获取当前页面快照"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_snapshot", {})
            if result.success:
                session.page_snapshot = result.content
                return {
                    "success": True,
                    "url": session.current_url,
                    "content": result.content[:8000] if result.content else ""
                }
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scroll(self, session_id: str, direction: str = "down") -> Dict[str, Any]:
        """滚动页面"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_scroll", {"direction": direction})
            if result.success:
                return {"success": True, "message": f"已滚动: {direction}"}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def go_back(self, session_id: str) -> Dict[str, Any]:
        """返回上一页"""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Invalid session"}

        try:
            result = session.client.call_tool("browser_back", {})
            if result.success:
                return {"success": True, "message": "已返回上一页"}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ========== 全局单例和便捷接口 ==========

_browser_manager: Optional[BrowserMCPManager] = None


def get_browser_manager() -> BrowserMCPManager:
    """获取浏览器管理器单例"""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserMCPManager()
    return _browser_manager


def browser_create_session() -> Dict[str, Any]:
    """创建浏览器会话"""
    def _run():
        return get_browser_manager().create_session()
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_close_session(session_id: str) -> Dict[str, Any]:
    """关闭浏览器会话"""
    def _run():
        return get_browser_manager().close_session(session_id)
    future = _executor.submit(_run)
    return future.result(timeout=10)


def browser_navigate(session_id: str, url: str) -> Dict[str, Any]:
    """导航到 URL"""
    def _run():
        return get_browser_manager().navigate(session_id, url)
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_click(session_id: str, element: str) -> Dict[str, Any]:
    """点击元素"""
    def _run():
        return get_browser_manager().click(session_id, element)
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_type(session_id: str, element: str, text: str) -> Dict[str, Any]:
    """输入文本"""
    def _run():
        return get_browser_manager().type_text(session_id, element, text)
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_snapshot(session_id: str) -> Dict[str, Any]:
    """获取页面快照"""
    def _run():
        return get_browser_manager().snapshot(session_id)
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_scroll(session_id: str, direction: str = "down") -> Dict[str, Any]:
    """滚动页面"""
    def _run():
        return get_browser_manager().scroll(session_id, direction)
    future = _executor.submit(_run)
    return future.result(timeout=30)


def browser_back(session_id: str) -> Dict[str, Any]:
    """返回上一页"""
    def _run():
        return get_browser_manager().go_back(session_id)
    future = _executor.submit(_run)
    return future.result(timeout=30)
