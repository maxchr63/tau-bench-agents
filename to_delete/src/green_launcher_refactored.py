"""AgentBeats-compatible launcher for REFACTORED green agent."""

import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import subprocess
import signal
from pathlib import Path
from typing import Optional

app = FastAPI(title="Green Agent Launcher (Refactored)")

# Global state
agent_process: Optional[subprocess.Popen] = None
agent_config = {
    "name": "tau_green_agent_refactored",
    "host": "localhost",
    "port": 9006,  # Different port to run side-by-side with original (avoiding 9005 conflict)
}


class LaunchRequest(BaseModel):
    config: dict = {}


class LaunchResponse(BaseModel):
    status: str
    agent_url: str
    agent_name: str


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "launcher": "green_agent_refactored"}


@app.post("/launch", response_model=LaunchResponse)
async def launch():
    """Launch the REFACTORED green agent."""
    global agent_process

    if agent_process and agent_process.poll() is None:
        return LaunchResponse(
            status="already_running",
            agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
            agent_name=agent_config['name']
        )

    # Launch refactored agent
    project_root = Path(__file__).parent.parent
    cmd = [
        "uv", "run", "python", "-c",
        f"""
from src.green_agent.agent_refactored import start_green_agent
start_green_agent('{agent_config['name']}', '{agent_config['host']}', {agent_config['port']})
"""
    ]

    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ}
    )

    import asyncio
    await asyncio.sleep(3)

    if agent_process.poll() is not None:
        stderr = agent_process.stderr.read().decode() if agent_process.stderr else "No error output"
        raise HTTPException(status_code=500, detail=f"Failed to start refactored agent: {stderr}")

    return LaunchResponse(
        status="launched",
        agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
        agent_name=agent_config['name']
    )


@app.post("/terminate")
async def terminate():
    """Terminate the refactored green agent."""
    global agent_process

    if agent_process is None or agent_process.poll() is not None:
        return {"status": "not_running"}

    agent_process.terminate()
    try:
        agent_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        agent_process.kill()

    agent_process = None
    return {"status": "terminated"}


@app.post("/reset")
async def reset(request: dict):
    """Reset the refactored green agent by restarting it."""
    global agent_process

    # Extract parameters from request
    agent_id = request.get("agent_id")
    backend_url = request.get("backend_url")

    # Terminate if running
    if agent_process and agent_process.poll() is None:
        agent_process.terminate()
        try:
            agent_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            agent_process.kill()
        agent_process = None

    # Relaunch the refactored agent
    project_root = Path(__file__).parent.parent
    cmd = [
        "uv", "run", "python", "-c",
        f"""
from src.green_agent.agent_refactored import start_green_agent
start_green_agent('{agent_config['name']}', '{agent_config['host']}', {agent_config['port']})
"""
    ]

    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ}
    )

    import asyncio
    await asyncio.sleep(3)

    if agent_process.poll() is not None:
        stderr = agent_process.stderr.read().decode() if agent_process.stderr else "No error output"
        raise HTTPException(status_code=500, detail=f"Failed to reset refactored agent: {stderr}")

    # Notify backend that agent is ready
    if backend_url and agent_id:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.put(
                    f"{backend_url}/agents/{agent_id}",
                    json={"ready": True}
                )
        except Exception as e:
            print(f"Warning: Failed to notify backend: {e}")

    return {"status": "reset_complete"}


@app.get("/status")
async def status():
    """Check refactored agent status."""
    if agent_process and agent_process.poll() is None:
        return {
            "status": "server up, with agent running",
            "agent_url": f"http://{agent_config['host']}:{agent_config['port']}",
            "pid": agent_process.pid,
            "version": "refactored"
        }
    return {"status": "stopped", "version": "refactored"}


@app.get("/.well-known/launcher-card.json")
async def launcher_card():
    """Provide launcher metadata."""
    return {
        "launcher_name": "tau_green_launcher_refactored",
        "agent_name": agent_config['name'],
        "agent_type": "green",
        "default_port": agent_config['port'],
        "version": "refactored",
        "features": ["agentbeats_sdk", "tool_decorators", "mcp_ready"],
        "capabilities": ["launch", "terminate", "status", "reset"]
    }


if __name__ == "__main__":
    # Launcher runs on port 9111 (refactored), agent will run on 9005
    uvicorn.run(app, host="0.0.0.0", port=9111)
