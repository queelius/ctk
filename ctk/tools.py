"""
tools.py - Tool and function definitions for CTK's LLM integration
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Define the available CTK commands as tools
CTK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ctk_list",
            "description": "List conversations in the ctk library",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices of conversations to list. If omitted, list all conversations."
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to include in the output (e.g., title, update_time, model)"
                    }
                },
                "required": ["libdir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_search",
            "description": "Search for conversations using regex",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "expression": {
                        "type": "string",
                        "description": "Regex expression to search for"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to search in (e.g., title, content)"
                    },
                    "json": {
                        "type": "boolean",
                        "description": "Output as JSON instead of formatted text"
                    }
                },
                "required": ["libdir", "expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_jmespath",
            "description": "Execute a JMESPath query on the conversations",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "query": {
                        "type": "string",
                        "description": "JMESPath expression to execute"
                    }
                },
                "required": ["libdir", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_conversation",
            "description": "Display specific conversations by index",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices of conversations to display"
                    },
                    "node": {
                        "type": "string",
                        "description": "Node ID that indicates the terminal node of a conversation path"
                    },
                    "json": {
                        "type": "boolean",
                        "description": "Output the conversation in JSON format"
                    }
                },
                "required": ["libdir", "indices"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_export",
            "description": "Export conversations in various formats",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices of conversations to export"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "hugo", "zip"],
                        "description": "Output format"
                    }
                },
                "required": ["libdir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_merge",
            "description": "Merge multiple ctk libraries",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["union", "intersection", "difference"],
                        "description": "Type of merge operation"
                    },
                    "libdirs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of library directories to merge"
                    },
                    "output": {
                        "type": "string",
                        "description": "Output library directory"
                    }
                },
                "required": ["operation", "libdirs", "output"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_dash",
            "description": "Launch Streamlit dashboard for library exploration",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    }
                },
                "required": ["libdir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_semantic_network",
            "description": "Build and analyze a semantic network of conversations",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Limit the number of conversations to analyze"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Similarity threshold for creating edges"
                    },
                    "model": {
                        "type": "string",
                        "description": "API embedding model to use"
                    },
                    "algorithm": {
                        "type": "string",
                        "enum": ["louvain", "leiden", "spectral"],
                        "description": "Clustering algorithm"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["html", "png", "graphml"],
                        "description": "Output format for visualization"
                    }
                },
                "required": ["libdir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_bridges",
            "description": "Find bridge conversations connecting different topic clusters",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Similarity threshold for creating edges"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top bridge conversations to return"
                    },
                    "model": {
                        "type": "string",
                        "description": "API embedding model to use"
                    }
                },
                "required": ["libdir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ctk_clusters",
            "description": "Find clusters of related conversations",
            "parameters": {
                "type": "object",
                "properties": {
                    "libdir": {
                        "type": "string",
                        "description": "Path to the ctk library directory"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Similarity threshold for creating edges"
                    },
                    "algorithm": {
                        "type": "string",
                        "enum": ["louvain", "leiden", "spectral"],
                        "description": "Clustering algorithm"
                    },
                    "resolution": {
                        "type": "number",
                        "description": "Resolution parameter for community detection"
                    },
                    "model": {
                        "type": "string",
                        "description": "API embedding model to use"
                    }
                },
                "required": ["libdir"]
            }
        }
    }
]

def function_to_command(function_name: str, arguments: Dict[str, Any]) -> str:
    """
    Convert a function call to a command line string
    
    Args:
        function_name: Name of the function that was called
        arguments: Arguments passed to the function
        
    Returns:
        Command line string
    """
    # Strip the 'ctk_' prefix from function name
    command = function_name[4:] if function_name.startswith("ctk_") else function_name
    
    # Start with the base command
    cmd = f"ctk {command}"
    
    # Handle special cases for each command
    if command == "list":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle indices if provided
        if "indices" in arguments and arguments["indices"]:
            indices_str = " ".join(str(idx) for idx in arguments["indices"])
            cmd += f" --indices {indices_str}"
            
        # Handle fields if provided
        if "fields" in arguments and arguments["fields"]:
            fields_str = " ".join(arguments["fields"])
            cmd += f" --fields {fields_str}"
            
    elif command == "search":
        # Handle libdir and expression
        cmd += f" {arguments['libdir']} {arguments['expression']}"
        
        # Handle fields if provided
        if "fields" in arguments and arguments["fields"]:
            fields_str = " ".join(arguments["fields"])
            cmd += f" --fields {fields_str}"
            
        # Handle JSON output flag
        if "json" in arguments and arguments["json"]:
            cmd += " --json"
            
    elif command == "jmespath":
        # Handle libdir and query
        cmd += f" {arguments['libdir']} {arguments['query']}"
        
    elif command == "conversation":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle indices
        indices_str = " ".join(str(idx) for idx in arguments["indices"])
        cmd += f" {indices_str}"
        
        # Handle node if provided
        if "node" in arguments and arguments["node"]:
            cmd += f" --node {arguments['node']}"
            
        # Handle JSON output flag
        if "json" in arguments and arguments["json"]:
            cmd += " --json"
            
    elif command == "export":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle indices if provided
        if "indices" in arguments and arguments["indices"]:
            indices_str = " ".join(str(idx) for idx in arguments["indices"])
            cmd += f" {indices_str}"
            
        # Handle format if provided
        if "format" in arguments and arguments["format"]:
            cmd += f" --format {arguments['format']}"
            
    elif command == "merge":
        # Handle operation
        cmd += f" {arguments['operation']}"
        
        # Handle libdirs
        libdirs_str = " ".join(arguments["libdirs"])
        cmd += f" {libdirs_str}"
        
        # Handle output
        cmd += f" -o {arguments['output']}"
        
    elif command == "dash":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
    elif command == "semantic_network":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle optional arguments
        if "limit" in arguments:
            cmd += f" --limit {arguments['limit']}"
        if "threshold" in arguments:
            cmd += f" --threshold {arguments['threshold']}"
        if "model" in arguments:
            cmd += f" --model {arguments['model']}"
        if "algorithm" in arguments:
            cmd += f" --algorithm {arguments['algorithm']}"
        if "output_format" in arguments:
            cmd += f" --output-format {arguments['output_format']}"
            
    elif command == "bridges":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle optional arguments
        if "threshold" in arguments:
            cmd += f" --threshold {arguments['threshold']}"
        if "top_n" in arguments:
            cmd += f" --top-n {arguments['top_n']}"
        if "model" in arguments:
            cmd += f" --model {arguments['model']}"
            
    elif command == "clusters":
        # Handle libdir
        cmd += f" {arguments['libdir']}"
        
        # Handle optional arguments
        if "threshold" in arguments:
            cmd += f" --threshold {arguments['threshold']}"
        if "algorithm" in arguments:
            cmd += f" --algorithm {arguments['algorithm']}"
        if "resolution" in arguments:
            cmd += f" --resolution {arguments['resolution']}"
        if "model" in arguments:
            cmd += f" --model {arguments['model']}"
    
    # Escape any special shell characters in the command
    # This is a simple implementation - a production version should be more careful
    cmd = cmd.replace('"', '\\"')
    
    return cmd

def parse_tool_calls(tool_calls):
    """
    Parse tool calls from the OpenAI response
    
    Args:
        tool_calls: Tool calls from the LLM response
        
    Returns:
        List of parsed commands
    """
    commands = []
    
    for tool in tool_calls:
        try:
            function_name = tool.function.name
            
            # Parse the arguments
            try:
                # For OpenAI Python client, arguments is already a string
                function_args = json.loads(tool.function.arguments)
            except TypeError:
                # In case arguments is already a dict
                function_args = tool.function.arguments
            
            # Convert to command string
            cmd = function_to_command(function_name, function_args)
            commands.append(cmd)
            
        except Exception as e:
            logger.error(f"Error parsing tool call: {e}", exc_info=True)
            continue
            
    return commands