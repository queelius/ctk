import configparser
import os

def load_ctkrc_config(model: str = "gpt-3.5-turbo"):
    """
    Loads configuration from ~/.ctkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.ctkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.ctkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.ctkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )

    return endpoint, api_key, model

def load_embeddings_config(model: str = "text-embedding-ada-002"):
    """
    Loads embedding configuration from ~/.ctkrc.
    
    If the [embeddings] section exists, use it;
    otherwise, fall back to [llm] section for backward compatibility.
    """
    config_path = os.path.expanduser("~/.ctkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    # First try to use dedicated embeddings section
    if "embeddings" in parser:
        endpoint = parser["embeddings"].get("endpoint", "")
        api_key = parser["embeddings"].get("api_key", "")
        model = parser["embeddings"].get("model", model)
    # Fall back to LLM section
    elif "llm" in parser:
        endpoint = parser["llm"].get("endpoint", "")
        api_key = parser["llm"].get("api_key", "")
        model = parser["llm"].get("model", model)
        
        # If endpoint is for chat/completions, update it for embeddings
        if "chat/completions" in endpoint or "engines" in endpoint:
            if "openai.com" in endpoint:
                endpoint = "https://api.openai.com/v1/embeddings"
            else:
                # For custom endpoints like Azure, try to get base URL
                base_url = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
                endpoint = f"{base_url}/v1/embeddings"
    else:
        raise ValueError(
            "Config file ~/.ctkrc is missing both [embeddings] and [llm] sections. "
            "Please add at least one with 'endpoint' and 'api_key' keys."
        )

    if not endpoint or not api_key:
        raise ValueError(
            "Please make sure your config section in ~/.ctkrc "
            "includes both 'endpoint' and 'api_key' keys."
        )

    return endpoint, api_key, model