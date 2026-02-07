"""MCP client wrapper for invoking tools on marketplace MCP servers."""

from __future__ import annotations

import json
from typing import Any

from agent_marketplace.mcp.registry import _build_connection


class MarketplaceMCPClient:
    """Async context manager wrapping MultiServerMCPClient for marketplace ops.

    As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient is no longer
    a context manager — just construct and call ``get_tools()``.
    """

    def __init__(self, registry: dict[str, Any]) -> None:
        self._registry = registry
        self._client = None

    async def __aenter__(self) -> MarketplaceMCPClient:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        # Build a combined connection dict for all servers
        connections: dict[str, Any] = {}
        for server_key, cfg in self._registry.items():
            conn = _build_connection(server_key, cfg)
            connections.update(conn)

        self._client = MultiServerMCPClient(connections)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._client = None

    async def _get_tool(self, server_key: str, tool_name: str) -> Any:
        """Find a tool by name from a specific server's tool set."""
        tools = await self._client.get_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        raise ValueError(f"Tool '{tool_name}' not found for server '{server_key}'")

    async def call_bid(
        self,
        server_key: str,
        job_description: str,
        job_budget_xpl: float,
        job_type: str,
    ) -> dict[str, Any]:
        """Invoke the ``bid`` tool on a specific MCP server."""
        tool = await self._get_tool(server_key, "bid")
        result = await tool.ainvoke({
            "job_description": job_description,
            "job_budget_xpl": job_budget_xpl,
            "job_type": job_type,
        })
        return json.loads(result)

    async def call_execute_task(
        self,
        server_key: str,
        job_description: str,
        job_type: str,
    ) -> str:
        """Invoke the ``execute_task`` tool on a specific MCP server."""
        tool = await self._get_tool(server_key, "execute_task")
        return await tool.ainvoke({
            "job_description": job_description,
            "job_type": job_type,
        })
