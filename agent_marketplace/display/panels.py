"""Rich panels, tables, and layouts for the terminal UI."""

from __future__ import annotations

from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_marketplace.state import MarketplaceState


def make_header() -> Panel:
    """Top banner for the marketplace."""
    title = Text("AGENT COMPUTE MARKETPLACE", style="bold white on blue")
    subtitle = Text("AI agents hiring & paying each other on Plasma", style="dim")
    content = Text.assemble(title, "\n", subtitle)
    return Panel(Align.center(content), style="blue", height=5)


def make_job_panel(state: MarketplaceState) -> Panel:
    """Panel showing the current job details."""
    desc = state.get("job_description", "No job posted yet")
    budget = state.get("job_budget_usdc", 0)
    status = state.get("marketplace_status", "idle")
    job_type = state.get("job_type", "text")

    status_colors = {
        "bidding": "yellow",
        "paying": "cyan",
        "delivering": "magenta",
        "complete": "green",
        "failed": "red",
    }
    color = status_colors.get(status, "white")
    type_colors = {"browser": "cyan", "shopping": "yellow", "text": "green"}
    type_color = type_colors.get(job_type, "green")

    content = (
        f"[bold]{desc}[/bold]\n\n"
        f"Budget: [green]${budget:.4f} USDC[/green]\n"
        f"Type: [{type_color}]{job_type.upper()}[/{type_color}]\n"
        f"Status: [{color}]{status.upper()}[/{color}]"
    )
    return Panel(content, title="Job", border_style="green")


def make_bids_table(state: MarketplaceState) -> Panel:
    """Table showing all bids received."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Provider", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Status", justify="center")

    bids = state.get("bids", [])
    selected = state.get("selected_provider", "")

    for bid in bids:
        name = bid["provider_name"]
        price = f"${bid['price_usdc']:.4f}"
        if name == selected:
            status = "[green]SELECTED[/green]"
        else:
            status = "[dim]outbid[/dim]"
        table.add_row(name, price, status)

    if not bids:
        table.add_row("[dim]Waiting for bids...[/dim]", "", "")

    return Panel(table, title="Bids", border_style="cyan")


def make_payment_panel(state: MarketplaceState) -> Panel:
    """Panel showing escrow lifecycle."""
    escrow_status = state.get("escrow_status", "pending")
    escrow_receipt = state.get("escrow_receipt")
    payment_receipt = state.get("payment_receipt")
    judge_verdict = state.get("judge_verdict", "")
    judge_reasoning = state.get("judge_reasoning", "")

    escrow_colors = {
        "pending": "dim",
        "held": "yellow",
        "released": "green",
        "refunded": "red",
    }
    escrow_color = escrow_colors.get(escrow_status, "white")

    lines = [f"Escrow: [{escrow_color}]{escrow_status.upper()}[/{escrow_color}]"]

    escrow_id = state.get("escrow_id", "")
    if escrow_id:
        truncated = escrow_id[:18] + "..." if len(escrow_id) > 18 else escrow_id
        lines.append(f"Escrow ID: [bold]{truncated}[/bold]")

    if escrow_receipt and escrow_receipt.get("tx_hash"):
        lines.append(f"Hold TX: [bold]{escrow_receipt['tx_hash']}[/bold]")

    if judge_verdict:
        v_color = "green" if judge_verdict == "approved" else "red"
        lines.append(f"Judge: [{v_color}]{judge_verdict.upper()}[/{v_color}]")
        if judge_reasoning:
            lines.append(f"  {judge_reasoning}")

    if payment_receipt and payment_receipt.get("tx_hash"):
        label = "Release TX" if escrow_status == "released" else "Refund TX"
        lines.append(
            f"{label}: [bold]{payment_receipt['tx_hash']}[/bold]\n"
            f"From: {payment_receipt['from_addr']}\n"
            f"To: {payment_receipt['to_addr']}\n"
            f"Amount: [green]${payment_receipt['amount_usdc']:.4f} USDC[/green]\n"
            f"Chain: {payment_receipt['chain']}"
        )

    content = "\n".join(lines)
    return Panel(content, title="Escrow & Payment", border_style="yellow")


def make_work_panel(state: MarketplaceState) -> Panel:
    """Panel showing delivered work result."""
    result = state.get("work_result", "")
    job_type = state.get("job_type", "text")
    is_shopping = job_type == "shopping"
    max_len = 1200 if is_shopping else 500
    panel_title = "Shopping Cart" if is_shopping else "Work Result"

    if result:
        # Truncate for display
        if len(result) > max_len:
            result = result[:max_len] + "..."
        content = result
    else:
        content = "[dim]Awaiting delivery...[/dim]"

    return Panel(content, title=panel_title, border_style="magenta")


def make_activity_feed(state: MarketplaceState) -> Panel:
    """Scrolling activity log at the bottom."""
    events = state.get("events_log", [])
    # Show last 10 events
    recent = events[-10:] if events else ["[dim]No activity yet[/dim]"]
    content = "\n".join(recent)
    return Panel(content, title="Activity Feed", border_style="white", height=14)


def build_layout(state: MarketplaceState) -> Layout:
    """Construct the full Rich Layout from current state."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=14),
    )

    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1),
    )

    layout["left"].split_column(
        Layout(name="job", size=8),
        Layout(name="bids", ratio=1),
    )

    layout["right"].split_column(
        Layout(name="payment", size=12),
        Layout(name="work", ratio=1),
    )

    layout["header"].update(make_header())
    layout["job"].update(make_job_panel(state))
    layout["bids"].update(make_bids_table(state))
    layout["payment"].update(make_payment_panel(state))
    layout["work"].update(make_work_panel(state))
    layout["footer"].update(make_activity_feed(state))

    return layout
