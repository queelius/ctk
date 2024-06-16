import typing

class MessageFilter:
    def make_field_filter(self, key_path, values):
        def field_filter(node):
            if not node.payload:
                return False
            cur = node.payload
            for key in key_path:
                if key not in cur:
                    return False
                cur = cur[key]
            if not isinstance(cur, list):
                cur = [cur]
            if not isinstance(values, list):
                values = [values]
            intersect = set(values).intersection(cur)
            return len(intersect) > 0
        
        return field_filter

    def make_role_filter(self, roles = ['user', 'assistant']):
        self.make_field_filter(key_path = ['message', 'author', 'role'],
                          values = roles)
    
    def make_content_type_filter(self, types = ["text"]):

        self.make_field_filter(key_path = ['message', 'content', 'content_type'],
                               values = types)

    def __init__(self):
        self.filters = {}
        self.filters["roles"] = self.make_role_filter
        self.filters["all"] = lambda _: lambda _: True
        self.filters["none"] = lambda _: lambda _: False
        self.filters["content_type"] = self.make_content_type_filter
        self.filters["lambda"] = lambda str: eval(str)
        self.filters["field"] = lambda t: self.make_field_filter(t[0], t[1])

class Conversation:
    def __init__(self, path, metadata):
        self.path = path
        self.metadata = metadata

    def filter(self, test):
        return Conversation([n for n in self.path if test(n)], self.metadata)

    def has_path(self, node, key_path):
        if not node.payload:
            return False
        cur = node.payload
        for key in key_path:
            if key not in cur:
                return False
            cur = cur[key]
        if not isinstance(cur, list):
            cur = [cur]
        if not isinstance(values, list):
            values = [values]

    def __str__(self):
        def merge_parts(node):
            if not node.payload or 'message' not in node.payload or 'content' not in node.payload.message:
                return []
            
            content = node.payload.message.content
            if 'parts' not in content:
                return []
            
            parts = [p for p in content.parts if p]
            if not parts:
                return []

            return ['\n'.join(parts)]
            
        return "".join(merge_parts(node) for node in self.path)