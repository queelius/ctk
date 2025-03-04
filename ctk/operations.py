"""
operations.py - Core operations for CTK using the Context pattern
"""

import os
import re
import json
import jmespath
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from .context import CTKContext

logger = logging.getLogger(__name__)

def list_conversations(ctx: CTKContext, fields: List[str] = None, indices: List[int] = None) -> List[Dict]:
    """
    List conversations with selected fields.
    
    Args:
        ctx: CTK context with conversations
        fields: Fields to include in the output
        indices: Indices of conversations to list
        
    Returns:
        List of conversation summaries with selected fields
    """
    if fields is None:
        fields = ["title", "create_time"]
    
    conversations = ctx.conversations
    
    if indices is None:
        indices = range(len(conversations))
    
    result = []
    for i in indices:
        if i < 0 or i >= len(conversations):
            logger.warning(f"Index {i} out of range")
            continue
            
        conv = conversations[i]
        summary = {"index": i}
        
        for field in fields:
            try:
                value = jmespath.search(field, conv)
                summary[field] = value
            except Exception as e:
                logger.warning(f"Error extracting field {field}: {e}")
                summary[field] = None
                
        result.append(summary)
        
    return result

def search_conversations(ctx: CTKContext, expression: str, fields: List[str] = None) -> List[Dict]:
    """
    Search conversations using regex.
    
    Args:
        ctx: CTK context with conversations
        expression: Regex pattern to search for
        fields: Fields to search in
        
    Returns:
        List of matching conversations
    """
    if fields is None:
        fields = ["title"]
    
    pattern = re.compile(expression, re.IGNORECASE)
    results = []
    
    for i, conv in enumerate(ctx.conversations):
        for field in fields:
            try:
                value = jmespath.search(field, conv)
                
                # Convert to string if needed
                if isinstance(value, (int, float)):
                    value = str(value)
                elif isinstance(value, (list, dict)):
                    value = json.dumps(value)
                elif value is None:
                    continue
                else:
                    value = str(value)
                
                if pattern.search(value):
                    results.append({"index": i, "conversation": conv})
                    break  # Stop after first match in this conversation
            except Exception as e:
                logger.warning(f"Error searching field {field}: {e}")
                
    return results

def execute_jmespath_query(ctx: CTKContext, query: str) -> Any:
    """
    Execute a JMESPath query on conversations.
    
    Args:
        ctx: CTK context with conversations
        query: JMESPath expression to execute
        
    Returns:
        Query result
    """
    try:
        return jmespath.search(query, ctx.conversations)
    except Exception as e:
        logger.error(f"Error executing JMESPath query: {e}")
        raise

def get_conversation_details(ctx: CTKContext, indices: List[int], node_id: str = None) -> List[Dict]:
    """
    Get detailed conversation information.
    
    Args:
        ctx: CTK context with conversations
        indices: Indices of conversations to get
        node_id: Optional terminal node ID
        
    Returns:
        List of conversation details
    """
    result = []
    
    for index in indices:
        conv = ctx.get_conversation(index)
        if not conv:
            continue
            
        # Extract the conversation path
        if node_id:
            # Logic to extract conversation path using the specified node
            # This would need implementation specific to your conversation structure
            pass
            
        result.append({
            "index": index,
            "conversation": conv
        })
        
    return result

def export_conversations(ctx: CTKContext, indices: List[int] = None, format: str = "json") -> Union[str, Dict]:
    """
    Export conversations in various formats.
    
    Args:
        ctx: CTK context with conversations
        indices: Indices of conversations to export
        format: Export format (json, markdown, hugo, zip)
        
    Returns:
        Exported content in requested format
    """
    conversations = ctx.conversations
    
    if indices is None:
        # Export all conversations
        to_export = conversations
    else:
        # Export only specified conversations
        to_export = [conversations[i] for i in indices if i < len(conversations)]
    
    if format == "json":
        return json.dumps(to_export, indent=2)
    elif format == "markdown":
        # Implementation for markdown conversion
        return convert_to_markdown(to_export)
    elif format == "hugo":
        # Implementation for Hugo format
        return convert_to_hugo(to_export)
    elif format == "zip":
        # For zip format, we'd return info about what would be included
        # Actual zip creation would require file I/O
        return {
            "format": "zip", 
            "count": len(to_export),
            "info": "Use ctx.lib_dir for actual file creation"
        }
    else:
        raise ValueError(f"Unsupported export format: {format}")

