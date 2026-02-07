"""Plasma testnet payment provider — native XPL transfers via web3.py."""

from __future__ import annotations

from eth_account import Account
from web3 import Web3

from agent_marketplace.config import (
    CLIENT_PRIVATE_KEY,
    PLASMA_CHAIN_ID,
    PLASMA_RPC_URL,
    PROVIDER_WALLET_ADDRESS,
)
from agent_marketplace.state import PaymentReceipt


class PlasmaPaymentProvider:
    """Real Plasma testnet payments via native XPL transfers."""

    def __init__(self) -> None:
        if not CLIENT_PRIVATE_KEY:
            raise ValueError("CLIENT_PRIVATE_KEY required for Plasma mode")
        if not PROVIDER_WALLET_ADDRESS:
            raise ValueError("PROVIDER_WALLET_ADDRESS required for Plasma mode")

        self.w3 = Web3(Web3.HTTPProvider(PLASMA_RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to Plasma RPC: {PLASMA_RPC_URL}")

        self.account = Account.from_key(CLIENT_PRIVATE_KEY)

    def transfer(
        self, from_addr: str, to_addr: str, amount_usdc: float
    ) -> PaymentReceipt:
        """Execute native XPL transfer on Plasma testnet."""
        amount_wei = self.w3.to_wei(amount_usdc, "ether")
        to = Web3.to_checksum_address(PROVIDER_WALLET_ADDRESS)

        tx = {
            "from": self.account.address,
            "to": to,
            "value": amount_wei,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": PLASMA_CHAIN_ID,
            "gas": 21_000,
            "gasPrice": self.w3.eth.gas_price,
        }

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

        return {
            "tx_hash": tx_hash.hex(),
            "from_addr": self.account.address,
            "to_addr": PROVIDER_WALLET_ADDRESS,
            "amount_usdc": amount_usdc,
            "chain": f"plasma-testnet (chainId={PLASMA_CHAIN_ID})",
        }

    def get_balance(self, addr: str | None = None) -> float:
        """Check native XPL balance."""
        address = Web3.to_checksum_address(addr or self.account.address)
        return float(self.w3.from_wei(self.w3.eth.get_balance(address), "ether"))
