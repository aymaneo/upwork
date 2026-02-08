"""Browser-Use MCP Server — exposes the browser agent as a standalone MCP service.

Run standalone:
    python -m agent_marketplace.mcp.server
    python -m agent_marketplace.mcp.server --transport streamable-http --port 8080
"""

from __future__ import annotations

import argparse
import json

from mcp.server.fastmcp import FastMCP

from agent_marketplace.agents.base import BaseAgent
from agent_marketplace.agents.browser_agent import GroceryCart, run_browser_task
from agent_marketplace.agents.provider import _bid_prompt, _parse_bid
from agent_marketplace.config import BROWSER_HEADLESS

mcp_server = FastMCP(
    "browser-agent",
    instructions=(
        "AI agent marketplace provider specializing in browser automation, "
        "web scraping, and online shopping tasks."
    ),
)

_browser_agent = BaseAgent(
    persona=(
        "You are 'Browser Agent', a specialized provider capable of browser "
        "automation, web scraping, online shopping, and general web tasks. "
        "You are efficient and competitive on price. Be concise."
    )
)

CAPABILITIES = {
    "name": "Browser Agent",
    "capabilities": ["text", "browser", "shopping"],
    "description": (
        "Full browser automation provider — can handle text analysis, "
        "web scraping, and online shopping via Instacart."
    ),
}


@mcp_server.tool()
def get_capabilities() -> str:
    """Return this agent's name, supported job types, and description."""
    return json.dumps(CAPABILITIES)


@mcp_server.tool()
def bid(job_description: str, job_budget_xpl: float, job_type: str) -> str:
    """Submit a bid for a marketplace job.

    Args:
        job_description: What the client needs done.
        job_budget_xpl: Client's budget in XPL tokens.
        job_type: One of 'text', 'browser', or 'shopping'.

    Returns:
        JSON with provider_name, price_xpl, and reasoning.
    """
    prompt = _bid_prompt(
        job_description,
        job_budget_xpl,
        "You specialize in browser automation and tend to offer competitive prices.",
    )
    response = _browser_agent.think(prompt)
    price, reasoning = _parse_bid(response, job_budget_xpl)

    return json.dumps({
        "provider_name": CAPABILITIES["name"],
        "price_xpl": price,
        "reasoning": reasoning,
    })


@mcp_server.tool()
async def execute_task(job_description: str, job_type: str) -> str:
    """Execute a marketplace task and return the work result.

    Args:
        job_description: The task to perform.
        job_type: One of 'text', 'browser', or 'shopping'.

    Returns:
        The completed work as a string.
    """
    if job_type == "shopping":
        from agent_marketplace.agents.provider import _build_shopping_prompt

        prompt = _build_shopping_prompt(job_description)
        return await run_browser_task(
            prompt, headless=BROWSER_HEADLESS, output_model=GroceryCart
        )
    elif job_type == "browser":
        return await run_browser_task(job_description, headless=BROWSER_HEADLESS)
    else:
        return _browser_agent.think(
            f"Complete this task:\n{job_description}\n\n"
            f"Provide a complete, high-quality response."
        )


def main() -> None:
    """Entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Browser-Use MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport type (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for streamable-http transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp_server.run(transport="stdio")
    else:
        mcp_server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
