"""
llm.py - Functions to interact with LLMs for CTK using OpenAI's Python library and CTKContext
"""

import os
import json
import subprocess
from string import Template
import logging
from typing import Dict, List, Any, Optional, Union, Callable
from openai import OpenAI
from rich.console import Console
from rich.syntax import Syntax
from rich.prompt import Confirm
from .config import load_ctkrc_config
from .context import CTKContext
from .tools import CTK_TOOLS, parse_tool_calls
from . import operations

console = Console()
logger = logging.getLogger(__name__)

def get_openai_client():
    """
    Create an OpenAI client based on .ctkrc configuration
    
    Returns:
        OpenAI client instance
    """
    endpoint, api_key, _ = load_ctkrc_config()
    
    # Set the base URL from the endpoint
    base_url = endpoint
    
    # Create the client
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    return client

def get_operation_for_tool(function_name, arguments, ctx):
    """
    Get the appropriate operation function for a tool call
    
    Args:
        function_name: Name of the function
        arguments: Arguments to the function
        ctx: CTK context
        
    Returns:
        Tuple of (function, args, kwargs) or None if operation not found
    """
    # Strip 'ctk_' prefix
    op_name = function_name[4:] if function_name.startswith("ctk_") else function_name
    
    if op_name == "list":
        return (
            operations.list_conversations,
            [ctx],
            {
                "fields": arguments.get("fields"),
                "indices": arguments.get("indices")
            }
        )
    
    elif op_name == "search":
        return (
            operations.search_conversations,
            [ctx, arguments["expression"]],
            {
                "fields": arguments.get("fields", ["title"])
            }
        )
    
    elif op_name == "jmespath":
        return (
            operations.execute_jmespath_query,
            [ctx, arguments["query"]],
            {}
        )
    
    elif op_name == "conversation":
        return (
            operations.get_conversation_details,
            [ctx, arguments["indices"]],
            {
                "node_id": arguments.get("node")
            }
        )
    
    elif op_name == "export":
        return (
            operations.export_conversations,
            [ctx],
            {
                "indices": arguments.get("indices"),
                "format": arguments.get("format", "json")
            }
        )
    
    elif op_name == "semantic_network":
        return (
            operations.analyze_semantic_network,
            [ctx],
            {
                "threshold": arguments.get("threshold", 0.5),
                "limit": arguments.get("limit", 1000),
                "algorithm": arguments.get("algorithm", "louvain")
            }
        )
    
    elif op_name == "bridges":
        return (
            operations.find_bridge_conversations,
            [ctx],
            {
                "threshold": arguments.get("threshold", 0.5),
                "top_n": arguments.get("top_n", 10)
            }
        )
    
    elif op_name == "clusters":
        return (
            operations.find_conversation_clusters,
            [ctx],
            {
                "threshold": arguments.get("threshold", 0.5),
                "algorithm": arguments.get("algorithm", "louvain"),
                "resolution": arguments.get("resolution", 1.0)
            }
        )
    
    # For operations not yet implemented to use context
    return None

