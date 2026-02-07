"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Plasma testnet
PLASMA_RPC_URL: str = os.getenv("PLASMA_RPC_URL", "https://testnet-rpc.plasma.to")
PLASMA_CHAIN_ID: int = int(os.getenv("PLASMA_CHAIN_ID", "9746"))

# Wallets
CLIENT_PRIVATE_KEY: str = os.getenv("CLIENT_PRIVATE_KEY", "")
PROVIDER_WALLET_ADDRESS: str = os.getenv("PROVIDER_WALLET_ADDRESS", "")

# Escrow contract (empty = auto-deploy on first run)
ESCROW_CONTRACT_ADDRESS: str = os.getenv("ESCROW_CONTRACT_ADDRESS", "")

# Judge key (empty = use CLIENT_PRIVATE_KEY)
JUDGE_PRIVATE_KEY: str = os.getenv("JUDGE_PRIVATE_KEY", "")

# Browser
BROWSER_HEADLESS: bool = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
CHROME_USER_DATA_DIR: str = os.getenv(
    "CHROME_USER_DATA_DIR",
    os.path.expanduser("~/Library/Application Support/Google/Chrome"),
)
CHROME_PROFILE_DIR: str = os.getenv("CHROME_PROFILE_DIR", "Default")

# MCP
MCP_REGISTRY_PATH: str = os.getenv("MCP_REGISTRY_PATH", "mcp_servers.json")
MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "true").lower() == "true"

# Smithery
SMITHERY_ENABLED: bool = os.getenv("SMITHERY_ENABLED", "true").lower() == "true"

# Demo
STEP_DELAY: float = float(os.getenv("STEP_DELAY", "1.5"))
