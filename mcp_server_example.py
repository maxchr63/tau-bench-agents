#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example MCP Server for Tau-Bench Tools

This demonstrates how to expose tau-bench evaluation tools via an MCP server
using the AgentBeats SDK and @ab.tool decorators.
"""

import asyncio
import logging
from typing import Any, Dict, List

import agentbeats as ab

# Import tools to register them
from implementations.mcp.green_agent import tools as green_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TauBenchMCPServer:
    """
    MCP Server exposing tau-bench evaluation tools.

    This server makes tau-bench tools available to any MCP-compatible client,
    including Claude Desktop, other agents, or custom applications.
    """

    def __init__(self):
        self.tools = ab.get_registered_tools()
        logger.info(f"Initialized TauBenchMCPServer with {len(self.tools)} tools")

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all available tools in MCP format.

        Returns:
            List of tool schemas compatible with MCP protocol
        """
        tool_schemas = []

        for tool in self.tools:
            # Extract tool information
            name = tool.__name__
            description = tool.__doc__ or "No description available"

            # Get function signature
            import inspect
            sig = inspect.signature(tool)
            parameters = {}

            for param_name, param in sig.parameters.items():
                param_info = {
                    "type": self._get_parameter_type(param),
                }

                # Add description if available from docstring
                # (You could enhance this with more sophisticated docstring parsing)
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                    param_info["required"] = False
                else:
                    param_info["required"] = True

                parameters[param_name] = param_info

            tool_schema = {
                "name": name,
                "description": description.strip(),
                "parameters": parameters,
            }

            tool_schemas.append(tool_schema)

        return tool_schemas

    def _get_parameter_type(self, param: Any) -> str:
        """
        Convert Python type annotations to simple type strings.

        Args:
            param: Function parameter

        Returns:
            Type string (e.g., "string", "number", "boolean", "object")
        """
        import inspect
        from typing import get_args, get_origin

        if param.annotation == inspect.Parameter.empty:
            return "string"  # Default to string

        annotation = param.annotation

        # Handle Optional types
        origin = get_origin(annotation)
        if origin is type(None) or str(annotation).startswith("Optional"):
            args = get_args(annotation)
            if args:
                annotation = args[0]

        # Map Python types to simple type strings
        type_map = {
            str: "string",
            int: "number",
            float: "number",
            bool: "boolean",
            dict: "object",
            list: "array",
            Dict: "object",
            List: "array",
        }

        for py_type, type_str in type_map.items():
            if annotation == py_type or origin == py_type:
                return type_str

        # Default to string for unknown types
        return "string"

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a registered tool by name.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        # Find the tool
        tool = None
        for t in self.tools:
            if t.__name__ == tool_name:
                tool = t
                break

        if tool is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Call the tool
        logger.info(f"Calling tool '{tool_name}' with arguments: {arguments}")

        # Check if tool is async
        import inspect
        if inspect.iscoroutinefunction(tool):
            result = await tool(**arguments)
        else:
            result = tool(**arguments)

        logger.info(f"Tool '{tool_name}' returned: {str(result)[:200]}...")
        return result

    def get_tool_by_name(self, name: str) -> Any:
        """Get a registered tool by name."""
        for tool in self.tools:
            if tool.__name__ == name:
                return tool
        return None


async def main():
    """
    Example usage of the MCP server.
    """
    print("=" * 80)
    print("Tau-Bench MCP Server Example")
    print("=" * 80)
    print()

    # Create server
    server = TauBenchMCPServer()

    # List available tools
    print(f"Available tools: {len(server.tools)}")
    print()

    tool_schemas = server.list_tools()

    for schema in tool_schemas:
        print(f"📦 {schema['name']}")
        print(f"   {schema['description'][:100]}...")
        print(f"   Parameters: {', '.join(schema['parameters'].keys())}")
        print()

    # Example: Call a tool
    print("=" * 80)
    print("Example: Listing tau-bench tools")
    print("=" * 80)
    print()

    try:
        result = await server.call_tool(
            "list_tau_bench_tools",
            {"task_id": 5}
        )
        print(result)
        print()
    except Exception as e:
        print(f"Error: {e}")
        print()

    # Example: Set up environment
    print("=" * 80)
    print("Example: Setting up tau-bench environment")
    print("=" * 80)
    print()

    try:
        result = await server.call_tool(
            "setup_tau_bench_environment",
            {
                "env_name": "retail",
                "task_id": 5
            }
        )
        print("Environment setup result:")
        print(f"  Success: {result.get('success')}")
        print(f"  Environment: {result.get('env_name')}")
        print(f"  Task ID: {result.get('task_id')}")
        print(f"  Tools available: {len(result.get('tools_available', []))}")
        print()
    except Exception as e:
        print(f"Error: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
