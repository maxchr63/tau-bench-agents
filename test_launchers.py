#!/usr/bin/env python3
"""Test script to verify launcher endpoints match AgentBeats expectations."""

import requests
import sys

def test_launcher(name, port):
    """Test a launcher's endpoints."""
    print(f"\n{'='*60}")
    print(f"Testing {name} on port {port}")
    print('='*60)
    
    base_url = f"http://localhost:{port}"
    
    # Test health endpoint
    try:
        resp = requests.get(f"{base_url}/health", timeout=2)
        print(f"✅ Health endpoint: {resp.status_code}")
        print(f"   Response: {resp.json()}")
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return False
    
    # Test status endpoint
    try:
        resp = requests.get(f"{base_url}/status", timeout=2)
        print(f"✅ Status endpoint: {resp.status_code}")
        data = resp.json()
        print(f"   Response: {data}")
        
        # Check if status format matches AgentBeats expectations
        if "status" in data:
            if data["status"] == "server up, with agent running":
                print(f"   ✅ Status format matches AgentBeats expectations")
            elif data["status"] == "stopped":
                print(f"   ℹ️  Launcher is running but agent is not launched yet")
            else:
                print(f"   ⚠️  Status format may not match AgentBeats expectations")
                print(f"      Expected: 'server up, with agent running' when running")
    except Exception as e:
        print(f"❌ Status endpoint failed: {e}")
        return False
    
    # Test launcher card endpoint
    try:
        resp = requests.get(f"{base_url}/.well-known/launcher-card.json", timeout=2)
        print(f"✅ Launcher card endpoint: {resp.status_code}")
        print(f"   Response: {resp.json()}")
    except Exception as e:
        print(f"❌ Launcher card endpoint failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("\n🧪 Testing Agent Launchers for AgentBeats Compatibility")
    
    green_ok = test_launcher("Green Launcher", 9110)
    white_ok = test_launcher("White Launcher", 9210)
    
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Green Launcher: {'✅ PASS' if green_ok else '❌ FAIL'}")
    print(f"  White Launcher: {'✅ PASS' if white_ok else '❌ FAIL'}")
    print('='*60)
    
    if green_ok and white_ok:
        print("\n✅ All tests passed! Launchers are ready for AgentBeats registration.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Make sure launchers are running:")
        print("   Terminal 1: cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents && uv run python src/green_launcher.py")
        print("   Terminal 2: cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents && uv run python src/white_launcher.py")
        sys.exit(1)
