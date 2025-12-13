"""CLI entry point for tau-bench-agents (AgentBeats v2 compatible)."""

import asyncio
import json
import os
import typer
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file FIRST before any other imports
import dotenv
dotenv.load_dotenv()

from implementations.mcp.green_agent.agent import start_green_agent
from implementations.mcp.my_util import my_a2a


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

    # Accept a few common user inputs (with scheme or trailing slash) and
    # normalize to a bare host so we don't accidentally generate URLs like
    # `https://<host>//to_agent/...`.
    cloudrun_host = cloudrun_host.strip()
    if cloudrun_host.startswith("https://"):
        cloudrun_host = cloudrun_host.removeprefix("https://")
    elif cloudrun_host.startswith("http://"):
        cloudrun_host = cloudrun_host.removeprefix("http://")
    cloudrun_host = cloudrun_host.rstrip("/")
    
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
def launch(
    domain: str = "retail",
    task_id: int = 5,
    variant: str = "baseline",
    k: int = 1,
    max_num_steps: int = 30,
    reset_between_attempts: bool = False,
):
    """Launch a complete local evaluation (like agentify-example)."""

    async def _run() -> None:
        import multiprocessing

        # Ports match this repo's default AgentBeats setup.
        green_address = ("localhost", 9006)
        green_url = f"http://{green_address[0]}:{green_address[1]}"

        variant_norm = (variant or "baseline").strip().lower()
        if variant_norm == "stateless":
            from implementations.mcp.white_agent.agent_stateless import start_white_agent as start_white_agent
            white_port = 9014
        elif variant_norm == "reasoning":
            from implementations.mcp.white_agent.agent_reasoning import start_white_agent as start_white_agent
            white_port = 9024
        else:
            variant_norm = "baseline"
            from implementations.mcp.white_agent.agent import start_white_agent as start_white_agent
            white_port = 9004
        white_address = ("localhost", white_port)
        white_url = f"http://{white_address[0]}:{white_address[1]}"

        p_green = multiprocessing.Process(
            target=start_green_agent,
            args=("tau_green_agent_mcp", *green_address),
            kwargs={"public_url": None},
        )
        p_white = multiprocessing.Process(
            target=start_white_agent,
            kwargs={"host": white_address[0], "port": white_address[1], "public_url": None},
        )

        try:
            print(f"Launching green agent at {green_url} ...")
            p_green.start()
            assert await my_a2a.wait_agent_ready(green_url), "Green agent not ready in time"
            print("Green agent is ready.")

            print(f"Launching white agent ({variant_norm}) at {white_url} ...")
            p_white.start()
            assert await my_a2a.wait_agent_ready(white_url), "White agent not ready in time"
            print("White agent is ready.")

            # Send the task description to the green agent (agentify-example style).
            task_config: dict[str, object] = {
                "env": domain,
                "user_strategy": "llm",
                "task_split": "test",
                "task_ids": [task_id],
                # extra knobs supported by our green agent:
                "k": k,
                "max_num_steps": max_num_steps,
                "reset_between_attempts": reset_between_attempts,
            }

            task_text = f"""
Your task is to instantiate tau-bench to test the agent located at:
<white_agent_url>
{white_url}
</white_agent_url>
You should use the following env configuration:
<env_config>
{json.dumps(task_config, indent=2)}
</env_config>
            """.strip()

            print("Sending task description to green agent...")
            response = await my_a2a.send_message(green_url, task_text)
            print("Response from green agent:")
            print(response)
        finally:
            # Best-effort cleanup
            for p in (p_green, p_white):
                try:
                    if p.is_alive():
                        p.terminate()
                except Exception:
                    pass
            for p in (p_green, p_white):
                try:
                    p.join(timeout=3)
                except Exception:
                    pass

    asyncio.run(_run())


@app.command("launch_remote")
def launch_remote(
    green_url: str,
    white_url: str,
    domain: str = "retail",
    task_id: int = 5,
    k: int = 1,
    max_num_steps: int = 30,
    reset_between_attempts: bool = False,
):
    """Send a tau-bench evaluation request to an existing green agent."""

    async def _run() -> None:
        task_config: dict[str, object] = {
            "env": domain,
            "user_strategy": "llm",
            "task_split": "test",
            "task_ids": [task_id],
            "k": k,
            "max_num_steps": max_num_steps,
            "reset_between_attempts": reset_between_attempts,
        }

        task_text = f"""
Your task is to instantiate tau-bench to test the agent located at:
<white_agent_url>
{white_url.rstrip('/')}
</white_agent_url>
You should use the following env configuration:
<env_config>
{json.dumps(task_config, indent=2)}
</env_config>
        """.strip()

        response = await my_a2a.send_message(green_url.rstrip("/"), task_text)
        print(response)

    asyncio.run(_run())


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
