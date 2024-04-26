from argparse import ArgumentParser
import json

def filter_message_by(type):
    if type == "roles":
        return lambda message, roles: message["author"]["role"] in roles
    elif type == "content_type":
        return lambda message, content_types: message["content"]["content_type"] in content_types
    else:
        return lambda message, _: True

def filter_conversation_by(type):
    if type == "title":
        return lambda conversation, title: conversation["title"] == title
    elif type == "date":
        return lambda conversation, daterange: conversation["create_time"] >= daterange[0] and conversation["create_time"] <= daterange[1]
    else:
        return lambda conversation, _: True

def process_conversation(data, filter_message_by, conv_fields, msg_fields):
    conv = {key: data[key] for key in conv_fields}
    if "mapping" not in conv_fields or "mapping" not in data:
        return conv
    
    for value in data["mapping"]:
        if filter_message_by(value["message"]):
            msg = {key: value["message"][key] for key in msg_fields}
            conv["mapping"].append(msg)
    return conv

parser = ArgumentParser()
parser.add_argument("--input",
                    default="-",
                    help="Santized conversations JSON file from ChatGPT data export")
parser.add_argument("--stats",
                    action="store_true",
                    help="Output stats")
parser.add_argument("--message-by-args",
                    nargs="+",
                    default=["user", "assistant"],
                    help="Roles to keep")
parser.add_argument("--message-by",
                    default="role",
                    help="Type of message filter (role, content_type, or none)")
parser.add_argument("--conversation-fields",
                    nargs="+",
                    default=["id", "title", "create_time", "update_time", "safe_urls", "is_archived", "mapping"],
                    help="Fields to keep in conversation")
parser.add_argument("--message-fields",
                    nargs="+", 
                    default=["id", "author", "content", "create_time", "update_time"],
                    help="Fields to keep in message")
parser.add_argument("--filter-conversation-by",
                    default="none",
                    help="Type of conversation filter (title, date, or none)")
args = parser.parse_args()

if args.input == "-":
    args.input = "/dev/stdin"

filter_message_by = filter_message_by(args.filter_message_by)
message_by_args = args.message_by_args
conversation_fields = args.conversation_fields
conv_fields = args.conversation_fields
msg_fields = args.message_fields

contents = open(args.input).read()
data = json.loads(contents)
data = [process_conversation(obj, filter_message_by, conv_fields, msg_fields) for obj in data]

if bool(args.stats):
    data = {
        "items": data,
        "processed_items": len(data),
        "total_items": len(data)
    }

print(json.dumps(data, indent=2))
