#!/usr/bin/env python3
"""Test script to verify white agent reset functionality."""

import asyncio
import sys

# Add project to path
sys.path.insert(0, '/Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents')

async def test_reset():
    """Test the white agent reset function."""
    from implementations.mcp.green_agent.tools import reset_white_agent
    
    white_agent_url = "http://localhost:9004"
    
    print("=" * 80)
    print("TESTING WHITE AGENT RESET")
    print("=" * 80)
    print()
    
    print(f"Target: {white_agent_url}")
    print(f"Launcher: http://localhost:9210")
    print()
    
    print("Calling reset_white_agent()...")
    result = await reset_white_agent(white_agent_url, timeout=30.0)
    
    print()
    print("Result:")
    print(f"  Success: {result['success']}")
    print(f"  Message: {result.get('message', result.get('error'))}")
    print()
    
    if result['success']:
        print("✅ Reset successful! White agent should be fresh and ready.")
    else:
        print("❌ Reset failed, but evaluation will continue with context isolation.")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_reset())
