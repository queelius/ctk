from argparse import ArgumentParser
import json

def keep_message(message):
    return message and message["author"]["role"] in ["user", "assistant"]

def transform_header(data):
    return {
        "id": data["id"],
        "title": data["title"],
        "create_time": data["create_time"],
        "update_time": data["update_time"],
        "messages": [],
        "safe_urls": data["safe_urls"],
        #"is_archived": data["is_archived"]
    }

def transform_message(message):
    new_message = {
  #      "parent": message["parent"],
  #      "children": message["children"],
        "message_id": message["id"],
        "role": message["author"]["role"],
        "create_time": message["create_time"],
        "update_time": message["update_time"]
    }
    if message["content"]:
        new_message["content_type"] = message["content"]["content_type"]
        if message["content"].get("parts"):
            new_message["content"] = message["content"].get("parts")[0]
    return new_message

def simplify(data):
    new_data = transform_header(data)    
    #new_data["messages"] = [transform_message(value) for value in data["mapping"] if keep_message(value)]
    for value in data["mapping"]:
        if keep_message(value["message"]):
            new_data["messages"].append(transform_message(value["message"]))
    return new_data

parser = ArgumentParser()
parser.add_argument("--input",
                    default="-",
                    help="Pre-santized conversations JSON file from ChatGPT data export")



args = parser.parse_args()

# this so no such file "-" error... i need to fix this, how do i open stdin?
if args.input == "-":
    args.input = "/dev/stdin"

contents = open(args.input).read()
data = json.loads(contents)
data = [simplify(obj) for obj in data]
print(json.dumps(data, indent=2))
