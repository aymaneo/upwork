"""Mock payment provider with in-memory ledger for demo mode."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from agent_marketplace.state import PaymentReceipt


@dataclass
class MockPaymentProvider:
    """In-memory ledger that simulates instant payments."""

    balances: dict[str, float] = field(default_factory=lambda: {
        "client-agent": 100.0,
        "provider-gpt4": 0.0,
        "provider-claude": 0.0,
    })
    transactions: list[PaymentReceipt] = field(default_factory=list)

    def transfer(
        self, from_addr: str, to_addr: str, amount_usdc: float
    ) -> PaymentReceipt:
        if self.balances.get(from_addr, 0) < amount_usdc:
            raise ValueError(
                f"Insufficient balance: {from_addr} has "
                f"${self.balances.get(from_addr, 0):.2f}, needs ${amount_usdc:.2f}"
            )

        self.balances[from_addr] -= amount_usdc
        self.balances[to_addr] = self.balances.get(to_addr, 0) + amount_usdc

        tx_hash = hashlib.sha256(
            f"{from_addr}-{to_addr}-{amount_usdc}-{time.time()}".encode()
        ).hexdigest()[:16]
        tx_hash = f"0x{tx_hash}"

        receipt: PaymentReceipt = {
            "tx_hash": tx_hash,
            "from_addr": from_addr,
            "to_addr": to_addr,
            "amount_usdc": amount_usdc,
            "chain": "mock",
        }
        self.transactions.append(receipt)
        return receipt

    def get_balance(self, addr: str) -> float:
        return self.balances.get(addr, 0.0)
