"""CLI entry point for agentify-example-tau-bench."""

import os
import typer
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file FIRST before any other imports
import dotenv
dotenv.load_dotenv()

from implementations.mcp.green_agent.agent import start_green_agent
from implementations.mcp.white_agent.agent import start_white_agent


class TaubenchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    role: str = "unspecified"
    host: str = "127.0.0.1"
    agent_port: int = 9000
    # Public URLs for the agents (used in agent cards)
    green_agent_url: str = ""
    white_agent_url: str = ""


app = typer.Typer(help="Agentified Tau-Bench - Standardized agent assessment framework")


@app.command()
def green():
    """Start the green agent (assessment manager)."""
    settings = TaubenchSettings()
    if settings.green_agent_url:
        os.environ["AGENT_URL"] = settings.green_agent_url
        print(f"Setting AGENT_URL={settings.green_agent_url} for green agent")
    start_green_agent()


@app.command()
def white():
    """Start the white agent (target being tested)."""
    settings = TaubenchSettings()
    print(f"[DEBUG] WHITE_AGENT_URL from env: {os.environ.get('WHITE_AGENT_URL', 'NOT SET')}")
    print(f"[DEBUG] settings.white_agent_url: {settings.white_agent_url or 'EMPTY'}")
    if settings.white_agent_url:
        os.environ["AGENT_URL"] = settings.white_agent_url
        print(f"Setting AGENT_URL={settings.white_agent_url} for white agent")
    else:
        print("[WARNING] white_agent_url is empty - agent card will use localhost")
    start_white_agent()

@app.command()
def run():
    """Run the agent based on environment variables."""
    settings = TaubenchSettings()
    
    # Set AGENT_URL based on role so agents use the correct public URL
    if settings.role == "green":
        if settings.green_agent_url:
            os.environ["AGENT_URL"] = settings.green_agent_url
            print(f"Setting AGENT_URL={settings.green_agent_url} for green agent")
        start_green_agent(host=settings.host, port=settings.agent_port)
    elif settings.role == "white":
        if settings.white_agent_url:
            os.environ["AGENT_URL"] = settings.white_agent_url
            print(f"Setting AGENT_URL={settings.white_agent_url} for white agent")
        start_white_agent(host=settings.host, port=settings.agent_port)
    else:
        raise ValueError(f"Unknown role: {settings.role}")


if __name__ == "__main__":
    app()
