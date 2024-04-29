import json
import argparse
import re

def load_data(file_path):
    """Load the JSON data from a file."""
    with open(file_path, 'r') as file:
        return json.load(file)

def find_conversations(data, search_field, search_value, use_regex=False, use_keywords=False, include_stats=False, logic='AND'):
    """Find conversations that match the search criteria and optionally calculate stats."""
    matches = []
    
    for doc in data:
        field_value = str(doc.get(search_field, "")).lower()
        if use_regex:
            pattern = re.compile(search_value, re.IGNORECASE)
            if pattern.search(field_value):
                matches.append(doc)
        elif use_keywords:
            keywords = search_value.lower().split()
            if logic == 'AND':
                if all(keyword in field_value for keyword in keywords):
                    matches.append(doc)
            elif logic == 'OR':
                if any(keyword in field_value for keyword in keywords):
                    matches.append(doc)
        else:
            # see if it has a jupter_messages field in one of the nested structures
            # so, look in the doc for the key 'jupyter_messages'

            def __find_jup(a_doc):
              if type(a_doc) == dict:
                  for key in a_doc.keys():
                      if key == 'jupyter_messages':
                          print(json.dumps(doc))
                          exit(1)
                      elif type(a_doc[key]) == dict:
                          __find_jup(a_doc[key])
                      elif type(a_doc[key]) == list:
                          for item in a_doc[key]:
                              __find_jup(item)
              elif type(a_doc) == list:
                  for item in a_doc:
                      __find_jup(item)
            __find_jup(doc)
                
            
            
            if search_value.lower() in field_value:
                matches.append(doc)

    # Prepare output
    output = {"results": matches}
    if include_stats:
        # Compute statistics
        stats = {
            "total_matches": len(matches)
        }
        output["stats"] = stats

    return json.dumps(output)

def main():
    # Setup argparse for command line arguments
    parser = argparse.ArgumentParser(description="Search conversations in a JSON file and output matches as a JSON string.",
                                     epilog="Example usage: \npython search_conversations.py --file /path/to/data.json --field title --value 'test runner' --keywords --logic OR --stats | jq .",
                                     formatter_class=argparse.RawTextHelpFormatter)
    
    parser.add_argument("-f", "--file", dest="file_path", required=True, type=str, help="Path to the JSON file containing conversations.")
    parser.add_argument("-s", "--field", dest="search_field", required=True, choices=['title', 'conversation_id', 'id'],
                        help="The field to search. Choices: 'title', 'conversation_id', 'id'.")
    parser.add_argument("-v", "--value", dest="search_value", required=True, type=str, help="The value to search for in the specified field.")
    parser.add_argument("-r", "--regex", action="store_true", help="Enable regex searching. When enabled, treats 'value' as a regex pattern.")
    parser.add_argument("-k", "--keywords", action="store_true", help="Enable keyword searching. Requires keywords to be present in the field.")
    parser.add_argument("-l", "--logic", choices=['AND', 'OR'], default='AND', help="Logical operation to use when searching with keywords. Default is 'AND'.")
    parser.add_argument("--stats", action="store_true", help="Compute and include statistics about the search results.")

    # Parse arguments
    args = parser.parse_args()

    # Load data
    data = load_data(args.file_path)

    # Find conversations and output as JSON string with optional stats
    result_json = find_conversations(data, args.search_field, args.search_value, args.regex, args.keywords, args.stats, args.logic)
    print(result_json)

if __name__ == "__main__":
    main()
