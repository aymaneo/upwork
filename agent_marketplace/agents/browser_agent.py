"""Browser-use wrapper for executing real web actions."""

from __future__ import annotations

from agent_marketplace.config import OPENAI_API_KEY, OPENAI_MODEL


async def run_browser_task(task: str, headless: bool = True) -> str:
    """Run a browser-use agent to execute a web task.

    Returns the final result string or an error message.
    """
    from browser_use import Agent, Browser, ChatOpenAI

    browser = Browser(
        headless=headless,
        disable_security=True,
        args=["--lang=en-US", "--accept-lang=en-US"],
    )
    llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY)
    agent = Agent(task=task, llm=llm, browser=browser)

    try:
        history = await agent.run()
        result = history.final_result()
        return result if result else "Browser task completed but returned no text."
    except Exception as e:
        return f"Browser task failed: {e}"
