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

    status_colors = {
        "bidding": "yellow",
        "paying": "cyan",
        "delivering": "magenta",
        "complete": "green",
        "failed": "red",
    }
    color = status_colors.get(status, "white")

    content = (
        f"[bold]{desc}[/bold]\n\n"
        f"Budget: [green]${budget:.4f} USDC[/green]\n"
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
    """Panel showing payment receipt."""
    receipt = state.get("payment_receipt")
    pay_status = state.get("payment_status", "pending")

    if receipt:
        content = (
            f"TX: [bold]{receipt['tx_hash']}[/bold]\n"
            f"From: {receipt['from_addr']}\n"
            f"To: {receipt['to_addr']}\n"
            f"Amount: [green]${receipt['amount_usdc']:.4f} USDC[/green]\n"
            f"Chain: {receipt['chain']}\n"
            f"Status: [green]{pay_status.upper()}[/green]"
        )
    else:
        content = f"[dim]Status: {pay_status}[/dim]"

    return Panel(content, title="Payment", border_style="yellow")


def make_work_panel(state: MarketplaceState) -> Panel:
    """Panel showing delivered work result."""
    result = state.get("work_result", "")
    if result:
        # Truncate for display
        if len(result) > 500:
            result = result[:500] + "..."
        content = result
    else:
        content = "[dim]Awaiting delivery...[/dim]"

    return Panel(content, title="Work Result", border_style="magenta")


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
        Layout(name="payment", size=10),
        Layout(name="work", ratio=1),
    )

    layout["header"].update(make_header())
    layout["job"].update(make_job_panel(state))
    layout["bids"].update(make_bids_table(state))
    layout["payment"].update(make_payment_panel(state))
    layout["work"].update(make_work_panel(state))
    layout["footer"].update(make_activity_feed(state))

    return layout
