from argparse import ArgumentParser
import json

parser = ArgumentParser()
parser.add_argument("--input",
                    default="-",
                    help="Conversations JSON file from ChatGPT data export")

parser.add_argument("--start",
                    default=0,
                    help="Start index to process")

parser.add_argument("--max_items",
                    default=-1,
                    help="Maximum number of items to process")

args = parser.parse_args()

if args.input == "-":
    args.input = "/dev/stdin"

contents = open(args.input).read()
data = json.loads(contents)


start = int(args.start)
end = min(start + int(args.max_items), len(data))
data = data[start:end]

#for obj in data:
#  keys = obj["mapping"].keys()
#  values = []
#  for key in keys:
#    values.append(obj["mapping"][key])
#    obj["mapping"] = values



for obj in data:
    obj["mapping"] = list(obj["mapping"].values())

print(json.dumps(data, indent=2))
