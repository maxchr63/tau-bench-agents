"""CLI entry point for tau-bench-agents (AgentBeats v2 compatible)."""

import os
import typer
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file FIRST before any other imports
import dotenv
dotenv.load_dotenv()

from implementations.mcp.green_agent.agent import start_green_agent


def _start_white_by_variant(*, host: str, port: int, public_url: str | None) -> None:
    """
    Start the white agent implementation selected by AGENT_VARIANT.

    Variants:
    - baseline (default)
    - stateless
    - reasoning
    """
    variant = (os.environ.get("AGENT_VARIANT") or "baseline").strip().lower()

    if variant in ("", "baseline", "default"):
        from implementations.mcp.white_agent.agent import start_white_agent as start_baseline
        start_baseline(host=host, port=port, public_url=public_url)
        return

    if variant == "stateless":
        from implementations.mcp.white_agent.agent_stateless import start_white_agent as start_stateless
        start_stateless(host=host, port=port, public_url=public_url)
        return

    if variant == "reasoning":
        from implementations.mcp.white_agent.agent_reasoning import start_white_agent as start_reasoning
        start_reasoning(host=host, port=port, public_url=public_url)
        return

    raise ValueError(f"Unknown AGENT_VARIANT: {variant!r}")


def get_agent_url() -> str | None:
    """
    Determine the externally reachable base URL for this agent.

    Priority (v2 / Earthshaker-compatible):
    1) AGENT_URL (preferred): Injected by the AgentBeats/Earthshaker controller.
       This already includes the required `/to_agent/<agent_id>` path, so it can be
       used as-is for the agent card URL.
    2) CLOUDRUN_HOST (+ HTTPS_ENABLED): Legacy/manual option when running the agent
       directly behind a tunnel without the controller proxy path.
    3) None: Fall back to localhost URLs.
    """
    agent_url = os.environ.get("AGENT_URL")
    if agent_url:
        return agent_url.rstrip("/")

    cloudrun_host = os.environ.get("CLOUDRUN_HOST")
    if not cloudrun_host:
        return None
    
    https_enabled = os.environ.get("HTTPS_ENABLED", "true").lower() in ("true", "1", "yes")
    protocol = "https" if https_enabled else "http"
    return f"{protocol}://{cloudrun_host}"


class TaubenchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    role: str = "unspecified"
    host: str = "0.0.0.0"
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
    from implementations.mcp.white_agent.agent import start_white_agent as start_baseline
    start_baseline(public_url=agent_url)


@app.command()
def run():
    """Run the agent based on environment variables (used by AgentBeats controller)."""
    settings = TaubenchSettings()
    agent_url = get_agent_url()
    
    role = (os.environ.get("ROLE") or os.environ.get("AGENT") or settings.role).strip().lower()
    if agent_url:
        print(f"[URL] {agent_url} ({role})")

    if role == "green":
        start_green_agent(host=settings.host, port=settings.agent_port, public_url=agent_url)
    elif role == "white":
        _start_white_by_variant(host=settings.host, port=settings.agent_port, public_url=agent_url)
    else:
        raise ValueError(f"Unknown role: {role}")


@app.command()
def white_stateless():
    """Start the stateless white agent (NO conversation memory - expected to perform worse)."""
    from implementations.mcp.white_agent.agent_stateless import start_white_agent as start_stateless
    start_stateless(public_url=get_agent_url())


@app.command()
def white_reasoning():
    """Start the reasoning-enhanced white agent (explicit reasoning steps - expected to perform better)."""
    from implementations.mcp.white_agent.agent_reasoning import start_white_agent as start_reasoning
    start_reasoning(public_url=get_agent_url())



if __name__ == "__main__":
    app()
