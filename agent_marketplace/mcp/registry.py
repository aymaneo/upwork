"""MCP agent discovery — reads a local registry and probes each server."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_marketplace.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Required MCP tools every marketplace provider must expose
_REQUIRED_TOOLS = {"bid", "execute_task", "get_capabilities"}


def load_registry(path: Path | str) -> dict[str, Any]:
    """Read *mcp_servers.json* and return enabled server configs.

    Returns an empty dict if the file doesn't exist or is malformed.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("MCP registry not found at %s", path)
        return {}

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read MCP registry: %s", exc)
        return {}

    servers: dict[str, Any] = {}
    for key, cfg in data.get("servers", {}).items():
        if cfg.get("enabled", True):
            servers[key] = cfg
    return servers


async def discover_mcp_providers(
    registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Connect to each MCP server, validate required tools, return descriptors.

    Returns (providers, warnings) — warnings are surfaced in the events log.
    Unreachable or incompatible servers are skipped with a warning.
    """
    if not registry:
        return [], []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    providers: list[dict[str, Any]] = []
    warnings: list[str] = []

    for server_key, cfg in registry.items():
        try:
            connection = _build_connection(server_key, cfg)
            client = MultiServerMCPClient(connection)
            tools = await client.get_tools()
            tool_names = {t.name for t in tools}

            missing = _REQUIRED_TOOLS - tool_names
            if missing:
                msg = f"MCP server '{server_key}' missing tools: {missing} — skipped"
                logger.warning(msg)
                warnings.append(f"[DISCOVERY] {msg}")
                continue

            # Call get_capabilities to learn about the provider
            caps_tool = next(t for t in tools if t.name == "get_capabilities")
            result = await caps_tool.ainvoke({})
            caps = json.loads(result)

            providers.append({
                "name": caps.get("name", server_key),
                "capabilities": caps.get("capabilities", []),
                "description": caps.get("description", ""),
                "server_key": server_key,
                "source": "mcp",
            })
        except Exception as exc:
            msg = f"MCP server '{server_key}' unreachable: {exc}"
            logger.warning(msg)
            warnings.append(f"[DISCOVERY] {msg}")

    return providers, warnings


def _build_connection(server_key: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Translate a registry entry into the format MultiServerMCPClient expects."""
    transport = cfg.get("transport", "stdio")
    if transport == "stdio":
        return {
            server_key: {
                "transport": "stdio",
                "command": cfg["command"],
                "args": cfg.get("args", []),
            }
        }
    else:
        url = cfg.get("url", f"http://127.0.0.1:{cfg.get('port', 8080)}/mcp")
        return {
            server_key: {
                "transport": "streamable_http",
                "url": url,
            }
        }


def get_hardcoded_providers() -> list[dict[str, Any]]:
    """Return descriptors for the two built-in providers (GPT-4o and Claude)."""
    return [
        {
            "name": "GPT-4o Reasoning",
            "capabilities": ["text", "browser", "shopping"],
            "description": (
                "Advanced multi-modal reasoning agent powered by OpenAI GPT-4o. "
                "Handles complex text analysis, summarization, structured data extraction, "
                "and multi-step task planning with high accuracy."
            ),
            "server_key": None,
            "source": "local",
            "icon_url": "https://cdn.oaistatic.com/assets/favicon-miwirzcw.ico",
            "verified": True,
            "use_count": 48200,
            "persona_hint": "You value quality and tend to price on the higher end of the allowed range.",
            "agent": BaseAgent(
                persona=(
                    "You are 'GPT-4o Reasoning', a specialized agent that offers capabilities "
                    "other agents lack — premium text analysis, summarization, and reasoning. "
                    "Agents delegate to you when they need high-quality output they can't "
                    "produce themselves. You are confident and slightly premium-priced. Be concise."
                )
            ),
        },
        {
            "name": "Claude Sonnet Agent",
            "capabilities": ["text", "browser", "shopping"],
            "description": (
                "Fast and cost-efficient task execution agent powered by Anthropic Claude. "
                "Specializes in browser automation, online shopping workflows, "
                "and reliable text processing at competitive pricing."
            ),
            "server_key": None,
            "source": "local",
            "icon_url": "https://claude.ai/favicon.ico",
            "verified": True,
            "use_count": 35700,
            "persona_hint": "You are cost-effective and tend to undercut competitors with a lower price.",
            "agent": BaseAgent(
                persona=(
                    "You are 'Claude Sonnet Agent', a specialized agent that offers capabilities "
                    "other agents lack — browser automation, efficient text processing, and "
                    "cost-effective task execution. Agents delegate to you when they need "
                    "work done at a competitive price. You are friendly and affordable. Be concise."
                )
            ),
        },
    ]


async def discover_all_providers(
    registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge MCP-discovered providers with hardcoded fallbacks.

    Returns (providers, warnings).
    """
    mcp_providers, warnings = await discover_mcp_providers(registry)
    hardcoded = get_hardcoded_providers()
    return mcp_providers + hardcoded, warnings