def merge_libraries(operation: str, lib_contexts: List[CTKContext], output_ctx: CTKContext) -> int:
    """
    Merge multiple conversation libraries.
    
    Args:
        operation: Type of merge operation (union, intersection, difference)
        lib_contexts: List of CTK contexts to merge
        output_ctx: CTK context for output
        
    Returns:
        Number of conversations in the merged result
    """
    # Ensure all contexts have loaded their conversations
    all_conversations = [ctx.conversations for ctx in lib_contexts]
    
    # Extract IDs for operations
    all_ids = []
    id_to_conv = {}
    
    for conv_list in all_conversations:
        ids = []
        for conv in conv_list:
            conv_id = conv.get("id")
            if conv_id:
                ids.append(conv_id)
                id_to_conv[conv_id] = conv
        all_ids.append(set(ids))
    
    # Perform the requested operation
    if operation == "union":
        # Union of all sets
        result_ids = set().union(*all_ids)
    elif operation == "intersection":
        # Intersection of all sets
        result_ids = set(all_ids[0]).intersection(*all_ids[1:]) if all_ids else set()
    elif operation == "difference":
        # Difference: items in first set but not in others
        result_ids = set(all_ids[0]).difference(*all_ids[1:]) if len(all_ids) > 1 else set(all_ids[0])
    else:
        raise ValueError(f"Unsupported merge operation: {operation}")
    
    # Create the merged library
    result_conversations = [id_to_conv[conv_id] for conv_id in result_ids]
    output_ctx.conversations = result_conversations
    
    return len(result_conversations)

def analyze_semantic_network(ctx: CTKContext, threshold: float = 0.5, limit: int = 1000, 
                           algorithm: str = "louvain") -> Dict:
    """
    Analyze the semantic network of conversations.
    
    Args:
        ctx: CTK context with conversations
        threshold: Similarity threshold for creating edges
        limit: Maximum number of conversations to analyze
        algorithm: Clustering algorithm
        
    Returns:
        Network analysis results
    """
    # This is a placeholder for semantic network analysis
    # The actual implementation would need semantic_network.py
    
    return {
        "num_conversations": min(len(ctx.conversations), limit),
        "threshold": threshold,
        "algorithm": algorithm,
        "message": "This function requires integration with semantic_network.py"
    }

def find_bridge_conversations(ctx: CTKContext, threshold: float = 0.5, top_n: int = 10) -> List[Dict]:
    """
    Find bridge conversations connecting different topic clusters.
    
    Args:
        ctx: CTK context with conversations
        threshold: Similarity threshold for creating edges
        top_n: Number of top bridge conversations to return
        
    Returns:
        List of bridge conversations
    """
    # This is a placeholder for bridge analysis
    # The actual implementation would need semantic_network.py
    
    return [{
        "index": i,
        "id": conv.get("id", ""),
        "title": conv.get("title", "Untitled"),
        "betweenness": 0.0  # Placeholder
    } for i, conv in enumerate(ctx.conversations[:top_n])]

def find_conversation_clusters(ctx: CTKContext, threshold: float = 0.5, 
                             algorithm: str = "louvain", 
                             resolution: float = 1.0) -> Dict:
    """
    Find clusters of related conversations.
    
    Args:
        ctx: CTK context with conversations
        threshold: Similarity threshold for creating edges
        algorithm: Clustering algorithm
        resolution: Resolution parameter for community detection
        
    Returns:
        Cluster analysis results
    """
    # This is a placeholder for cluster analysis
    # The actual implementation would need semantic_network.py
    
    return {
        "num_conversations": len(ctx.conversations),
        "num_clusters": 0,  # Placeholder
        "algorithm": algorithm,
        "resolution": resolution,
        "message": "This function requires integration with semantic_network.py"
    }

# Helper functions

def convert_to_markdown(conversations: List[Dict]) -> str:
    """Convert conversations to Markdown format"""
    result = []
    
    for conv in conversations:
        title = conv.get("title", "Untitled Conversation")
        result.append(f"# {title}\n")
        
        # Add metadata
        create_time = conv.get("create_time", "Unknown")
        result.append(f"**Date**: {create_time}\n")
        
        # Process messages
        if "mapping" in conv:
            result.append("\n## Conversation\n")
            # This would need implementation specific to your conversation structure
            result.append("*Conversation content would be processed here*\n")
        
        result.append("\n---\n\n")
        
    return "".join(result)

def convert_to_hugo(conversations: List[Dict]) -> Dict:
    """Convert conversations to Hugo format"""
    # This is a placeholder for Hugo conversion
    # The actual implementation would need to create Hugo-compatible content
    
    return {
        "count": len(conversations),
        "message": "Hugo conversion would generate front matter and content for each conversation"
    }