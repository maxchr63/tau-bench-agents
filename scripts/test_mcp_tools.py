#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for MCP tau-bench tools.

This script tests that the tools are properly registered and can be called.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import from implementations/
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import agentbeats as ab


async def test_tool_registration():
    """Test that tools are properly registered with @ab.tool."""
    print("=" * 80)
    print("Test 1: Tool Registration")
    print("=" * 80)
    print()

    # Import tools module to trigger registration
    from implementations.mcp.green_agent import tools as green_tools

    # Get registered tools
    registered_tools = ab.get_registered_tools()

    print(f"✓ Registered {len(registered_tools)} tools")
    print()

    expected_tools = [
        "send_message_to_white_agent",
        "log_battle_progress",
        "report_battle_result",
        "setup_tau_bench_environment",
        "get_tau_bench_tools_as_json",
        "list_tau_bench_tools",
        "evaluate_white_agent",
        "parse_xml_tags",
        "format_evaluation_result",
    ]

    found_tools = [tool.__name__ for tool in registered_tools]

    for expected in expected_tools:
        if expected in found_tools:
            print(f"  ✓ {expected}")
        else:
            print(f"  ✗ {expected} (MISSING)")

    print()
    return len(registered_tools) >= len(expected_tools)


async def test_list_tau_bench_tools():
    """Test listing tau-bench tools."""
    print("=" * 80)
    print("Test 2: List Tau-Bench Tools")
    print("=" * 80)
    print()

    from implementations.mcp.green_agent import tools as green_tools

    try:
        result = green_tools.list_tau_bench_tools(task_id=5)
        print(result)
        print()
        print("✓ list_tau_bench_tools() works")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_setup_environment():
    """Test setting up tau-bench environment."""
    print("=" * 80)
    print("Test 3: Setup Tau-Bench Environment")
    print("=" * 80)
    print()

    from implementations.mcp.green_agent import tools as green_tools

    try:
        result = await green_tools.setup_tau_bench_environment(
            env_name="retail",
            task_id=5
        )

        print(f"Success: {result.get('success')}")
        print(f"Environment: {result.get('env_name')}")
        print(f"Task ID: {result.get('task_id')}")
        print(f"Tools count: {result.get('tools_count')}")
        print(f"Tools available: {len(result.get('tools_available', []))}")
        print()

        if result.get('success'):
            tools_list = result.get('tools_available', [])
            print("Available tools:")
            for tool in tools_list[:5]:  # Show first 5
                print(f"  - {tool}")
            if len(tools_list) > 5:
                print(f"  ... and {len(tools_list) - 5} more")
            print()
            print("✓ setup_tau_bench_environment() works")
        else:
            print("✗ setup_tau_bench_environment() FAILED")
            if 'error' in result:
                print(f"   Error: {result['error']}")

        return result.get('success', False)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_parse_xml_tags():
    """Test XML tag parsing."""
    print("=" * 80)
    print("Test 4: Parse XML Tags")
    print("=" * 80)
    print()

    from implementations.mcp.green_agent import tools as green_tools

    test_text = """
    Here is some text with tags.
    <json>
    {"name": "test_tool", "kwargs": {"arg1": "value1"}}
    </json>
    And some more text.
    <xml>
    <data>test</data>
    </xml>
    """

    try:
        result = green_tools.parse_xml_tags(test_text, "json")
        print(f"Extracted JSON tag content:")
        print(result)
        print()
        print("✓ parse_xml_tags() works")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_format_evaluation_result():
    """Test formatting evaluation results."""
    print("=" * 80)
    print("Test 5: Format Evaluation Result")
    print("=" * 80)
    print()

    from implementations.mcp.green_agent import tools as green_tools

    try:
        # Test success case
        result = green_tools.format_evaluation_result(
            success=True,
            reward=1.0,
            info={"task": {"instruction": "Test task"}},
            metrics={"time_used": 45.2, "steps": 10}
        )
        print("Success case:")
        print(result)
        print()

        # Test failure case
        result = green_tools.format_evaluation_result(
            success=False,
            reward=0.0,
            info={
                "error": "White agent timeout",
                "error_detail": "Agent did not respond within 120 seconds",
                "steps_completed": 5,
                "task": {"instruction": "Complete the user request"}
            },
            metrics={"time_used": 120.0}
        )
        print("Failure case:")
        print(result)
        print()

        print("✓ format_evaluation_result() works")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 23 + "TAU-BENCH MCP TOOLS TEST" + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    results = []

    # Run tests
    results.append(("Tool Registration", await test_tool_registration()))
    results.append(("List Tau-Bench Tools", await test_list_tau_bench_tools()))
    results.append(("Setup Environment", await test_setup_environment()))
    results.append(("Parse XML Tags", await test_parse_xml_tags()))
    results.append(("Format Evaluation Result", await test_format_evaluation_result()))

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed")
    print()

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
