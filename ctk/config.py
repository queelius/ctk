import configparser
import os

def load_ctkrc_config():
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
