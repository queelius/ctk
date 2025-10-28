# MCP Integration Guide

This guide explains how to use the Model Context Protocol (MCP) integration in CTK chat.

## What is MCP?

Model Context Protocol (MCP) is an open standard for connecting AI assistants to external tools and data sources. With MCP, you can:

- Provide file system access
- Execute shell commands
- Query databases
- Call APIs
- And more...

## Quick Start

### 1. Install MCP SDK

```bash
pip install mcp
```

### 2. Run the Example

```bash
python examples/test_mcp_integration.py
```

### 3. Add and Connect to a Server

Once in the chat interface:

```
/mcp add example python examples/mcp_example_server.py
/mcp connect example
```

### 4. List Available Tools

```
/mcp tools
```

### 5. Call a Tool

```
/mcp call echo {"text": "Hello from MCP!"}
/mcp call list_files {"path": "."}
/mcp call get_env {"name": "HOME"}
```

## MCP Commands

### Server Management

- `/mcp add <name> <command> [args...]` - Add a new MCP server
- `/mcp remove <name>` - Remove a server configuration
- `/mcp connect <name>` - Connect to a configured server
- `/mcp disconnect <name>` - Disconnect from a server
- `/mcp list` - List all configured servers

### Tool Management

- `/mcp tools` - List all available tools from connected servers
- `/mcp tools <server>` - List tools from a specific server
- `/mcp call <tool> [json_args]` - Call an MCP tool

## Example MCP Server

The included `mcp_example_server.py` provides these tools:

### echo
Echo back the provided text.

```
/mcp call echo {"text": "Hello World"}
```

### get_env
Get the value of an environment variable.

```
/mcp call get_env {"name": "HOME"}
```

### list_files
List files in a directory.

```
/mcp call list_files {"path": "/tmp"}
```

### run_command
Run a shell command (use with caution!).

```
/mcp call run_command {"command": "ls -la"}
```

## Creating Custom MCP Servers

Here's a minimal example of creating your own MCP server:

```python
#!/usr/bin/env python3
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# Create server
server = Server("my-tools")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="my_tool",
            description="Description of what this tool does",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "First parameter"
                    }
                },
                "required": ["param1"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "my_tool":
        param1 = arguments.get("param1", "")
        result = f"You called my_tool with param1={param1}"
        return [types.TextContent(type="text", text=result)]
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

Save this as `my_mcp_server.py`, then in CTK chat:

```
/mcp add myserver python my_mcp_server.py
/mcp connect myserver
/mcp call my_tool {"param1": "test"}
```

## Pre-built MCP Servers

The MCP community has created many pre-built servers:

- **filesystem** - File system operations
- **git** - Git repository operations
- **github** - GitHub API access
- **postgres** - PostgreSQL database access
- **sqlite** - SQLite database access
- **puppeteer** - Web browser automation
- **slack** - Slack API access

See the [MCP GitHub organization](https://github.com/modelcontextprotocol) for more.

### Using Pre-built Servers

Most pre-built servers are installable via npm or pip. For example:

```bash
# Install the filesystem server
npm install -g @modelcontextprotocol/server-filesystem

# Or for Python servers
pip install mcp-server-git
```

Then in CTK chat:

```
/mcp add fs npx @modelcontextprotocol/server-filesystem /path/to/directory
/mcp connect fs
/mcp tools fs
```

## Architecture

The MCP integration in CTK consists of:

1. **MCPClient** (`ctk/integrations/llm/mcp_client.py`) - Manages connections to MCP servers
2. **ChatTUI** - Provides `/mcp` slash commands for interacting with MCP tools
3. **MCP Servers** - External processes that provide tools via the MCP protocol

The client communicates with servers over stdio (standard input/output), making it easy to integrate servers written in any language.

## Troubleshooting

### Server Won't Connect

Check that:
- The server script/command is correct
- Required dependencies are installed
- The server is executable (for Python: `chmod +x server.py`)

### Tool Call Fails

Verify:
- Server is connected (`/mcp list` should show "connected")
- Tool name is correct (`/mcp tools` to list available tools)
- Arguments match the tool's schema (use `/mcp tools` to see required parameters)
- Arguments are valid JSON

### Server Crashes

Check:
- Server logs (if available)
- Python/Node version compatibility
- Required environment variables are set

## Security Considerations

MCP servers can execute arbitrary code and access system resources. Always:

1. Review server source code before using
2. Only connect to trusted servers
3. Be cautious with tools that execute commands or modify files
4. Run servers with minimal necessary permissions
5. Use environment isolation (containers, VMs) for untrusted servers

## Further Reading

- [MCP Specification](https://modelcontextprotocol.io/specification)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Pre-built Servers](https://github.com/modelcontextprotocol)
