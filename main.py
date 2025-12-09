"""CLI entry point for agentify-example-tau-bench."""

import typer

from implementations.mcp.green_agent.agent import start_green_agent
from implementations.mcp.white_agent.agent import start_white_agent

app = typer.Typer(help="Agentified Tau-Bench - Standardized agent assessment framework")


@app.command()
def green():
    """Start the green agent (assessment manager)."""
    start_green_agent()


@app.command()
def white():
    """Start the white agent (baseline with conversation memory)."""
    start_white_agent()


@app.command()
def white_stateless():
    """Start the stateless white agent (NO conversation memory - expected to perform worse)."""
    from implementations.mcp.white_agent.agent_stateless import start_white_agent as start_stateless
    start_stateless()


@app.command()
def white_reasoning():
    """Start the reasoning-enhanced white agent (explicit reasoning steps - expected to perform better)."""
    from implementations.mcp.white_agent.agent_reasoning import start_white_agent as start_reasoning
    start_reasoning()


if __name__ == "__main__":
    app()
