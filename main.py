"""CLI entry point for agentify-example-tau-bench."""

import typer
from pydantic_settings import BaseSettings

from implementations.mcp.green_agent.agent import start_green_agent
from implementations.mcp.white_agent.agent import start_white_agent


class TaubenchSettings(BaseSettings):
    role: str = "unspecified"
    host: str = "127.0.0.1"
    agent_port: int = 9000


app = typer.Typer(help="Agentified Tau-Bench - Standardized agent assessment framework")


@app.command()
def green():
    """Start the green agent (assessment manager)."""
    start_green_agent()


@app.command()
def white():
    """Start the white agent (target being tested)."""
    start_white_agent()


@app.command()
def run():
    """Run the agent based on environment variables."""
    settings = TaubenchSettings()
    if settings.role == "green":
        start_green_agent(host=settings.host, port=settings.agent_port)
    elif settings.role == "white":
        start_white_agent(host=settings.host, port=settings.agent_port)
    else:
        raise ValueError(f"Unknown role: {settings.role}")


if __name__ == "__main__":
    app()
