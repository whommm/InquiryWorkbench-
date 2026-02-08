"""
MCP 服务配置

管理 MCP 服务器的配置信息。
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


# 默认 MCP 服务器配置
DEFAULT_MCP_SERVERS: Dict[str, MCPServerConfig] = {
    "playwright": MCPServerConfig(
        name="playwright",
        command=["npx", "@playwright/mcp@latest"],
        env={"PLAYWRIGHT_HEADLESS": "true"},
        enabled=True,
    ),
}


def get_mcp_config(name: str) -> Optional[MCPServerConfig]:
    """获取 MCP 服务器配置"""
    return DEFAULT_MCP_SERVERS.get(name)


def is_mcp_enabled(name: str) -> bool:
    """检查 MCP 服务器是否启用"""
    config = get_mcp_config(name)
    return config is not None and config.enabled
