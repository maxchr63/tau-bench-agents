"""CLI entry point for agentify-example-tau-bench."""

import os
import typer
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file FIRST before any other imports
import dotenv
dotenv.load_dotenv()

from implementations.mcp.green_agent.agent import start_green_agent
from implementations.mcp.white_agent.agent import start_white_agent


def get_agent_url() -> str | None:
    """
    Get agent URL from CLOUDRUN_HOST.
    This is the ONLY way to set the public URL for agents.
    
    CLOUDRUN_HOST is set by the AgentBeats controller and contains the public hostname.
    If not set, agents will use localhost (for local development).
    """
    cloudrun_host = os.environ.get("CLOUDRUN_HOST")
    if not cloudrun_host:
        return None
    
    https_enabled = os.environ.get("HTTPS_ENABLED", "true").lower() in ("true", "1", "yes")
    protocol = "https" if https_enabled else "http"
    return f"{protocol}://{cloudrun_host}"


class TaubenchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    role: str = "unspecified"
    host: str = "127.0.0.1"
    agent_port: int = 9000


app = typer.Typer(help="Agentified Tau-Bench - Standardized agent assessment framework")


@app.command()
def green():
    """Start the green agent (assessment manager)."""
    agent_url = get_agent_url()
    if agent_url:
        print(f"[URL] {agent_url}")
    start_green_agent(public_url=agent_url)


@app.command()
def white():
    """Start the white agent (target being tested)."""
    agent_url = get_agent_url()
    if agent_url:
        print(f"[URL] {agent_url}")
    start_white_agent(public_url=agent_url)


@app.command()
def run():
    """Run the agent based on environment variables (used by AgentBeats controller)."""
    settings = TaubenchSettings()
    agent_url = get_agent_url()
    
    if agent_url:
        print(f"[URL] {agent_url} ({settings.role})")
    
    if settings.role == "green":
        start_green_agent(host=settings.host, port=settings.agent_port, public_url=agent_url)
    elif settings.role == "white":
        start_white_agent(host=settings.host, port=settings.agent_port, public_url=agent_url)
    else:
        raise ValueError(f"Unknown role: {settings.role}")


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
