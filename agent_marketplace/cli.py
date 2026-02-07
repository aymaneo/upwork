"""Main demo loop with display."""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt, FloatPrompt

from agent_marketplace.config import PAYMENT_MODE, STEP_DELAY
from agent_marketplace.display.panels import build_layout
from agent_marketplace.graph import build_graph, set_payment_provider
from agent_marketplace.payments.mock import MockPaymentProvider
from agent_marketplace.state import MarketplaceState

console = Console()


def _get_payment_provider() -> MockPaymentProvider:
    """Return the appropriate payment provider based on config."""
    if PAYMENT_MODE == "plasma":
        try:
            from agent_marketplace.payments.plasma import PlasmaPaymentProvider

            return PlasmaPaymentProvider()
        except Exception as e:
            console.print(
                f"[yellow]Warning: Plasma init failed ({e}), falling back to mock[/yellow]"
            )
    return MockPaymentProvider()


def main() -> None:
    """Run the marketplace demo."""
    console.print("\n[bold blue]Agent Compute Marketplace[/bold blue]")
    console.print("[dim]AI agents hiring & paying each other on Plasma[/dim]\n")

    # Setup
    provider = _get_payment_provider()
    set_payment_provider(provider)

    graph = build_graph()
    app = graph.compile()

    # Prompt user for job details
    job_description = Prompt.ask(
        "[bold cyan]Describe the job for agents[/bold cyan]",
        default="Summarize the key innovations of Plasma blockchain in 3 bullet points",
    )
    job_budget_usdc = FloatPrompt.ask(
        "[bold cyan]Budget in XPL[/bold cyan]",
        default=0.01,
    )
    console.print()

    # Initial state
    initial_state: MarketplaceState = {
        "job_description": job_description,
        "job_budget_usdc": job_budget_usdc,
        "bids": [],
        "selected_provider": "",
        "selected_price": 0.0,
        "budget_valid": False,
        "payment_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_usdc": 0.0, "chain": ""},
        "payment_status": "pending",
        "escrow_status": "pending",
        "escrow_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_usdc": 0.0, "chain": ""},
        "judge_verdict": "",
        "judge_reasoning": "",
        "work_result": "",
        "job_type": "text",
        "marketplace_status": "idle",
        "events_log": [],
    }

    # Merge updates from stream into running state
    current_state: dict = dict(initial_state)

    console.print(f"[green]Payment mode:[/green] {PAYMENT_MODE}")
    console.print(f"[green]Job:[/green] {initial_state['job_description']}")
    console.print(f"[green]Budget:[/green] ${initial_state['job_budget_usdc']:.4f} USDC")
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
        console.print(f"[green]Price:[/green] ${current_state.get('selected_price', 0):.4f} USDC")
        console.print(f"[green]Escrow Hold TX:[/green] {escrow_receipt.get('tx_hash', 'N/A')}")
        console.print(f"[green]Judge Verdict:[/green] {current_state.get('judge_verdict', 'N/A')}")
        console.print(f"[green]Release TX:[/green] {payment_receipt.get('tx_hash', 'N/A')}")
        console.print(f"[green]Chain:[/green] {payment_receipt.get('chain', 'N/A')}")
        console.print(f"\n[bold]Work Result:[/bold]")
        console.print(current_state.get("work_result", "No result"))
    else:
        console.print(f"[red]Status: {status}[/red]")
        judge_verdict = current_state.get("judge_verdict", "")
        if judge_verdict:
            console.print(f"[red]Judge Verdict:[/red] {judge_verdict}")
            console.print(f"[red]Reason:[/red] {current_state.get('judge_reasoning', '')}")

    console.print()
