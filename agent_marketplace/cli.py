"""Main demo loop with display."""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt, FloatPrompt

from pathlib import Path

from agent_marketplace.config import MCP_ENABLED, MCP_REGISTRY_PATH, STEP_DELAY
from agent_marketplace.display.panels import build_layout
from agent_marketplace.graph import build_graph, set_payment_provider
from agent_marketplace.mcp.registry import load_registry
from agent_marketplace.payments.plasma import PlasmaEscrowProvider
from agent_marketplace.state import MarketplaceState

console = Console()


def _get_payment_provider() -> PlasmaEscrowProvider:
    """Return the Plasma escrow payment provider."""
    return PlasmaEscrowProvider()


def main() -> None:
    """Run the marketplace demo."""
    console.print("\n[bold blue]Agent Task Marketplace[/bold blue]")
    console.print("[dim]Outsource tasks your agent can't handle — settled on-chain[/dim]\n")

    # Setup
    provider = _get_payment_provider()
    set_payment_provider(provider)

    graph = build_graph()
    app = graph.compile()

    # Prompt user for job details
    job_description = Prompt.ask(
        "[bold cyan]What task does your agent need help with?[/bold cyan]",
        default="Summarize the key innovations of Plasma blockchain in 3 bullet points",
    )
    job_budget_xpl = FloatPrompt.ask(
        "[bold cyan]Budget in XPL[/bold cyan]",
        default=0.01,
    )
    console.print()

    # Load MCP registry
    registry = load_registry(Path(MCP_REGISTRY_PATH)) if MCP_ENABLED else {}

    # Initial state
    initial_state: MarketplaceState = {
        "job_description": job_description,
        "job_budget_xpl": job_budget_xpl,
        "bids": [],
        "selected_provider": "",
        "selected_price": 0.0,
        "budget_valid": False,
        "payment_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_xpl": 0.0, "chain": ""},
        "payment_status": "pending",
        "escrow_id": "",
        "escrow_status": "pending",
        "escrow_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_xpl": 0.0, "chain": ""},
        "judge_scores": {},
        "judge_verdict": "",
        "judge_reasoning": "",
        "work_result": "",
        "job_type": "text",
        "marketplace_status": "idle",
        "events_log": [],
        "discovered_providers": [],
        "mcp_provider_map": {},
        "mcp_registry": registry,
    }

    # Merge updates from stream into running state
    current_state: dict = dict(initial_state)

    console.print(f"[green]Network:[/green] Plasma Testnet")
    console.print(f"[green]Contract:[/green] {provider.contract_address}")
    console.print(f"[green]Job:[/green] {initial_state['job_description']}")
    console.print(f"[green]Budget:[/green] {initial_state['job_budget_xpl']:.4f} XPL")
    console.print()

    with Live(build_layout(current_state), console=console, screen=True, refresh_per_second=4) as live:
        for event in app.stream(initial_state, stream_mode="updates"):
            # event is a dict of {node_name: state_update}
            for node_name, updates in event.items():
                if not isinstance(updates, dict):
                    continue

                # Merge updates into current state
                for key, value in updates.items():
                    if key in ("bids", "events_log") and isinstance(value, list):
                        if not isinstance(current_state.get(key), list):
                            current_state[key] = []
                        current_state[key] = current_state[key] + value
                    else:
                        current_state[key] = value

                # Refresh display
                live.update(build_layout(current_state))
                time.sleep(STEP_DELAY)

    # Final summary
    console.print("\n[bold green]Demo complete![/bold green]\n")

    status = current_state.get("marketplace_status", "unknown")
    if status == "complete":
        escrow_receipt = current_state.get("escrow_receipt", {})
        payment_receipt = current_state.get("payment_receipt", {})
        console.print(f"[green]Provider:[/green] {current_state.get('selected_provider')}")
        console.print(f"[green]Price:[/green] {current_state.get('selected_price', 0):.4f} XPL")
        console.print(f"[green]Escrow ID:[/green] {current_state.get('escrow_id', 'N/A')}")
        console.print(f"[green]Escrow Hold TX:[/green] {escrow_receipt.get('tx_hash', 'N/A')}")
        console.print(f"[green]Judge Verdict:[/green] {current_state.get('judge_verdict', 'N/A')}")
        judge_scores = current_state.get("judge_scores", {})
        if judge_scores:
            avg = sum(judge_scores.get(k, 0.0) for k in ("completeness", "relevance", "quality")) / 3
            console.print(
                f"[green]Rubric Scores:[/green] "
                f"Completeness={judge_scores.get('completeness', 0.0):.1f}  "
                f"Relevance={judge_scores.get('relevance', 0.0):.1f}  "
                f"Quality={judge_scores.get('quality', 0.0):.1f}  "
                f"(avg: {avg:.2f})"
            )
        console.print(f"[green]Release TX:[/green] {payment_receipt.get('tx_hash', 'N/A')}")
        console.print(f"[green]Chain:[/green] {payment_receipt.get('chain', 'N/A')}")
        console.print(f"\n[bold]Work Result:[/bold]")
        console.print(current_state.get("work_result", "No result"))
    else:
        console.print(f"[red]Status: {status}[/red]")
        judge_verdict = current_state.get("judge_verdict", "")
        if judge_verdict:
            console.print(f"[red]Judge Verdict:[/red] {judge_verdict}")
            judge_scores = current_state.get("judge_scores", {})
            if judge_scores:
                avg = sum(judge_scores.get(k, 0.0) for k in ("completeness", "relevance", "quality")) / 3
                console.print(
                    f"[red]Rubric Scores:[/red] "
                    f"Completeness={judge_scores.get('completeness', 0.0):.1f}  "
                    f"Relevance={judge_scores.get('relevance', 0.0):.1f}  "
                    f"Quality={judge_scores.get('quality', 0.0):.1f}  "
                    f"(avg: {avg:.2f})"
                )
            console.print(f"[red]Reason:[/red] {current_state.get('judge_reasoning', '')}")

        # Print recent events so the failure reason is visible
        events = current_state.get("events_log", [])
        if events:
            console.print(f"\n[bold]Activity log:[/bold]")
            for event in events[-10:]:
                console.print(f"  {event}")

    console.print()
