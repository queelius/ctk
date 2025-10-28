#!/usr/bin/env python3
"""
Example MCP server with basic tools.

This demonstrates how to create an MCP server that provides tools
for the CTK chat interface.
"""

import asyncio
import os
import subprocess
import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions


# Create server instance
server = Server("example-tools")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="echo",
            description="Echo back the provided text",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to echo back"
                    }
                },
                "required": ["text"]
            }
        ),
        types.Tool(
            name="get_env",
            description="Get the value of an environment variable",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the environment variable"
                    }
                },
                "required": ["name"]
            }
        ),
        types.Tool(
            name="list_files",
            description="List files in a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list"
                    }
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="run_command",
            description="Run a shell command (use with caution!)",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    }
                },
                "required": ["command"]
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""

    if name == "echo":
        text = arguments.get("text", "")
        return [types.TextContent(
            type="text",
            text=f"Echo: {text}"
        )]

    elif name == "get_env":
        var_name = arguments.get("name", "")
        value = os.environ.get(var_name, "(not set)")
        return [types.TextContent(
            type="text",
            text=f"{var_name}={value}"
        )]

    elif name == "list_files":
        path = arguments.get("path", ".")
        try:
            files = os.listdir(path)
            files_str = "\n".join(f"  - {f}" for f in sorted(files))
            return [types.TextContent(
                type="text",
                text=f"Files in {path}:\n{files_str}"
            )]
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error listing directory: {e}"
            )]

    elif name == "run_command":
        command = arguments.get("command", "")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout if result.stdout else result.stderr
            return [types.TextContent(
                type="text",
                text=f"Exit code: {result.returncode}\n\nOutput:\n{output}"
            )]
        except subprocess.TimeoutExpired:
            return [types.TextContent(
                type="text",
                text="Error: Command timed out after 10 seconds"
            )]
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error running command: {e}"
            )]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="example-tools",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
