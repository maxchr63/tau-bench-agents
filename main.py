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
    """Start the white agent (target being tested)."""
    start_white_agent()


if __name__ == "__main__":
    app()
