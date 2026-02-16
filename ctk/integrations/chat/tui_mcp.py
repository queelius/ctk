"""MCP (Model Context Protocol) commands extracted from ChatTUI."""

import json


def handle_mcp_command(mcp_client, args, mcp_auto_tools_ref=None):
    """Handle MCP subcommands.

    Args:
        mcp_client: MCPClient instance
        args: Raw argument string after 'mcp' command
        mcp_auto_tools_ref: Mutable container [bool] for auto-tools toggle state.
            Pass a single-element list like [False] so the function can mutate it.
            Returns the new value if toggled.

    Returns:
        Updated mcp_auto_tools value if 'auto' subcommand was used, else None.
    """
    from ctk.integrations.llm.mcp_client import MCPServer

    parts = args.split(maxsplit=1)
    if not parts or not parts[0].strip():
        print("Usage: mcp <subcommand>")
        print("Available: add, remove, connect, disconnect, list, tools, call, auto")
        return None

    subcmd = parts[0].lower()
    subargs = parts[1] if len(parts) > 1 else ""

    if subcmd == "add":
        # /mcp add <name> <command> [args...]
        if not subargs:
            print("Error: /mcp add requires name and command")
            print("Usage: /mcp add <name> <command> [args...]")
            print(
                "Example: /mcp add filesystem python -m mcp_server_filesystem /path"
            )
            return None

        parts = subargs.split(maxsplit=2)
        if len(parts) < 2:
            print("Error: /mcp add requires name and command")
            return None

        name = parts[0]
        command = parts[1]
        cmd_args = parts[2].split() if len(parts) > 2 else []

        server = MCPServer(name=name, command=command, args=cmd_args)
        mcp_client.add_server(server)
        print(f"Added MCP server '{name}'")

    elif subcmd == "remove":
        if not subargs:
            print("Error: /mcp remove requires server name")
            return None

        mcp_client.remove_server(subargs)
        print(f"Removed MCP server '{subargs}'")

    elif subcmd == "connect":
        if not subargs:
            print("Error: /mcp connect requires server name")
            return None

        try:
            success = mcp_client.connect_server(subargs)
            if success:
                print(f"Connected to MCP server '{subargs}'")
                # Show available tools
                tools = mcp_client.get_server_tools(subargs)
                if tools:
                    print(f"  Available tools ({len(tools)}):")
                    for tool in tools[:5]:  # Show first 5
                        desc = f" - {tool.description}" if tool.description else ""
                        print(f"    - {tool.name}{desc}")
                    if len(tools) > 5:
                        print(f"    ... and {len(tools) - 5} more")
        except Exception as e:
            print(f"Error connecting to server: {e}")

    elif subcmd == "disconnect":
        if not subargs:
            print("Error: /mcp disconnect requires server name")
            return None

        try:
            mcp_client.disconnect_server(subargs)
            print(f"Disconnected from MCP server '{subargs}'")
        except Exception as e:
            print(f"Error disconnecting from server: {e}")

    elif subcmd == "list":
        servers = mcp_client.list_servers()
        if not servers:
            print("No MCP servers configured")
            return None

        print("\nConfigured MCP servers:")
        for server in servers:
            status = (
                "connected"
                if mcp_client.is_connected(server.name)
                else "disconnected"
            )
            print(f"  - {server.name} ({status})")
            print(f"    Command: {server.command} {' '.join(server.args)}")
            if server.description:
                print(f"    Description: {server.description}")

    elif subcmd == "tools":
        # Show tools from specific server or all
        if subargs:
            tools = mcp_client.get_server_tools(subargs)
            if not tools:
                if mcp_client.is_connected(subargs):
                    print(f"No tools available from server '{subargs}'")
                else:
                    print(f"Server '{subargs}' is not connected")
                return None

            print(f"\nTools from '{subargs}':")
        else:
            tools = mcp_client.get_all_tools()
            if not tools:
                print("No tools available (no servers connected)")
                return None

            print("\nAll available tools:")

        for tool in tools:
            desc = f" - {tool.description}" if tool.description else ""
            print(f"  - {tool.name}{desc}")
            if tool.input_schema:
                # Show required parameters
                props = tool.input_schema.get("properties", {})
                required = tool.input_schema.get("required", [])
                if props:
                    print(f"    Parameters:")
                    for param, schema in props.items():
                        req = " (required)" if param in required else ""
                        param_desc = schema.get("description", "")
                        print(f"      - {param}: {schema.get('type', 'any')}{req}")
                        if param_desc:
                            print(f"        {param_desc}")

    elif subcmd == "call":
        # /mcp call <tool_name> [json_args]
        if not subargs:
            print("Error: /mcp call requires tool name")
            print("Usage: /mcp call <tool_name> [json_args]")
            print('Example: /mcp call read_file {"path": "/etc/hosts"}')
            return None

        parts = subargs.split(maxsplit=1)
        tool_name = parts[0]

        # Parse arguments as JSON if provided
        arguments = {}
        if len(parts) > 1:
            try:
                arguments = json.loads(parts[1])
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON arguments: {e}")
                return None

        try:
            print(f"Calling tool '{tool_name}'...")
            result = mcp_client.call_tool(tool_name, arguments)
            print(f"\nTool result:")
            # Use the for_display() method for human-readable output
            print(result.for_display())
        except Exception as e:
            print(f"Error calling tool: {e}")

    elif subcmd == "auto":
        # Toggle automatic tool use
        if mcp_auto_tools_ref is not None:
            mcp_auto_tools_ref[0] = not mcp_auto_tools_ref[0]
            new_val = mcp_auto_tools_ref[0]
        else:
            new_val = True  # Default to enabling if no ref provided

        status = "enabled" if new_val else "disabled"
        print(f"Automatic tool use {status}")
        if new_val:
            connected = mcp_client.get_connected_servers()
            if connected:
                tools = mcp_client.get_all_tools()
                print(
                    f"  {len(tools)} tool(s) available from {len(connected)} server(s)"
                )
            else:
                print("  Warning: No MCP servers connected")
                print("  Use 'mcp connect <server>' to connect to a server")
        return new_val

    else:
        print(f"Unknown MCP subcommand: {subcmd}")
        print(
            "Available: add, remove, connect, disconnect, list, tools, call, auto"
        )

    return None
