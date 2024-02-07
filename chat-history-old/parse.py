import json

def parse_conversations(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)

    parsed_conversations = []
    for conversation in data:
        conversation_id = conversation.get('conversation_id')
        messages = []
        mapping = conversation.get('mapping', {})
        
        for message_key, message_data in mapping.items():
            message_content = message_data.get('message')
            if message_content:
                author_info = message_content.get('author')
                author_role = author_info.get('role', 'unknown') if author_info else 'unknown'

                content_info = message_content.get('content')
                content_parts = content_info.get('parts', []) if content_info else []
                
                # Handle complex content_parts
                content = ' '.join([part if isinstance(part, str) else str(part) for part in content_parts])
                
                create_time = message_content.get('create_time')

                messages.append({
                    'message_id': message_key,
                    'author': author_role,
                    'timestamp': create_time,
                    'content': content
                })

        if conversation_id:
            parsed_conversations.append({
                'conversation_id': conversation_id,
                'messages': messages
            })

    return parsed_conversations

# pretty print the parsed data
def pretty_print_json(data):
    print(json.dumps(data, indent=2))

#    for conversation in data:
#        print(f"Conversation ID: {conversation['conversation_id']}")
#        for message in conversation['messages']:
#            print(f"\tMessage ID: {message['message_id']}, Author: {message['author']}, Timestamp: {message['timestamp']}, Content: {message['content']}")

if __name__ == "__main__":
#    parsed_data = parse_conversations('data/conversations.json')

    # this is a list of dicts i think. let's look at the first dict
    #print(parsed_data[0])
 #   for x in parsed_data:
  #      print(x.keys())

    file_path = 'data/conversations.json'
    with open(file_path, 'r') as file:
        data = json.load(file)

    print(data[0].keys())
