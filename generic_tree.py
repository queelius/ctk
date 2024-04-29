import json
from anytree import Node, RenderTree, findall, PreOrderIter
from anytree.exporter import DotExporter
import graphviz

class GenericTree:
    def __init__(self, data, verify_integrity=True, mapping_key='mapping'):
        self.metadata = self.extract_metadata(data)
        if mapping_key not in data:
            raise ValueError(f"{mapping_key} not found found")
        self.nodes = self.load_openai_export(data.get(mapping_key, []))
        self.root_node = self.find_root_node()
        if verify_integrity:
            self.verify_tree_integrity()

    def extract_metadata(self, mapping_key):
            {key: value for key, value in data.items() if key != mapping_key}

    def load(self,
             mapping,
             payload = lambda x: x['message']):
        """
        Load a tree from mapping data.

        Mapping data is a dictionary of key-value pairs, where the key is
        the node ID and the value is a dictionary containing the node's
        parent ID, children IDs, and any other relevant data.

        We rerieve the relevant data using the payload function. By default,
        the payload function retrieves the 'message' field from the mapping data,
        which is the default structure of OpenAI's conversation data.

        :param mapping: Mapping data.
        :param payload: Function to retrieve payload from mapping data.

        :return: A dictionary of nodes compatible with anyTree library.
        """
        
        nodes = {}
        for key, value in mapping:
            nodes[key] = Node(key, parent=None, children=[], payload=payload(value))
        for key, value in mapping:
            parent_id = value['parent']
            if parent_id:
                nodes[key].parent = nodes.get(parent_id)
            for child_id in value.get('children', []):
                nodes[child_id].parent = nodes[key]
        return nodes

    def find_root_node(self):
        for node in self.nodes.values():
            if node.parent is None:
                return node
        raise ValueError("No root node found")

    def verify_tree_integrity(self):
        visited = set()
        path = set()

        def dfs(node):
            if node in path:
                raise ValueError(f"Cycle detected involving node {node.name}")
            path.add(node)
            for child in node.children:
                if child not in visited:
                    visited.add(child)
                    dfs(child)
            path.remove(node)

        visited.add(self.root_node)
        dfs(self.root_node)
        print("Tree integrity verified.")

    def render_tree(self,
                    nodenamefunc = lambda node: f"{node.name}\n{node.payload.truncate(20)}",
                    filename='tree.png'):
        """
        Render the tree to an image file. The filename should include the
        format extension (e.g., 'tree.png').

        :param nodenamefunc: Function to generate node names. By default, it
                                includes the node ID and the node payload.
        :param filename: Name of the output file.

        :return: None
        """
        format = filename.split('.')[-1]
        filename = filename.split('.')[0]
        
        DotExporter(node = self.root_node,
                    nodenamefunc = nodenamefunc).to_dotfile(f"{filename}.dot")
        graphviz.render('dot', format, filename)
        print(f"Tree rendered and saved as {filename}")

    def get_node_by_id(self, id):
        return self.nodes.get(id)

    def get_nodes(self):
        return self.nodes
    
    def flatten(self): 
        paths = []
        for leaf in [node for node in PreOrderIter(self.root_node) if node.is_leaf]:
            path = []
            cur = leaf
            while cur is not None:
                path.append(cur)
                cur = cur.parent
            paths.append(path[::-1])
    

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Render a generic tree from JSON data")
        parser.add_argument("json_file", help="Path to JSON file")
        args = parser.parse_args()
        
        json_data = None
        with open(args.json_file, "r") as file:
            json_data = json.load(file)
        tree = GenericTree(json_data)
        tree.render_tree()
    except Exception as e:
        print(e)
