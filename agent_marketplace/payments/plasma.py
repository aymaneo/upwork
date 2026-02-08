"""Plasma testnet escrow provider — on-chain smart contract escrow via web3.py."""

from __future__ import annotations

from eth_account import Account
from web3 import Web3

from agent_marketplace.config import (
    CLIENT_PRIVATE_KEY,
    ESCROW_CONTRACT_ADDRESS,
    JUDGE_PRIVATE_KEY,
    PLASMA_CHAIN_ID,
    PLASMA_RPC_URL,
    PROVIDER_WALLET_ADDRESS,
)
from agent_marketplace.payments.escrow_contract import ESCROW_ABI, ESCROW_BYTECODE
from agent_marketplace.state import PaymentReceipt


class PlasmaEscrowProvider:
    """On-chain escrow on Plasma testnet using the AgentEscrow contract."""

    def __init__(self) -> None:
        if not CLIENT_PRIVATE_KEY:
            raise ValueError("CLIENT_PRIVATE_KEY required for Plasma escrow")
        if not PROVIDER_WALLET_ADDRESS:
            raise ValueError("PROVIDER_WALLET_ADDRESS required for Plasma escrow")

        self.w3 = Web3(Web3.HTTPProvider(PLASMA_RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to Plasma RPC: {PLASMA_RPC_URL}")

        self.client_account = Account.from_key(CLIENT_PRIVATE_KEY)

        judge_key = JUDGE_PRIVATE_KEY or CLIENT_PRIVATE_KEY
        self.judge_account = Account.from_key(judge_key)

        if ESCROW_CONTRACT_ADDRESS:
            self.contract_address = Web3.to_checksum_address(ESCROW_CONTRACT_ADDRESS)
            self.contract = self.w3.eth.contract(
                address=self.contract_address, abi=ESCROW_ABI
            )
        else:
            self.contract_address, self.contract = self._deploy_contract()

    def _deploy_contract(self) -> tuple:
        """Deploy AgentEscrow contract using the judge address as constructor arg."""
        contract = self.w3.eth.contract(abi=ESCROW_ABI, bytecode=ESCROW_BYTECODE)
        judge_addr = Web3.to_checksum_address(self.judge_account.address)

        tx = contract.constructor(judge_addr).build_transaction(
            {
                "from": self.client_account.address,
                "nonce": self.w3.eth.get_transaction_count(self.client_account.address),
                "chainId": PLASMA_CHAIN_ID,
                "gas": 1_500_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.client_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status != 1:
            raise RuntimeError(f"Contract deploy reverted: {tx_hash.hex()}")

        addr = receipt.contractAddress
        deployed = self.w3.eth.contract(address=addr, abi=ESCROW_ABI)
        return addr, deployed

    @staticmethod
    def generate_escrow_id(job_description: str, provider_address: str) -> bytes:
        """Unique escrow ID from job + provider + timestamp."""
        import time
        return Web3.keccak(
            text=f"{job_description}:{provider_address}:{time.time()}"
        )

    def deposit(
        self, escrow_id: bytes, provider_address: str, amount_xpl: float
    ) -> PaymentReceipt:
        """Lock XPL in the escrow contract."""
        amount_wei = self.w3.to_wei(amount_xpl, "ether")
        provider = Web3.to_checksum_address(provider_address)

        tx = self.contract.functions.deposit(escrow_id, provider).build_transaction(
            {
                "from": self.client_account.address,
                "value": amount_wei,
                "nonce": self.w3.eth.get_transaction_count(self.client_account.address),
                "chainId": PLASMA_CHAIN_ID,
                "gas": 200_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.client_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            raise RuntimeError(f"Deposit reverted: {tx_hash.hex()}")

        return {
            "tx_hash": tx_hash.hex(),
            "from_addr": self.client_account.address,
            "to_addr": self.contract_address,
            "amount_xpl": amount_xpl,
            "chain": f"plasma-testnet (chainId={PLASMA_CHAIN_ID})",
        }

    def release(self, escrow_id: bytes) -> PaymentReceipt:
        """Judge releases escrowed funds to the provider."""
        tx = self.contract.functions.release(escrow_id).build_transaction(
            {
                "from": self.judge_account.address,
                "nonce": self.w3.eth.get_transaction_count(self.judge_account.address),
                "chainId": PLASMA_CHAIN_ID,
                "gas": 100_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.judge_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            raise RuntimeError(f"Release reverted: {tx_hash.hex()}")

        return {
            "tx_hash": tx_hash.hex(),
            "from_addr": self.contract_address,
            "to_addr": "provider",
            "amount_xpl": 0.0,
            "chain": f"plasma-testnet (chainId={PLASMA_CHAIN_ID})",
        }

    def refund(self, escrow_id: bytes) -> PaymentReceipt:
        """Judge refunds escrowed funds to the client."""
        tx = self.contract.functions.refund(escrow_id).build_transaction(
            {
                "from": self.judge_account.address,
                "nonce": self.w3.eth.get_transaction_count(self.judge_account.address),
                "chainId": PLASMA_CHAIN_ID,
                "gas": 100_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.judge_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            raise RuntimeError(f"Refund reverted: {tx_hash.hex()}")

        return {
            "tx_hash": tx_hash.hex(),
            "from_addr": self.contract_address,
            "to_addr": self.client_account.address,
            "amount_xpl": 0.0,
            "chain": f"plasma-testnet (chainId={PLASMA_CHAIN_ID})",
        }

    def get_balance(self, addr: str | None = None) -> float:
        """Check native XPL balance."""
        address = Web3.to_checksum_address(addr or self.client_account.address)
        return float(self.w3.from_wei(self.w3.eth.get_balance(address), "ether"))
