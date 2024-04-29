import os
import json
from anytree import Node, RenderTree, find, PreOrderIter
from anytree.exporter import DotExporter
import graphviz


# Function to load JSON data into an anytree structure
def load_json_to_anytree(json_data):
    nodes = {}
    
    # First pass: create all nodes
    for key, value in json_data.items():
        node_id = key
        if node_id not in nodes:
            nodes[node_id] = Node(name=node_id,
                                  parent=None,
                                  children=[],
                                  payload=value['message'])
    
    # Second pass: establish parent-child relationships
    for key, value in json_data.items():
        node_id = key
        parent_id = value['parent']
        if parent_id and parent_id in nodes:
            nodes[node_id].parent = nodes[parent_id]
        for child_id in value.get('children', []):
            if child_id in nodes:
                nodes[child_id].parent = nodes[node_id]
    
    return nodes

def flatten_conversations(tree): 
    paths = []
    for leaf in [node for node in PreOrderIter(tree) if node.is_leaf]:
        path = []
        current = leaf
        while current is not None:
            path.append(current)
            current = current.parent
        paths.append(path[::-1])
    return paths


def flatten_conversation(conversation, roles = ['user', 'assistant']):
    def flatten(node):
        if not (node.payload and 'author' in node.payload and 'content' in node.payload):
            return None
        
        author = node.payload['author']
        content = node.payload['content']

        if author.get('role') not in roles or 'parts' not in content or not content['parts']:
            return None
        
        parts = content['parts']
        parts = [part for part in parts if part]
        if not parts:
            return None

        msg = '\n'.join(parts)
        return f"{author.get('role', '')}: {msg}\n"
    
    conversation_nodes = []
    for node in conversation:
        txt = flatten(node)
        if txt is not None:
            conversation_nodes.append((node, txt))
    return conversation_nodes


def render_tree(root,
                nodenamefunc,
                filename='tree.png'):
    """
    Render the tree to an image file. The filename should include the
    format extension (e.g., 'tree.png').

    :param root: Root node of the tree.        
    :param nodenamefunc: Function to generate node names.
    :param filename: Name of the output file.

    :return: None
    """
    format = filename.split('.')[-1]
    base = filename.split('.')[0]
    print(f"Rendering tree to {filename}")
    
    DotExporter(node = root,
                nodenamefunc = nodenamefunc).to_dotfile(f"{base}.dot")
    
    if format != "dot":
        graphviz.render('dot', format = format, filepath = f"{base}.dot", outfile = filename)
        os.remove(f"{base}.dot")
    print(f"Tree rendered and saved as {filename}")

if __name__ == "__main__": 

    data = open("export/conversations.json").read()
    json_data = json.loads(data)

    #json_data = json_data[1120]["mapping"]
    json_data = json_data[0]["mapping"]

    # Load the tree from JSON
    nodes = load_json_to_anytree(json_data)
    root_node = None
    for node in nodes.values():
        if node.parent is None:
            root_node = node
            break


    # Function to handle the node
    def handle(node):
        if node.payload is not None:
            txt = node.payload['content']['parts'][0]
            # let's trim to 100 characters and remove newlines
            txt = txt.replace("\n", " ")
            if len(txt) > 50:
                txt = txt[:50] + "..."
            return txt
        return node.name
        

    # Print the tree structure
    #for pre, fill, node in RenderTree(root_node):
    #    print("%s%s" % (pre, handle(node)))

    #conversations = flatten_conversations(root_node)

    # just print the txt in the conversation nodes
    #for node, txt in flatten_conversation(conversations[0]):
    #    print(txt, end="")


    # Render the tree to an image file
    #render_tree(root_node, filename='tree.png', nodenamefunc=handle)
    render_tree(root_node, filename='tree.dot', nodenamefunc=lambda node: node.name)
