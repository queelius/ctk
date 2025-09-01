"""
Utility functions for CTK
"""

import re
from typing import Optional


def slugify(text: str, max_length: Optional[int] = None) -> str:
    """
    Convert text to a URL-friendly slug
    
    Args:
        text: Text to slugify
        max_length: Maximum length of slug
    
    Returns:
        Slugified text
    
    Examples:
        >>> slugify("Hello World!")
        'hello-world'
        >>> slugify("GPT-4 Turbo (Latest)")
        'gpt-4-turbo-latest'
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Replace spaces and special characters with hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    # Limit length if specified
    if max_length:
        text = text[:max_length].rstrip('-')
    
    return text


def extract_domain(url: str) -> str:
    """
    Extract domain from URL
    
    Examples:
        >>> extract_domain("https://chat.openai.com/share/abc")
        'openai.com'
    """
    import re
    pattern = r'https?://(?:www\.)?([^/]+)'
    match = re.search(pattern, url)
    if match:
        domain = match.group(1)
        # Get base domain (last two parts)
        parts = domain.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
    return url


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_filesize(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    
    Examples:
        >>> format_filesize(1024)
        '1.0 KB'
        >>> format_filesize(1048576)
        '1.0 MB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def count_tokens_estimate(text: str, model: str = "gpt-3.5") -> int:
    """
    Estimate token count for text
    
    This is a rough estimate based on average tokenization patterns.
    For exact counts, use the tiktoken library.
    
    Args:
        text: Text to count tokens for
        model: Model name for estimation
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Rough estimates based on OpenAI's tokenization
    # GPT-3.5/4 average: ~4 characters per token
    # Code and special characters: ~3 characters per token
    
    # Check if text contains code
    has_code = any(indicator in text for indicator in [
        'def ', 'function ', 'class ', 'import ', 'const ', 'var ',
        '```', 'return ', 'if ', 'for ', 'while '
    ])
    
    if has_code:
        # Code tends to have more tokens
        chars_per_token = 3
    else:
        # Regular text
        chars_per_token = 4
    
    # Estimate based on character count
    estimated_tokens = len(text) / chars_per_token
    
    # Add buffer for special tokens
    estimated_tokens *= 1.1
    
    return int(estimated_tokens)


def estimate_cost(token_count: int, model: str = "gpt-3.5-turbo") -> float:
    """
    Estimate cost based on token count and model
    
    Args:
        token_count: Number of tokens
        model: Model name
    
    Returns:
        Estimated cost in USD
    """
    # Pricing as of 2024 (per 1K tokens)
    pricing = {
        # OpenAI
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        
        # Anthropic (approximate)
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        
        # Default
        "default": {"input": 0.001, "output": 0.002}
    }
    
    # Get pricing for model
    model_key = None
    for key in pricing:
        if key in model.lower():
            model_key = key
            break
    
    if not model_key:
        model_key = "default"
    
    # Assume 50/50 input/output split for conversation
    input_tokens = token_count // 2
    output_tokens = token_count // 2
    
    cost = (input_tokens * pricing[model_key]["input"] / 1000 +
            output_tokens * pricing[model_key]["output"] / 1000)
    
    return round(cost, 4)