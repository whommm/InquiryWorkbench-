"""
MCP 客户端基础类

提供与 MCP 服务器通信的基础能力，支持 stdio 和 SSE 传输方式。
"""

import asyncio
import json
import logging
import subprocess
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """MCP 工具调用结果"""
    success: bool
    content: Any = None
    error: Optional[str] = None


class MCPClient:
    """
    MCP 客户端基础类

    支持通过 stdio 方式与 MCP 服务器通信
    """

    def __init__(self, server_command: List[str], env: Optional[Dict[str, str]] = None):
        """
        初始化 MCP 客户端

        Args:
            server_command: 启动 MCP 服务器的命令，如 ["npx", "@playwright/mcp"]
            env: 环境变量
        """
        self.server_command = server_command
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._tools: List[MCPTool] = []
        self._initialized = False

    def _next_id(self) -> int:
        """生成下一个请求 ID"""
        self._request_id += 1
        return self._request_id

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """
        发送 JSON-RPC 请求并等待响应

        Args:
            method: 方法名
            params: 参数

        Returns:
            响应结果
        """
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP server is not running")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            request["params"] = params

        request_str = json.dumps(request) + "\n"
        self.process.stdin.write(request_str)
        self.process.stdin.flush()

        # 读取响应
        response_line = self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("No response from MCP server")

        response = json.loads(response_line)

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})

    def start(self) -> bool:
        """启动 MCP 服务器"""
        try:
            self.process = subprocess.Popen(
                self.server_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
                bufsize=1,
            )

            # 初始化连接
            self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smart-procure", "version": "1.0.0"}
            })

            # 发送 initialized 通知
            self.process.stdin.write(json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }) + "\n")
            self.process.stdin.flush()

            self._initialized = True
            logger.info(f"MCP server started: {' '.join(self.server_command)}")
            return True

        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            return False

    def stop(self):
        """停止 MCP 服务器"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
            self._initialized = False
            logger.info("MCP server stopped")

    def list_tools(self) -> List[MCPTool]:
        """获取可用工具列表"""
        if not self._initialized:
            return []

        try:
            result = self._send_request("tools/list")
            tools = result.get("tools", [])
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {})
                )
                for t in tools
            ]
            return self._tools
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """
        调用 MCP 工具

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果
        """
        if not self._initialized:
            return MCPToolResult(success=False, error="MCP client not initialized")

        try:
            result = self._send_request("tools/call", {
                "name": name,
                "arguments": arguments
            })

            content = result.get("content", [])
            # 提取文本内容
            text_content = []
            for item in content:
                if item.get("type") == "text":
                    text_content.append(item.get("text", ""))

            return MCPToolResult(
                success=True,
                content="\n".join(text_content) if text_content else content
            )

        except Exception as e:
            logger.error(f"Failed to call tool {name}: {e}")
            return MCPToolResult(success=False, error=str(e))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
