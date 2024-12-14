import AlgoTree
from typing import Dict
from conversation import Conversation
import json

class ConversationTree:
    def __init__(self, *args, **kwargs):

        # everything but `mapping` key at the root level is metadata about
        # the conversation tree, and `mapping` is the actual conversation tree
        # itself

        self.metadata : Dict = { key: kwargs[key] for key in kwargs if key != "mapping" } 
        self.tree = AlgoTree.FlatTree(tree_mapping = kwargs.get("mapping", {}))

    def __str__(self):
        return json.dumps(self.metadata, indent=4)        
    
    def conversation_tree(self, pretty = False):
        if pretty:
            return AlgoTree.pretty_tree.pretty_tree(self.tree)
        else:
            return self.tree





