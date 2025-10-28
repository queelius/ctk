#!/usr/bin/env python3
"""
MCP server for stateful Python code execution.

Provides tools for executing Python code and inspecting the execution namespace.
The namespace persists across tool calls, allowing for stateful interactions.
"""

import asyncio
import sys
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions


# Create server instance
server = Server("python-repl")

# Persistent namespace for code execution
# Initialize with common imports
execution_namespace = {
    '__builtins__': __builtins__,
    '__name__': '__main__',
    '__doc__': None,
}


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="exec_python",
            description="Execute Python code in a persistent namespace. Variables and functions defined persist across calls.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute"
                    }
                },
                "required": ["code"]
            }
        ),
        types.Tool(
            name="inspect_namespace",
            description="Inspect the current Python namespace to see defined variables, functions, classes, and imports.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_type": {
                        "type": "string",
                        "enum": ["all", "variables", "functions", "classes", "modules"],
                        "description": "Type of objects to show (default: all)"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="reset_namespace",
            description="Reset the Python namespace to its initial state, clearing all user-defined variables and functions.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_variable",
            description="Get the value and type of a specific variable from the namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the variable to inspect"
                    }
                },
                "required": ["name"]
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""

    if name == "exec_python":
        code = arguments.get("code", "")

        # Capture stdout and stderr
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        result_lines = []

        try:
            # Execute code with output capture
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                # Try to eval first (for expressions), fall back to exec
                try:
                    result = eval(code, execution_namespace)
                    if result is not None:
                        result_lines.append(f"Result: {repr(result)}")
                except SyntaxError:
                    # Not an expression, use exec
                    exec(code, execution_namespace)

            # Get captured output
            stdout_output = stdout_buffer.getvalue()
            stderr_output = stderr_buffer.getvalue()

            if stdout_output:
                result_lines.append(f"Output:\n{stdout_output}")

            if stderr_output:
                result_lines.append(f"Stderr:\n{stderr_output}")

            if not result_lines:
                result_lines.append("Code executed successfully (no output)")

            return [types.TextContent(
                type="text",
                text="\n".join(result_lines)
            )]

        except Exception as e:
            error_msg = f"Error: {type(e).__name__}: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            return [types.TextContent(
                type="text",
                text=error_msg
            )]

    elif name == "inspect_namespace":
        filter_type = arguments.get("filter_type", "all")

        # Get user-defined items (exclude builtins and private)
        items = {
            k: v for k, v in execution_namespace.items()
            if not k.startswith('_') and k != '__builtins__'
        }

        if not items:
            return [types.TextContent(
                type="text",
                text="Namespace is empty (no user-defined variables, functions, or classes)"
            )]

        # Categorize items
        variables = {}
        functions = {}
        classes = {}
        modules = {}

        for name, value in items.items():
            import types as python_types
            import inspect

            if inspect.ismodule(value):
                modules[name] = str(type(value).__name__)
            elif inspect.isclass(value):
                classes[name] = f"class {name}"
            elif inspect.isfunction(value) or inspect.ismethod(value):
                try:
                    sig = inspect.signature(value)
                    functions[name] = f"{name}{sig}"
                except:
                    functions[name] = f"{name}(...)"
            else:
                # Regular variable
                value_repr = repr(value)
                if len(value_repr) > 100:
                    value_repr = value_repr[:100] + "..."
                variables[name] = f"{type(value).__name__}: {value_repr}"

        # Format output based on filter
        output_lines = []

        if filter_type in ["all", "modules"] and modules:
            output_lines.append("=== Modules ===")
            for name, info in sorted(modules.items()):
                output_lines.append(f"  {name}: {info}")
            output_lines.append("")

        if filter_type in ["all", "classes"] and classes:
            output_lines.append("=== Classes ===")
            for name, info in sorted(classes.items()):
                output_lines.append(f"  {info}")
            output_lines.append("")

        if filter_type in ["all", "functions"] and functions:
            output_lines.append("=== Functions ===")
            for name, sig in sorted(functions.items()):
                output_lines.append(f"  {sig}")
            output_lines.append("")

        if filter_type in ["all", "variables"] and variables:
            output_lines.append("=== Variables ===")
            for name, value_info in sorted(variables.items()):
                output_lines.append(f"  {name}: {value_info}")

        if not output_lines:
            return [types.TextContent(
                type="text",
                text=f"No items of type '{filter_type}' found in namespace"
            )]

        return [types.TextContent(
            type="text",
            text="\n".join(output_lines)
        )]

    elif name == "reset_namespace":
        # Clear all user-defined items from namespace
        user_keys = [k for k in execution_namespace.keys()
                     if not k.startswith('__')]
        for key in user_keys:
            del execution_namespace[key]

        return [types.TextContent(
            type="text",
            text="✓ Namespace reset to initial state"
        )]

    elif name == "get_variable":
        var_name = arguments.get("name", "")

        if var_name not in execution_namespace:
            return [types.TextContent(
                type="text",
                text=f"Variable '{var_name}' not found in namespace"
            )]

        value = execution_namespace[var_name]
        value_type = type(value).__name__
        value_repr = repr(value)

        # Get additional info for certain types
        info_lines = [
            f"Name: {var_name}",
            f"Type: {value_type}",
            f"Value: {value_repr}",
        ]

        # Add size info for collections
        if hasattr(value, '__len__'):
            try:
                info_lines.append(f"Length: {len(value)}")
            except:
                pass

        # Add callable info
        if callable(value):
            import inspect
            if inspect.isfunction(value) or inspect.ismethod(value):
                try:
                    sig = inspect.signature(value)
                    info_lines.append(f"Signature: {var_name}{sig}")

                    # Get docstring
                    doc = inspect.getdoc(value)
                    if doc:
                        info_lines.append(f"Docstring:\n{doc}")
                except:
                    pass

        return [types.TextContent(
            type="text",
            text="\n".join(info_lines)
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
                server_name="python-repl",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
