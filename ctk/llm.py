import os
import requests
from string import Template
from .config import load_ctkrc_config
from rich.console import Console

console = Console()


def chat_llm(lib_dir):
    """
    Instantiates a chatbot at the endpoint in the ctkrc config file.

    The chatbot can use any of the functions in this library as tools,
    and can return the results of those functions in the response. It is also
    prompted with the `llm-instructions.md` file, which also provides
    information about how the LLM might use the functions / API.

    :param lib_dir: The directory where the library is located.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    file_instr_path = os.path.join(
        os.path.dirname(__file__), "llm-instructions.md")

    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    instructions = template.safe_substitute({
        "libdir": lib_dir
    })

    while True:

        prompt = input("User: ")

        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            resp = requests.post(endpoint, headers=headers, json=data)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise SystemError(f"Error calling LLM endpoint: {e}")

        console.print("assistant: ", resp.json()[
                      "choices"][0]["message"]["content"])


def query_llm(lib_dir, prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param lib_dir: The directory where the library is located.
    :param prompt: The user query or conversation prompt text.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()
    print(f"{endpoint}, {api_key}, {model}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    file_instr_path = os.path.join(
        os.path.dirname(__file__), "llm-instructions.md")

    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    instructions = template.safe_substitute({
        "libdir": lib_dir
    })
    print(instructions)
    prompt = instructions + "\n\nQuestion: " + prompt

    data = {
        "model": model,
        "prompt": prompt,
        #"stream": False,
        #"format": "json"
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=data)
        print(resp)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    print("test")


    return resp.json()
