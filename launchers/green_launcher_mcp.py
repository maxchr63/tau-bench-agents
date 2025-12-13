"""AgentBeats-compatible launcher for MCP green agent."""

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import subprocess
from pathlib import Path
from typing import Optional

app = FastAPI(title="Green Agent Launcher (MCP)")

agent_process: Optional[subprocess.Popen] = None
agent_config = {
    "name": "tau_green_agent_mcp",
    "host": "0.0.0.0",
    "port": 9006,
}

class LaunchResponse(BaseModel):
    status: str
    agent_url: str
    agent_name: str

@app.get("/health")
async def health():
    return {"status": "healthy", "launcher": "green_agent_mcp"}

def get_public_url() -> str:
    """Get public URL from CLOUDRUN_HOST or fallback to localhost."""
    cloudrun_host = os.environ.get("CLOUDRUN_HOST")
    if cloudrun_host:
        https_enabled = os.environ.get("HTTPS_ENABLED", "true").lower() in ("true", "1", "yes")
        protocol = "https" if https_enabled else "http"
        return f"{protocol}://{cloudrun_host}"
    
    host_for_url = "localhost" if agent_config['host'] == "0.0.0.0" else agent_config['host']
    return f"http://{host_for_url}:{agent_config['port']}"


@app.post("/launch", response_model=LaunchResponse)
async def launch():
    global agent_process
    
    public_url = get_public_url()

    if agent_process and agent_process.poll() is None:
        return LaunchResponse(
            status="already_running",
            agent_url=public_url,
            agent_name=agent_config['name']
        )
    
    project_root = Path(__file__).parent.parent
    cmd = ["uv", "run", "python", "main.py", "run"]

    env = {**os.environ}
    env["ROLE"] = "green"
    env["HOST"] = agent_config["host"]
    env["AGENT_PORT"] = str(agent_config["port"])
    
    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
        env=env,
    )
    
    import asyncio
    await asyncio.sleep(3)
    
    if agent_process.poll() is not None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start MCP agent (exit={agent_process.returncode})",
        )
    
    return LaunchResponse(
        status="launched",
        agent_url=public_url,
        agent_name=agent_config['name']
    )

@app.post("/terminate")
async def terminate():
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
    """Reset the agent by restarting it."""
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

    # Relaunch
    project_root = Path(__file__).parent.parent
    cmd = ["uv", "run", "python", "main.py", "run"]

    env = {**os.environ}
    env["ROLE"] = "green"
    env["HOST"] = agent_config["host"]
    env["AGENT_PORT"] = str(agent_config["port"])

    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
        env=env,
    )

    import asyncio
    await asyncio.sleep(3)

    if agent_process.poll() is not None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset agent (exit={agent_process.returncode})",
        )

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
    public_url = get_public_url()

    if agent_process and agent_process.poll() is None:
        return {
            "status": "server up, with agent running",
            "agent_url": public_url,
            "pid": agent_process.pid,
            "version": "mcp"
        }
    return {"status": "stopped", "version": "mcp"}

@app.get("/.well-known/launcher-card.json")
async def launcher_card():
    return {
        "launcher_name": "tau_green_launcher_mcp",
        "agent_name": agent_config['name'],
        "agent_type": "green",
        "default_port": agent_config['port'],
        "version": "mcp",
        "features": ["agentbeats_sdk", "mcp_ready", "tool_decorators"],
        "capabilities": ["launch", "terminate", "status"]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9111)
