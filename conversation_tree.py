
from anytree import Node, RenderTree, PreOrderIter
import GenericTree

class Conversation:
    def __init__(self, path, metadata):
        self.path = path
        self.metadata = metadata

    def to_list(self, roles = ['user', 'assistant']):
        def __helper(node):
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
        
        nodes = []
        for node in path
            txt = __helper(node)
            if txt is not None:
                nodes.append((node, txt))
        return nodes

    def __str__(self):
        return self.metadata + "\n" + "".join([txt for node, txt in self.to_list()])

class ConversationTree(GenericTree.GenericTree):
    def __init__(self, root):
        super().__init__(root)

    def flatten_conversations(self): 
        conversation_paths = []
        for leaf in [node for node in PreOrderIter(self.root_node) if node.is_leaf]:
            path = []
            cur = leaf
            while cur is not None:
                path.append(cur)
                cur = cur.parent
            conv = Conversation(path[::-1], "")
            conversation_paths.append(conv)

        return conversation_paths
