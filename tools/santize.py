from argparse import ArgumentParser
import json

parser = ArgumentParser()
parser.add_argument("--input",
                    default="-",
                    help="Conversations JSON file from ChatGPT data export")

parser.add_argument("--start",
                    default=0,
                    help="Start index to process")

parser.add_argument("--end",
                    default=-1,
                    help="End index to process. If negative, it will be subtracted from the length of the data.")

parser.add_argument("--message-hashes-only", action="store_true", help="Output hash references for messages in the mappings.")

parser.add_argument("--stats", action="store_true", help="Output stats")

parser.add_argument("--keep-message-hash-keys", action="store_true", help="Keep hash key mappings.")

args = parser.parse_args()

if args.input == "-":
    args.input = "/dev/stdin"

contents = open(args.input).read()
data = json.loads(contents)

start = int(args.start)
if start < 0:
    start = len(data) + start
end = min(int(args.end), len(data)-1)
if end < 0:
    end = len(data) + end
if end < start:
    print("End index is less than start index")
    exit(1)

total_items = len(data)
data = data[start:(end+1)]

for obj in data:
    if bool(args.message_hashes_only):
        obj["mapping"] = list(obj["mapping"].keys())
    elif not bool(args.keep_message_hash_keys):
        obj["mapping"] = list(obj["mapping"].values())

if bool(args.stats):
    data = {
        "items": data,
        "processed_items": len(data),
        "total_items": total_items,
        "start": start,
        "end": end,
    }

print(json.dumps(data, indent=2))


