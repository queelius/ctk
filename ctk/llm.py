"""
llm.py - Functions to interact with LLMs for ctk using OpenAI's Python library
"""

import os
import json
import subprocess
from string import Template
import logging
from typing import Dict, List, Any, Optional
from openai import OpenAI
from rich.console import Console
from rich.syntax import Syntax
from rich.prompt import Confirm
from .config import load_ctkrc_config
from .tools import CTK_TOOLS, parse_tool_calls

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

def chat_llm(lib_dir):
    """
    Instantiates a chatbot that can use CTK commands to interact with the library.
    
    Args:
        lib_dir: The directory where the library is located.
    """
    _, _, model = load_ctkrc_config()
    client = get_openai_client()

    #file_instr_path = os.path.join(
    #    os.path.dirname(__file__), "llm-instructions.md")

    # Read the markdown file for instructions
    #with open(file_instr_path, "r") as f:
    #    template = Template(f.read())

    

    #instructions = template.safe_substitute({
    #    "libdir": lib_dir
    #})

    # Initialize conversation with system instructions
    messages = [
        #{"role": "system", "content": instructions},
        #{"role": "system", "content": f"The current library directory is: {lib_dir}"}
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
                #{"role": "system", "content": instructions},
                #{"role": "system", "content": f"The current library directory is: {lib_dir}"}
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
                                # Execute the command
                                console.print("[bold green]Executing command...[/bold green]")
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
                    console.print(f"[bold green]Assistant:[/bold green] {new_response.content}")
                    
                    # Add assistant response to history
                    messages.append({"role": "assistant", "content": new_response.content})
                
            else:
                # Regular response with no tool calls
                console.print(f"[bold green]Assistant:[/bold green] {response.content}")
                
                # Add assistant response to history
                messages.append({"role": "assistant", "content": response.content})
                
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            logger.error(f"Error in chat_llm: {e}", exc_info=True)

def query_llm(lib_dir, prompt):
    """
    Queries an LLM with CTK tools to execute a command based on the query.
    
    Args:
        lib_dir: The directory where the library is located.
        prompt: The user query or conversation prompt text.
        
    Returns:
        The executed command's output or the LLM's response.
    """
    _, _, model = load_ctkrc_config()
    client = get_openai_client()
    
    file_instr_path = os.path.join(
        os.path.dirname(__file__), "llm-instructions.md")

    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    instructions = template.safe_substitute({
        "libdir": lib_dir
    })

    # Create messages with system instructions and user query
    messages = [
        {"role": "system", "content": instructions},
        {"role": "system", "content": f"The current library directory is: {lib_dir}"},
        {"role": "user", "content": prompt}
    ]

    console.print(f"[bold cyan]Query:[/bold cyan] {prompt}")
    
    try:
        # Call the LLM with tools
        response = call_llm_with_tools(messages, model, client)
        
        # Handle tool calls if present
        if response.tool_calls:
            # Parse the tool calls into command strings
            commands = parse_tool_calls(response.tool_calls)
            
            if commands:
                console.print("[bold yellow]Generated commands:[/bold yellow]")
                results = []
                executed_tool_calls = []
                
                for i, cmd in enumerate(commands):
                    console.print(Syntax(cmd, "bash", theme="monokai"))
                    
                    # Get the corresponding tool call
                    tool_call = response.tool_calls[i]
                    
                    # Ask for confirmation
                    if Confirm.ask("Execute this command?"):
                        try:
                            # Execute the command
                            console.print("[bold green]Executing command...[/bold green]")
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
                                results.append(stdout)
                                
                            if stderr:
                                console.print("[bold red]Command error:[/bold red]")
                                console.print(stderr)
                                messages.append({
                                    "role": "tool", 
                                    "content": f"Error: {stderr}",
                                    "tool_call_id": tool_call.id
                                })
                                executed_tool_calls.append(tool_call.id)
                                results.append(stderr)
                        except Exception as e:
                            console.print(f"[bold red]Error executing command:[/bold red] {e}")
                            messages.append({
                                "role": "tool", 
                                "content": f"Error executing command: {e}",
                                "tool_call_id": tool_call.id
                            })
                            executed_tool_calls.append(tool_call.id)
                            results.append(str(e))
                    else:
                        console.print("[yellow]Command skipped.[/yellow]")
                        messages.append({
                            "role": "tool", 
                            "content": "User chose not to execute this command.",
                            "tool_call_id": tool_call.id
                        })
                        executed_tool_calls.append(tool_call.id)
                        results.append("Command skipped")
                
                # Get final response from the model if at least one tool call was executed
                if executed_tool_calls:
                    final_response = call_llm(messages, model, client)
                    console.print(f"[bold green]Assistant:[/bold green] {final_response.content}")
                    
                    return {
                        "commands": commands,
                        "results": results,
                        "response": final_response.content
                    }
                else:
                    # No commands were executed
                    console.print("[bold yellow]No commands were executed.[/bold yellow]")
                    return {
                        "commands": commands,
                        "results": ["No commands executed"],
                        "response": "No commands were executed. Please try a different query."
                    }
            
        # Regular response with no tool calls
        console.print(f"[bold green]Assistant:[/bold green] {response.content}")
        return {
            "response": response.content
        }
            
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logger.error(f"Error in query_llm: {e}", exc_info=True)
        return {
            "error": str(e)
        }

def call_llm_with_tools(messages, model, client=None):
    """
    Call the LLM with tools for function calling using OpenAI's Python library.
    
    Args:
        messages: List of message objects
        model: Model name to use
        client: OpenAI client (optional)
        
    Returns:
        Response object from the LLM
    """
    if client is None:
        client = get_openai_client()
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=CTK_TOOLS,
            tool_choice="auto"
        )
        
        # Return the message from the first choice
        return response.choices[0].message
            
    except Exception as e:
        logger.error(f"Error calling LLM with tools: {e}", exc_info=True)
        raise

def call_llm(messages, model, client=None):
    """
    Call the LLM without tools for follow-up responses using OpenAI's Python library.
    
    Args:
        messages: List of message objects
        model: Model name to use
        client: OpenAI client (optional)
        
    Returns:
        Response object from the LLM
    """
    if client is None:
        client = get_openai_client()
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        
        # Return the message from the first choice
        return response.choices[0].message
            
    except Exception as e:
        logger.error(f"Error calling LLM: {e}", exc_info=True)
        raise