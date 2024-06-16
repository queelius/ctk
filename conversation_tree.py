from treekit import DictTree
from conversation import Conversation
import json

class ConversationTree(DictTree):
    def __init__(self, data, mapping_key="mapping"):
        super().__init__(data=data, mapping_key=mapping_key)

    def flatten(self,
                node_name=lambda node: node.name,
                fallback_node_name=None):
         
        return [Conversation(conv, self.metadata) for conv in super.flatten())]
    
    def __repr__(self):
        return json.dumps(self.data, indent=4)
    
    def __str__(self):
        conversations = self.flatten()





