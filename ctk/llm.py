import os
import requests
from string import Template
from .config import load_ctkrc_config

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