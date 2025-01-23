import os
import requests
import configparser
from string import Template

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

def query_llm(lib_dir, prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param lib_dir: The directory where the library is located.
    :param prompt: The user query or conversation prompt text.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    file_instr_path = os.path.join(os.path.dirname(__file__), "llm-instructions.md")    

    from string import Template
    
    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    data = {
        "libdir": lib_dir
    }

    instructions = template.safe_substitute(data)
    prompt = instructions + "\n\nQuestion: " + prompt

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()