def chat_llm(lib_dir):
    """
    Instantiates a chatbot that can use CTK commands to interact with the library.
    
    Args:
        lib_dir: The directory where the library is located.
    """
    # Load model and create API client
    _, _, model = load_ctkrc_config()
    client = get_openai_client()
    
    # Create context - conversations will be loaded when needed
    ctx = CTKContext(lib_dir=lib_dir)

    # Load instruction template
    file_instr_path = os.path.join(
        os.path.dirname(__file__), "llm-instructions.md")

    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    instructions = template.safe_substitute({
        "libdir": lib_dir
    })

    # Initialize conversation with system instructions
    messages = [
        {"role": "system", "content": instructions},
        {"role": "system", "content": f"The current library directory is: {lib_dir}"}
    ]

    console.print("[bold green]CTK Chat Assistant[/bold green]")
    console.print("Type 'exit', 'quit', or 'bye' to end the chat session.")
    console.print("Type 'clear' to clear the chat history.")
    console.print("---")

    while True:
        # Get user input
        prompt = console.input("[bold cyan]User:[/bold cyan] ")
        
        # Check for exit commands
        if prompt.lower() in ["exit", "quit", "bye"]:
            console.print("[bold green]Goodbye![/bold green]")
            break
            
        # Check for clear command
        if prompt.lower() == "clear":
            messages = [
                {"role": "system", "content": instructions},
                {"role": "system", "content": f"The current library directory is: {lib_dir}"}
            ]
            console.print("[bold yellow]Chat history cleared.[/bold yellow]")
            continue

        # Add user message to history
        messages.append({"role": "user", "content": prompt})

        # Call the LLM
        try:
            response = call_llm_with_tools(messages, model, client)
            
            # Handle tool calls if present
            if response.tool_calls:
                # Parse the tool calls into command strings
                commands = parse_tool_calls(response.tool_calls)
                
                if commands:
                    console.print("[bold yellow]Generated commands:[/bold yellow]")
                    
                    # Keep track of which tool calls were executed successfully
                    executed_tool_calls = []
                    
                    for i, cmd in enumerate(commands):
                        console.print(Syntax(cmd, "bash", theme="monokai"))
                        
                        # Get the corresponding tool call
                        tool_call = response.tool_calls[i]
                        
                        # Ask for confirmation
                        if Confirm.ask("Execute this command?"):
                            try:
                                # Try to get operation function
                                function_name = tool_call.function.name
                                
                                # Parse arguments
                                try:
                                    function_args = json.loads(tool_call.function.arguments)
                                except TypeError:
                                    function_args = tool_call.function.arguments
                                
                                # Get operation details
                                op_details = get_operation_for_tool(function_name, function_args, ctx)
                                
                                if op_details:
                                    # We have a direct operation - execute it
                                    console.print("[bold green]Executing operation...[/bold green]")
                                    func, args, kwargs = op_details
                                    
                                    try:
                                        result = func(*args, **kwargs)
                                        result_str = json.dumps(result, indent=2)
                                        
                                        messages.append({
                                            "role": "tool", 
                                            "content": result_str,
                                            "tool_call_id": tool_call.id
                                        })
                                        executed_tool_calls.append(tool_call.id)
                                        console.print("[bold green]Operation output:[/bold green]")
                                        console.print(result_str)
                                        
                                    except Exception as e:
                                        error_msg = f"Error executing operation: {str(e)}"
                                        console.print(f"[bold red]{error_msg}[/bold red]")
                                        messages.append({
                                            "role": "tool", 
                                            "content": error_msg,
                                            "tool_call_id": tool_call.id
                                        })
                                        executed_tool_calls.append(tool_call.id)
                                        
                                else:
                                    # Fall back to command-line execution
                                    console.print("[bold yellow]Using command-line execution...[/bold yellow]")
                                    process = subprocess.Popen(
                                        cmd,
                                        shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True
                                    )
                                    stdout, stderr = process.communicate()
                                    
                                    # Add tool response to messages
                                    if stdout:
                                        messages.append({
                                            "role": "tool", 
                                            "content": stdout,
                                            "tool_call_id": tool_call.id
                                        })
                                        executed_tool_calls.append(tool_call.id)
                                        console.print("[bold green]Command output:[/bold green]")
                                        console.print(stdout)
                                        
                                    if stderr:
                                        console.print("[bold red]Command error:[/bold red]")
                                        console.print(stderr)
                                        messages.append({
                                            "role": "tool", 
                                            "content": f"Error: {stderr}",
                                            "tool_call_id": tool_call.id
                                        })
                                        executed_tool_calls.append(tool_call.id)
                                
                            except Exception as e:
                                console.print(f"[bold red]Error executing command:[/bold red] {e}")
                                messages.append({
                                    "role": "tool", 
                                    "content": f"Error executing command: {e}",
                                    "tool_call_id": tool_call.id
                                })
                                executed_tool_calls.append(tool_call.id)
                        else:
                            console.print("[yellow]Command skipped.[/yellow]")
                            messages.append({
                                "role": "tool", 
                                "content": "User chose not to execute this command.",
                                "tool_call_id": tool_call.id
                            })
                            executed_tool_calls.append(tool_call.id)
                
                # Get final response from the model if at least one tool call was executed
                if executed_tool_calls:
                    final_response = call_llm(messages, model, client)
                    console.print(f"[bold green]Assistant:[/bold green] {final_response.content}")
                    
                    # Add assistant response to history
                    messages.append({"role": "assistant", "content": final_response.content})
                    
                else:
                    # No tool calls were executed
                    console.print("[bold yellow]No commands were executed.[/bold yellow]")
                    
                    # Add a note about skipped commands
                    messages.append({
                        "role": "user", 
                        "content": "I chose not to execute any of the suggested commands. Please provide a different approach."
                    })
                    
                    # Get a new response
                    new_response = call_llm(messages, model, client)
                    console.print(