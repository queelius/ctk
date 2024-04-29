import logging
from argparse import ArgumentParser
import json

def get_messages(conv):
    if "mapping" in conv:
        return conv["mapping"]
    else:
        return []

def get_messages(conv):
    msgs = get_mapping(conv)
    if has_mapping(conv) and "message" in conv["mapping"]:
        return conv["mapping"]["message"]
    else:
        return []

def get_role(msg):
    if "author" not in msg or "role" not in msg["author"]:
        return None
    else:
        return msg["author"]["role"]

parser = ArgumentParser()
parser.add_argument("--input",
                    default="-",
                    help="Santized conversations JSON file from ChatGPT data export")
parser.add_argument("--log-level",
                    default="INFO",
                    choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
                    help="Log level")
parser.add_argument("--message-roles",
                    nargs="+",
                    default=["user", "assistant"],
                    help="Roles to keep")
parser.add_argument("--conversation-fields",
                    nargs="+",
                    default=["id", "title", "create_time", "update_time", "mapping"],
                    help="Fields to remove in conversation sessions")
parser.add_argument("--message-fields",
                    nargs="+", 
                    default=["id", "author", "content", "create_time", "update_time"],
                    help="Fields to remove in messages")

args = parser.parse_args()

if args.input == "-":
    args.input = "/dev/stdin"

numeric_level = getattr(logging, args.log_level.upper(), None)
logging.basicConfig(level=numeric_level)

data = open(args.input).read()
convs = json.loads(data)

# check to see if `convs` is a list or a single conversation
if isinstance(convs, dict):
    convs = [convs]

if not isinstance(convs, list):
    logging.error("Invalid data format")
    exit(1)

new_convs = []
for conv in convs:
    logging.debug(f"Processing conversation {conv['id']}")

    if args.conversation_fields:
        new_conv = {key: conv[key] for key in conv if key in args.conversation_fields}
    else:
        new_conv = conv
        
    mapping = get_mapping(new_conv)

    if args.message_roles:
        new_msgs = []
        for msg in get_messages(new_conv)
            logging.debug(f"Processing message {msg['id']}")
            if get_role(msg) in args.keep_message_roles:
                new_msgs.append(get_role(msg))

        
print(json.dumps(convs, indent=2))
