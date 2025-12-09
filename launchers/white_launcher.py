"""AgentBeats-compatible launcher for white agent."""
import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import subprocess
import signal
from pathlib import Path
from typing import Optional

app = FastAPI(title="White Agent Launcher")

agent_process: Optional[subprocess.Popen] = None

# Support for different agent variants
# Set via environment variable AGENT_VARIANT: baseline, stateless, or reasoning
AGENT_VARIANT = os.getenv("AGENT_VARIANT", "baseline")

VARIANT_CONFIG = {
    "baseline": {
        "name": "general_white_agent",
        "host": "localhost",
        "port": 9004,
        "command": "white"
    },
    "stateless": {
        "name": "stateless_white_agent",
        "host": "localhost",
        "port": 9014,
        "command": "white-stateless"
    },
    "reasoning": {
        "name": "reasoning_white_agent",
        "host": "localhost",
        "port": 9024,
        "command": "white-reasoning"
    }
}

agent_config = VARIANT_CONFIG.get(AGENT_VARIANT, VARIANT_CONFIG["baseline"])
print(f"[White Launcher] Using variant: {AGENT_VARIANT} on port {agent_config['port']}")


class LaunchResponse(BaseModel):
    status: str
    agent_url: str
    agent_name: str


@app.get("/health")
async def health():
    return {"status": "healthy", "launcher": "white_agent"}


# @app.post("/launch", response_model=LaunchResponse)
# async def launch():
#     global agent_process
    
#     if agent_process and agent_process.poll() is None:
#         return LaunchResponse(
#             status="already_running",
#             agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
#             agent_name=agent_config['name']
#         )
    
#     project_root = Path(__file__).parent
#     cmd = [
#         "uv", "run", "python", "-c",
#         f"""
# from src.white_agent.agent import start_white_agent
# start_white_agent('{agent_config['name']}', '{agent_config['host']}', {agent_config['port']})
# """
#     ]
    
#     agent_process = subprocess.Popen(
#         cmd,
#         cwd=project_root,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.PIPE,
#         preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
#     )
    
#     import asyncio
#     await asyncio.sleep(2)
    
#     if agent_process.poll() is not None:
#         raise HTTPException(status_code=500, detail="Failed to start agent")
    
#     return LaunchResponse(
#         status="launched",
#         agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
#         agent_name=agent_config['name']
#     )

@app.post("/launch", response_model=LaunchResponse)
async def launch():
    global agent_process
    
    if agent_process and agent_process.poll() is None:
        return LaunchResponse(
            status="already_running",
            agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
            agent_name=agent_config['name']
        )
    
    project_root = Path(__file__).parent.parent
    cmd = [
        "uv", "run", "python", "main.py", agent_config['command']
    ]
    
    # IMPORTANT: Do NOT PIPE stdout/stderr without draining them. It can deadlock when buffers fill.
    # Let the child inherit the parent's stdio or redirect to files.
    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
        env={**os.environ}
    )
    
    import asyncio
    await asyncio.sleep(3)
    
    if agent_process.poll() is not None:
        stderr = agent_process.stderr.read().decode() if agent_process.stderr else "No error output"
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {stderr}")
    
    return LaunchResponse(
        status="launched",
        agent_url=f"http://{agent_config['host']}:{agent_config['port']}",
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
    """Reset the white agent by restarting it."""
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
    
    # Relaunch the agent
    project_root = Path(__file__).parent.parent
    cmd = ["uv", "run", "python", "main.py", agent_config['command']]
    
    # IMPORTANT: Do NOT PIPE stdout/stderr without draining them. It can deadlock when buffers fill.
    agent_process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
        env={**os.environ}
    )
    
    import asyncio
    await asyncio.sleep(3)
    
    if agent_process.poll() is not None:
        stderr = agent_process.stderr.read().decode() if agent_process.stderr else "No error output"
        raise HTTPException(status_code=500, detail=f"Failed to reset agent: {stderr}")
    
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
    if agent_process and agent_process.poll() is None:
        return {
            "status": "server up, with agent running",
            "agent_url": f"http://{agent_config['host']}:{agent_config['port']}",
            "pid": agent_process.pid
        }
    return {"status": "stopped"}


@app.get("/.well-known/launcher-card.json")
async def launcher_card():
    return {
        "launcher_name": "tau_white_launcher",
        "agent_name": agent_config['name'],
        "agent_type": "white",
        "default_port": agent_config['port'],
        "capabilities": ["launch", "terminate", "status"]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9210)

