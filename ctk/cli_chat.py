#!/usr/bin/env python3
"""
Interactive CLI chat interface for browsing conversations
"""

import cmd
import textwrap
from typing import Optional, List
from datetime import datetime

from ctk.core.database import ConversationDB
from ctk.core.models import MessageRole


class ConversationBrowser(cmd.Cmd):
    """Interactive conversation browser"""
    
    intro = """
╔══════════════════════════════════════════════════════════════╗
║          CTK - Conversation Browser                         ║
║  Type 'help' for commands, 'quit' to exit                  ║
╚══════════════════════════════════════════════════════════════╝
    """
    prompt = "(ctk) "
    
    def __init__(self, db_path: str):
        super().__init__()
        self.db = ConversationDB(db_path)
        self.current_conv = None
        self.current_messages = []
        self.current_path_idx = 0
        self.search_results = []
        
    def do_list(self, arg):
        """List conversations: list [limit]"""
        limit = int(arg) if arg else 20
        conversations = self.db.list_conversations(limit=limit)
        
        if not conversations:
            print("No conversations found")
            return
        
        print(f"\n{'ID[:8]':<10} {'Title':<50} {'Messages':<10} {'Updated'}")
        print("-" * 90)
        
        for conv in conversations:
            # Count messages for this conversation
            conv_obj = self.db.load_conversation(conv['id'])
            msg_count = len(conv_obj.message_map) if conv_obj else 0
            
            # Format display
            id_short = conv['id'][:8]
            title = (conv['title'] or 'Untitled')[:48]
            updated = conv['updated_at'][:10] if conv['updated_at'] else 'Unknown'
            
            print(f"{id_short:<10} {title:<50} {msg_count:<10} {updated}")
    
    def do_search(self, query):
        """Search conversations: search <query>"""
        if not query:
            print("Usage: search <query>")
            return
        
        self.search_results = self.db.search_conversations(query, limit=50)
        
        if not self.search_results:
            print(f"No results for '{query}'")
            return
        
        print(f"\nFound {len(self.search_results)} results:")
        for idx, conv in enumerate(self.search_results):
            print(f"{idx+1}. [{conv['id'][:8]}] {conv['title'] or 'Untitled'}")
        
        print("\nUse 'open <number>' to open a search result")
    
    def do_open(self, arg):
        """Open a conversation: open <id|search_number>"""
        if not arg:
            print("Usage: open <conversation_id> or open <search_number>")
            return
        
        # Check if it's a search result number
        if arg.isdigit() and self.search_results:
            idx = int(arg) - 1
            if 0 <= idx < len(self.search_results):
                conv_id = self.search_results[idx]['id']
            else:
                print("Invalid search result number")
                return
        else:
            conv_id = arg
        
        # Load conversation
        self.current_conv = self.db.load_conversation(conv_id)
        if not self.current_conv:
            # Try partial match
            convs = self.db.list_conversations(limit=1000)
            matches = [c for c in convs if c['id'].startswith(conv_id)]
            if matches:
                self.current_conv = self.db.load_conversation(matches[0]['id'])
        
        if not self.current_conv:
            print(f"Conversation '{conv_id}' not found")
            return
        
        # Load messages from longest path
        self.current_messages = self.current_conv.get_longest_path()
        self.current_path_idx = 0
        
        # Show info
        print(f"\n📂 Opened: {self.current_conv.title or 'Untitled'}")
        print(f"   ID: {self.current_conv.id[:16]}...")
        print(f"   Messages: {len(self.current_messages)}")
        print(f"   Model: {self.current_conv.metadata.model or 'Unknown'}")
        print(f"   Tags: {', '.join(self.current_conv.metadata.tags) or 'None'}")
        print(f"\nUse 'show' to display messages, 'next'/'prev' to navigate")
    
    def do_show(self, arg):
        """Show current conversation: show [start] [count]"""
        if not self.current_conv:
            print("No conversation open. Use 'open <id>' first")
            return
        
        args = arg.split() if arg else []
        start = int(args[0]) if args else self.current_path_idx
        count = int(args[1]) if len(args) > 1 else 5
        
        end = min(start + count, len(self.current_messages))
        
        print(f"\n[Messages {start+1}-{end} of {len(self.current_messages)}]")
        print("=" * 70)
        
        for idx in range(start, end):
            msg = self.current_messages[idx]
            self._print_message(msg, idx)
        
        self.current_path_idx = end
        
        if end < len(self.current_messages):
            print(f"\n[More messages available. Use 'next' to continue]")
    
    def do_next(self, arg):
        """Show next messages: next [count]"""
        count = int(arg) if arg else 5
        self.do_show(f"{self.current_path_idx} {count}")
    
    def do_prev(self, arg):
        """Show previous messages: prev [count]"""
        count = int(arg) if arg else 5
        start = max(0, self.current_path_idx - count - 5)
        self.do_show(f"{start} {count}")
    
    def do_tag(self, arg):
        """Manage tags: tag add <tag> | tag remove <tag> | tag list"""
        if not self.current_conv:
            print("No conversation open")
            return
        
        args = arg.split(maxsplit=1)
        if not args:
            print("Usage: tag add <tag> | tag remove <tag> | tag list")
            return
        
        action = args[0]
        
        if action == "list":
            tags = self.current_conv.metadata.tags
            if tags:
                print("Tags: " + ", ".join(tags))
            else:
                print("No tags")
        
        elif action == "add" and len(args) > 1:
            tag = args[1].strip()
            if tag not in self.current_conv.metadata.tags:
                self.current_conv.metadata.tags.append(tag)
                self.db.save_conversation(self.current_conv)
                print(f"Added tag: {tag}")
            else:
                print(f"Tag already exists: {tag}")
        
        elif action == "remove" and len(args) > 1:
            tag = args[1].strip()
            if tag in self.current_conv.metadata.tags:
                self.current_conv.metadata.tags.remove(tag)
                self.db.save_conversation(self.current_conv)
                print(f"Removed tag: {tag}")
            else:
                print(f"Tag not found: {tag}")
        
        else:
            print("Usage: tag add <tag> | tag remove <tag> | tag list")
    
    def do_project(self, arg):
        """Manage projects: project set <name> | project clear | project list"""
        if not arg:
            print("Usage: project set <name> | project clear | project list")
            return
        
        args = arg.split(maxsplit=1)
        action = args[0]
        
        if action == "list":
            # List all projects
            conversations = self.db.list_conversations(limit=1000)
            projects = set()
            
            for conv_data in conversations:
                conv = self.db.load_conversation(conv_data['id'])
                if conv:
                    for tag in conv.metadata.tags:
                        if tag.startswith("project:"):
                            projects.add(tag[8:])
            
            if projects:
                print("Projects:")
                for proj in sorted(projects):
                    print(f"  - {proj}")
            else:
                print("No projects found")
        
        elif action == "set" and len(args) > 1:
            if not self.current_conv:
                print("No conversation open")
                return
            
            project_name = args[1].strip()
            # Remove existing project tags
            self.current_conv.metadata.tags = [
                t for t in self.current_conv.metadata.tags 
                if not t.startswith("project:")
            ]
            # Add new project tag
            self.current_conv.metadata.tags.append(f"project:{project_name}")
            self.db.save_conversation(self.current_conv)
            print(f"Set project: {project_name}")
        
        elif action == "clear":
            if not self.current_conv:
                print("No conversation open")
                return
            
            # Remove project tags
            self.current_conv.metadata.tags = [
                t for t in self.current_conv.metadata.tags 
                if not t.startswith("project:")
            ]
            self.db.save_conversation(self.current_conv)
            print("Cleared project")
        
        else:
            print("Usage: project set <name> | project clear | project list")
    
    def do_filter(self, arg):
        """Filter by tags: filter <tag1,tag2> | filter project:<name>"""
        if not arg:
            print("Usage: filter <tag1,tag2> | filter project:<name>")
            return
        
        tags = [t.strip() for t in arg.split(',')]
        
        # Get all conversations and filter
        conversations = self.db.list_conversations(limit=1000)
        filtered = []
        
        for conv_data in conversations:
            conv = self.db.load_conversation(conv_data['id'])
            if conv and all(tag in conv.metadata.tags for tag in tags):
                filtered.append(conv_data)
        
        if not filtered:
            print(f"No conversations with tags: {', '.join(tags)}")
            return
        
        print(f"\nFound {len(filtered)} conversations:")
        for conv in filtered[:20]:
            print(f"[{conv['id'][:8]}] {conv['title'] or 'Untitled'}")
    
    def do_stats(self, arg):
        """Show statistics for current conversation"""
        if not self.current_conv:
            stats = self.db.get_statistics()
            print("\nDatabase Statistics:")
            print(f"  Total conversations: {stats['total_conversations']}")
            print(f"  Total messages: {stats['total_messages']}")
            
            if stats.get('messages_by_role'):
                print("\nMessages by role:")
                for role, count in stats['messages_by_role'].items():
                    print(f"    {role}: {count}")
            
            if stats.get('conversations_by_source'):
                print("\nConversations by source:")
                for source, count in stats['conversations_by_source'].items():
                    print(f"    {source}: {count}")
        else:
            # Stats for current conversation
            msg_count = len(self.current_messages)
            word_count = sum(len(msg.content.get_text().split()) for msg in self.current_messages)
            
            role_counts = {}
            for msg in self.current_messages:
                role = msg.role.value
                role_counts[role] = role_counts.get(role, 0) + 1
            
            print(f"\nConversation Statistics:")
            print(f"  Title: {self.current_conv.title or 'Untitled'}")
            print(f"  Messages: {msg_count}")
            print(f"  Words: {word_count:,}")
            print(f"  Avg words/message: {word_count // msg_count if msg_count else 0}")
            print(f"\nMessages by role:")
            for role, count in role_counts.items():
                print(f"    {role}: {count}")
    
    def do_paths(self, arg):
        """Show conversation paths (for branching conversations)"""
        if not self.current_conv:
            print("No conversation open")
            return
        
        paths = self.current_conv.get_all_paths()
        print(f"\nConversation has {len(paths)} path(s):")
        
        for idx, path in enumerate(paths):
            summary = f"Path {idx+1}: {len(path)} messages"
            if path:
                first_user = next((m for m in path if m.role == MessageRole.USER), None)
                if first_user:
                    preview = first_user.content.get_text()[:50]
                    summary += f" - '{preview}...'"
            print(summary)
        
        if len(paths) > 1:
            print("\nThis is a branching conversation (has regenerated responses)")
    
    def _print_message(self, msg, idx):
        """Pretty print a message"""
        role_colors = {
            MessageRole.USER: "\033[94m",     # Blue
            MessageRole.ASSISTANT: "\033[92m", # Green
            MessageRole.SYSTEM: "\033[93m",    # Yellow
            MessageRole.TOOL: "\033[95m",      # Magenta
        }
        reset = "\033[0m"
        
        color = role_colors.get(msg.role, "")
        role_str = msg.role.value.upper()
        
        print(f"\n{color}[{idx+1}] {role_str}{reset}")
        if msg.timestamp:
            print(f"    {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Wrap text for readability
        text = msg.content.get_text()
        if text:
            wrapped = textwrap.fill(text, width=70, initial_indent="    ", 
                                   subsequent_indent="    ")
            print(wrapped[:500])  # Limit display length
            if len(wrapped) > 500:
                print("    [... truncated, use 'show' with index to see full]")
    
    def do_quit(self, arg):
        """Exit the browser"""
        print("Goodbye!")
        self.db.close()
        return True
    
    def do_exit(self, arg):
        """Exit the browser"""
        return self.do_quit(arg)
    
    def do_help(self, arg):
        """Show help"""
        if arg:
            super().do_help(arg)
        else:
            print("""
Available Commands:
  
  Browsing:
    list [limit]         - List conversations
    open <id>           - Open a conversation
    show [start] [count] - Show messages
    next [count]        - Show next messages
    prev [count]        - Show previous messages
    paths               - Show conversation branches
    
  Searching:
    search <query>      - Search conversations
    filter <tags>       - Filter by tags
    
  Tagging:
    tag list            - List tags for current conversation
    tag add <tag>       - Add a tag
    tag remove <tag>    - Remove a tag
    project set <name>  - Set project
    project clear       - Clear project
    project list        - List all projects
    
  Other:
    stats               - Show statistics
    help [command]      - Show help
    quit/exit           - Exit browser
""")


def main():
    """Main entry point for interactive browser"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Interactive conversation browser')
    parser.add_argument('--db', required=True, help='Database path')
    args = parser.parse_args()
    
    browser = ConversationBrowser(args.db)
    browser.cmdloop()


if __name__ == '__main__':
    main()