"""
MCP (Model Context Protocol) client integration.

Provides MCP server management and tool calling capabilities.
"""

import asyncio
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json
from concurrent.futures import Future

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class MCPServer:
    """Configuration for an MCP server"""
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    description: Optional[str] = None


@dataclass
class MCPTool:
    """Represents an MCP tool"""
    name: str
    description: Optional[str]
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    server_name: str


@dataclass
class MCPToolResult:
    """
    Structured representation of an MCP tool result.

    This provides both raw access to the result and formatted versions
    for different consumers (humans vs LLMs).
    """
    raw_result: Any  # The CallToolResult object
    is_error: bool
    error_message: Optional[str] = None

    # Content extracted from result
    text_content: Optional[str] = None
    structured_content: Optional[Dict[str, Any]] = None
    content_items: Optional[List[Any]] = None

    def for_display(self) -> str:
        """Format result for human display"""
        if self.is_error:
            return f"Error: {self.error_message}"

        if self.structured_content:
            import json
            return json.dumps(self.structured_content, indent=2)

        if self.text_content:
            return self.text_content

        if self.content_items:
            return "\n".join(str(item) for item in self.content_items)

        return "(empty result)"

    def for_llm(self) -> Dict[str, Any]:
        """
        Format result for LLM consumption.

        Returns structured data that an LLM can parse and reason about.
        """
        result = {
            "success": not self.is_error,
        }

        if self.is_error:
            result["error"] = self.error_message
        else:
            if self.structured_content:
                result["data"] = self.structured_content
            elif self.text_content:
                result["text"] = self.text_content
            elif self.content_items:
                result["content"] = self.content_items

        return result


