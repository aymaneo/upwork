"""Browser-use wrapper for executing real web actions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_marketplace.config import (
    CHROME_PROFILE_DIR,
    CHROME_USER_DATA_DIR,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


class GroceryItem(BaseModel):
    """A single grocery item."""

    name: str = Field(..., description="Item name")
    price: float = Field(..., description="Price as number")
    brand: str | None = Field(None, description="Brand name")
    size: str | None = Field(None, description="Size or quantity")


class GroceryCart(BaseModel):
    """Grocery cart results."""

    items: list[GroceryItem] = Field(default_factory=list, description="All grocery items found")


async def run_browser_task(
    task: str,
    headless: bool = True,
    output_model: type[BaseModel] | None = None,
) -> str:
    """Run a browser-use agent to execute a web task.

    Returns the final result string or an error message.
    """
    from browser_use import Agent, BrowserSession, ChatOpenAI

    session = BrowserSession(
        headless=headless,
        disable_security=True,
        user_data_dir=CHROME_USER_DATA_DIR,
        profile_directory=CHROME_PROFILE_DIR,
        args=["--lang=en-US", "--accept-lang=en-US"],
    )
    llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY)

    agent_kwargs: dict[str, Any] = dict(task=task, llm=llm, browser_session=session)
    if output_model is not None:
        agent_kwargs["output_model_schema"] = output_model

    agent = Agent(**agent_kwargs)

    try:
        history = await agent.run()
        result = history.final_result()
        return result if result else "Browser task completed but returned no text."
    except Exception as e:
        return f"Browser task failed: {e}"