class MCPClient:
    """
    MCP client for connecting to and interacting with MCP servers.

    Manages multiple server connections and provides tool discovery/calling.
    """

    def __init__(self):
        """Initialize MCP client"""
        self.servers: Dict[str, MCPServer] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.stdio_contexts: Dict[str, Any] = {}  # Store stdio context managers
        self.session_contexts: Dict[str, Any] = {}  # Store session context managers
        self.tools_cache: Dict[str, List[MCPTool]] = {}

        # Create dedicated event loop in background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        """Run the event loop in a background thread"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit_async(self, coro):
        """Submit a coroutine to run in the background loop"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()  # Block until complete

    def add_server(self, server: MCPServer):
        """Add an MCP server configuration"""
        self.servers[server.name] = server

    def remove_server(self, name: str):
        """Remove an MCP server configuration"""
        # Disconnect if connected
        if name in self.sessions:
            asyncio.run(self.disconnect_server(name))

        if name in self.servers:
            del self.servers[name]

    def list_servers(self) -> List[MCPServer]:
        """List all configured servers"""
        return list(self.servers.values())

    def connect_server(self, name: str) -> bool:
        """
        Connect to an MCP server (synchronous wrapper).

        Args:
            name: Server name

        Returns:
            True if successful, False otherwise
        """
        return self._submit_async(self._connect_server(name))

    async def _connect_server(self, name: str) -> bool:
        """
        Connect to an MCP server.

        Args:
            name: Server name

        Returns:
            True if successful, False otherwise
        """
        if name not in self.servers:
            raise ValueError(f"Server '{name}' not configured")

        if name in self.sessions:
            # Already connected
            return True

        server = self.servers[name]

        try:
            # Create server parameters
            server_params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=server.env
            )

            # Establish connection - keep context manager
            stdio_ctx = stdio_client(server_params)
            read, write = await stdio_ctx.__aenter__()
            self.stdio_contexts[name] = stdio_ctx

            # Create session - keep context manager
            session_ctx = ClientSession(read, write)
            session = await session_ctx.__aenter__()
            self.session_contexts[name] = session_ctx
            self.sessions[name] = session

            # Initialize connection
            await session.initialize()

            # Cache available tools
            await self._refresh_tools(name)

            return True

        except Exception as e:
            # Clean up on error
            await self._cleanup_connection(name)
            raise RuntimeError(f"Failed to connect to server '{name}': {e}")

    async def _cleanup_connection(self, name: str):
        """Clean up connection resources"""
        if name in self.session_contexts:
            try:
                await self.session_contexts[name].__aexit__(None, None, None)
            except:
                pass
            del self.session_contexts[name]

        if name in self.sessions:
            del self.sessions[name]

        if name in self.stdio_contexts:
            try:
                await self.stdio_contexts[name].__aexit__(None, None, None)
            except:
                pass
            del self.stdio_contexts[name]

        if name in self.tools_cache:
            del self.tools_cache[name]

    def disconnect_server(self, name: str):
        """Disconnect from an MCP server (synchronous wrapper)"""
        return self._submit_async(self._disconnect_server(name))

    async def _disconnect_server(self, name: str):
        """Disconnect from an MCP server"""
        await self._cleanup_connection(name)

    async def _refresh_tools(self, server_name: str):
        """Refresh the tools cache for a server"""
        if server_name not in self.sessions:
            return

        session = self.sessions[server_name]

        try:
            tools_response = await session.list_tools()
            tools = []

            for tool in tools_response.tools:
                tools.append(MCPTool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.inputSchema,
                    output_schema=getattr(tool, 'outputSchema', None),
                    server_name=server_name
                ))

            self.tools_cache[server_name] = tools

        except Exception as e:
            import traceback
            print(f"Warning: Failed to list tools from '{server_name}': {e}")
            print("Traceback:")
            traceback.print_exc()
            self.tools_cache[server_name] = []

    def get_all_tools(self) -> List[MCPTool]:
        """Get all available tools from all connected servers"""
        all_tools = []
        for tools in self.tools_cache.values():
            all_tools.extend(tools)
        return all_tools

    def get_server_tools(self, server_name: str) -> List[MCPTool]:
        """Get tools from a specific server"""
        return self.tools_cache.get(server_name, [])

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPToolResult:
        """
        Call an MCP tool (synchronous wrapper).

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            MCPToolResult with structured access to the result
        """
        return self._submit_async(self._call_tool(tool_name, arguments))

    async def _call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPToolResult:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        # Find which server has this tool
        server_name = None
        for name, tools in self.tools_cache.items():
            if any(t.name == tool_name for t in tools):
                server_name = name
                break

        if not server_name:
            raise ValueError(f"Tool '{tool_name}' not found in any connected server")

        if server_name not in self.sessions:
            raise RuntimeError(f"Server '{server_name}' is not connected")

        session = self.sessions[server_name]

        try:
            result = await session.call_tool(tool_name, arguments or {})

            # CallToolResult has:
            # - content: list[TextContent | ImageContent | ...]
            # - structuredContent: dict | None
            # - isError: bool
            # - meta: dict | None

            # Check if it's an error
            if result.isError:
                error_text = ""
                for item in result.content:
                    if hasattr(item, 'text'):
                        error_text += item.text
                return MCPToolResult(
                    raw_result=result,
                    is_error=True,
                    error_message=error_text
                )

            # Extract content based on what's available
            text_parts = []
            content_items = []

            for item in result.content:
                if hasattr(item, 'text'):
                    # TextContent
                    text_parts.append(item.text)
                    content_items.append({"type": "text", "text": item.text})
                elif hasattr(item, 'data'):
                    # ImageContent, AudioContent
                    mime = getattr(item, 'mimeType', 'unknown')
                    content_items.append({
                        "type": item.type,
                        "mimeType": mime,
                        "data": "(base64 data)"
                    })
                elif hasattr(item, 'uri'):
                    # ResourceLink, EmbeddedResource
                    content_items.append({
                        "type": "resource",
                        "uri": str(item.uri)
                    })

            # Combine text parts
            text_content = "\n".join(text_parts) if text_parts else None

            return MCPToolResult(
                raw_result=result,
                is_error=False,
                text_content=text_content,
                structured_content=result.structuredContent,
                content_items=content_items if content_items else None
            )

        except Exception as e:
            return MCPToolResult(
                raw_result=None,
                is_error=True,
                error_message=str(e)
            )

    async def list_resources(self, server_name: str) -> List[Any]:
        """List resources from a specific server"""
        if server_name not in self.sessions:
            raise RuntimeError(f"Server '{server_name}' is not connected")

        session = self.sessions[server_name]

        try:
            resources_response = await session.list_resources()
            return resources_response.resources
        except Exception as e:
            raise RuntimeError(f"Failed to list resources: {e}")

    async def read_resource(self, server_name: str, uri: str) -> tuple[Any, str]:
        """
        Read a resource from a specific server.

        Args:
            server_name: Server name
            uri: Resource URI

        Returns:
            Tuple of (content, mime_type)
        """
        if server_name not in self.sessions:
            raise RuntimeError(f"Server '{server_name}' is not connected")

        session = self.sessions[server_name]

        try:
            content, mime_type = await session.read_resource(uri)
            return content, mime_type
        except Exception as e:
            raise RuntimeError(f"Failed to read resource: {e}")

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected"""
        return server_name in self.sessions

    def get_connected_servers(self) -> List[str]:
        """Get list of connected server names"""
        return list(self.sessions.keys())

    def get_tools_as_dicts(self) -> List[Dict[str, Any]]:
        """
        Get all tools in a generic dictionary format.

        Returns a provider-agnostic list of tool definitions that can be
        converted to any provider's format via provider.format_tools_for_api()

        Returns:
            List of dicts with 'name', 'description', 'input_schema'
        """
        all_tools = self.get_all_tools()
        tool_dicts = []

        for tool in all_tools:
            tool_dicts.append({
                'name': tool.name,
                'description': tool.description or f"Tool: {tool.name}",
                'input_schema': tool.input_schema,
                'output_schema': tool.output_schema
            })

        return tool_dicts


# Synchronous wrapper functions for use in non-async contexts

def run_async(coro):
    """
    Helper to run async code from sync context.

    Uses asyncio.run() which creates a fresh event loop each time,
    avoiding conflicts with any existing loops.
    """
    return asyncio.run(coro)
