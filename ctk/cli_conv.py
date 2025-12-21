"""
Conversation-level commands for CTK CLI.

Commands that operate on individual conversations:
- show, tree, paths (viewing)
- star, pin, archive, title, delete, duplicate (organization)
- tag, untag (tagging)
- say (send message - future)
- fork (create branch - future)
"""

import argparse
from typing import Optional

from ctk.core.database import ConversationDB


def resolve_conversation_id(db: ConversationDB, partial_id: str) -> Optional[str]:
    """Resolve a partial conversation ID to a full ID."""
    # Try exact match first
    conv = db.load_conversation(partial_id)
    if conv:
        return partial_id

    # Try prefix match
    all_convs = db.list_conversations(limit=1000)
    matches = [c for c in all_convs if c.id.startswith(partial_id)]

    if len(matches) == 1:
        return matches[0].id
    elif len(matches) > 1:
        print(f"Error: Multiple conversations match '{partial_id}':")
        for match in matches[:5]:
            print(f"  - {match.id[:8]}... {match.title}")
        return None
    else:
        print(f"Error: No conversation found matching '{partial_id}'")
        return None


def cmd_show(args):
    """Show a specific conversation"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Get path to display
        if args.path is not None:
            paths = conv.get_all_paths()
            if args.path < 0 or args.path >= len(paths):
                print(f"Error: Path {args.path} not found (valid: 0-{len(paths)-1})")
                return 1
            messages = paths[args.path]
        else:
            messages = conv.get_longest_path()

        # Display header
        title = conv.title or "Untitled"
        flags = []
        if conv.metadata.starred_at:
            flags.append("⭐")
        if conv.metadata.pinned_at:
            flags.append("📌")
        if conv.metadata.archived_at:
            flags.append("📦")

        header = f"{title} {' '.join(flags)}"
        console.print(Panel(header, style="bold cyan"))
        console.print(f"ID: {conv.id}")
        console.print(f"Messages: {len(messages)}")
        if conv.metadata.model:
            console.print(f"Model: {conv.metadata.model}")
        if conv.metadata.tags:
            console.print(f"Tags: {', '.join(conv.metadata.tags)}")
        console.print()

        # Display messages
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            role_style = {
                'USER': 'green',
                'ASSISTANT': 'blue',
                'SYSTEM': 'yellow',
                'TOOL': 'magenta'
            }.get(role, 'white')

            content = msg.content.text if msg.content else ""
            if args.truncate and len(content) > args.truncate:
                content = content[:args.truncate] + "..."

            console.print(f"[bold {role_style}]{role}[/bold {role_style}]")
            console.print(content)
            console.print()

        return 0


def cmd_tree(args):
    """Show conversation tree structure"""
    from rich.console import Console
    from rich.tree import Tree

    console = Console()

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Build tree visualization
        title = conv.title or "Untitled"
        tree = Tree(f"[bold cyan]{title}[/bold cyan]")

        def add_message_node(parent_tree, message, depth=0):
            role = message.role.value if hasattr(message.role, 'value') else str(message.role)
            role_style = {
                'USER': 'green',
                'ASSISTANT': 'blue',
                'SYSTEM': 'yellow',
                'TOOL': 'magenta'
            }.get(role, 'white')

            content = message.content.text if message.content else ""
            preview = content[:50].replace('\n', ' ') + "..." if len(content) > 50 else content.replace('\n', ' ')

            node = parent_tree.add(f"[{role_style}]{role}[/{role_style}]: {preview}")

            # Add children
            children = conv.get_children(message.id)
            for child in children:
                add_message_node(node, child, depth + 1)

        # Start from root messages
        for root_id in conv.root_message_ids:
            if root_id in conv.message_map:
                add_message_node(tree, conv.message_map[root_id])

        console.print(tree)

        # Show path count
        paths = conv.get_all_paths()
        if len(paths) > 1:
            console.print(f"\n[dim]{len(paths)} paths in conversation[/dim]")

        return 0


def cmd_paths(args):
    """List all paths in a conversation"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        paths = conv.get_all_paths()

        if not paths:
            console.print("[dim]No paths found[/dim]")
            return 0

        table = Table(title=f"Paths in: {conv.title or 'Untitled'}")
        table.add_column("#", style="dim")
        table.add_column("Length")
        table.add_column("Last Message Preview")

        for i, path in enumerate(paths):
            last_msg = path[-1] if path else None
            preview = ""
            if last_msg and last_msg.content:
                preview = last_msg.content.text[:60].replace('\n', ' ')
                if len(last_msg.content.text) > 60:
                    preview += "..."

            table.add_row(str(i), str(len(path)), preview)

        console.print(table)
        return 0


def cmd_star(args):
    """Star or unstar a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        star = not args.unstar
        db.star_conversation(conv_id, star=star)

        action = "Starred" if star else "Unstarred"
        print(f"✓ {action} conversation {conv_id[:8]}...")
        return 0


def cmd_pin(args):
    """Pin or unpin a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        pin = not args.unpin
        db.pin_conversation(conv_id, pin=pin)

        action = "Pinned" if pin else "Unpinned"
        print(f"✓ {action} conversation {conv_id[:8]}...")
        return 0


def cmd_archive(args):
    """Archive or unarchive a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        archive = not args.unarchive
        db.archive_conversation(conv_id, archive=archive)

        action = "Archived" if archive else "Unarchived"
        print(f"✓ {action} conversation {conv_id[:8]}...")
        return 0


def cmd_title(args):
    """Rename a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        old_title = conv.title
        conv.title = args.title
        db.save_conversation(conv)

        print(f"✓ Renamed: '{old_title}' → '{args.title}'")
        return 0


def cmd_delete(args):
    """Delete a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        if not args.force:
            print(f"About to delete: {conv.title or 'Untitled'} ({conv_id[:8]}...)")
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("Cancelled")
                return 1

        db.delete_conversation(conv_id)
        print(f"✓ Deleted conversation {conv_id[:8]}...")
        return 0


def cmd_duplicate(args):
    """Duplicate a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        new_id = db.duplicate_conversation(conv_id, new_title=args.title)

        if new_id:
            new_conv = db.load_conversation(new_id)
            print(f"✓ Duplicated conversation")
            print(f"  New ID: {new_id[:8]}...")
            print(f"  Title: {new_conv.title if new_conv else 'Unknown'}")
            return 0
        else:
            print(f"Error: Failed to duplicate conversation")
            return 1


def cmd_tag(args):
    """Add tags to a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        tags = [t.strip() for t in args.tags.split(',') if t.strip()]
        if not tags:
            print("Error: No valid tags provided")
            return 1

        db.add_tags(conv_id, tags)
        print(f"✓ Added tags to {conv_id[:8]}...: {', '.join(tags)}")
        return 0


def cmd_untag(args):
    """Remove a tag from a conversation"""
    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        db.remove_tag(conv_id, args.tag)
        print(f"✓ Removed tag '{args.tag}' from {conv_id[:8]}...")
        return 0


def add_conv_commands(subparsers):
    """Add conversation command group to parser"""
    conv_parser = subparsers.add_parser('conv', help='Conversation operations')
    conv_subparsers = conv_parser.add_subparsers(dest='conv_command', help='Conversation commands')

    # show
    show_parser = conv_subparsers.add_parser('show', help='Show conversation content')
    show_parser.add_argument('id', help='Conversation ID (full or partial)')
    show_parser.add_argument('--db', '-d', required=True, help='Database path')
    show_parser.add_argument('--path', '-p', type=int, help='Path index for branching conversations')
    show_parser.add_argument('--truncate', '-t', type=int, help='Truncate messages to N characters')

    # tree
    tree_parser = conv_subparsers.add_parser('tree', help='Show conversation tree structure')
    tree_parser.add_argument('id', help='Conversation ID (full or partial)')
    tree_parser.add_argument('--db', '-d', required=True, help='Database path')

    # paths
    paths_parser = conv_subparsers.add_parser('paths', help='List all paths in conversation')
    paths_parser.add_argument('id', help='Conversation ID (full or partial)')
    paths_parser.add_argument('--db', '-d', required=True, help='Database path')

    # star
    star_parser = conv_subparsers.add_parser('star', help='Star/unstar conversation')
    star_parser.add_argument('id', help='Conversation ID (full or partial)')
    star_parser.add_argument('--db', '-d', required=True, help='Database path')
    star_parser.add_argument('--unstar', action='store_true', help='Unstar instead of star')

    # pin
    pin_parser = conv_subparsers.add_parser('pin', help='Pin/unpin conversation')
    pin_parser.add_argument('id', help='Conversation ID (full or partial)')
    pin_parser.add_argument('--db', '-d', required=True, help='Database path')
    pin_parser.add_argument('--unpin', action='store_true', help='Unpin instead of pin')

    # archive
    archive_parser = conv_subparsers.add_parser('archive', help='Archive/unarchive conversation')
    archive_parser.add_argument('id', help='Conversation ID (full or partial)')
    archive_parser.add_argument('--db', '-d', required=True, help='Database path')
    archive_parser.add_argument('--unarchive', action='store_true', help='Unarchive instead of archive')

    # title
    title_parser = conv_subparsers.add_parser('title', help='Rename conversation')
    title_parser.add_argument('id', help='Conversation ID (full or partial)')
    title_parser.add_argument('title', help='New title')
    title_parser.add_argument('--db', '-d', required=True, help='Database path')

    # delete
    delete_parser = conv_subparsers.add_parser('delete', help='Delete conversation')
    delete_parser.add_argument('id', help='Conversation ID (full or partial)')
    delete_parser.add_argument('--db', '-d', required=True, help='Database path')
    delete_parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation')

    # duplicate
    duplicate_parser = conv_subparsers.add_parser('duplicate', help='Duplicate conversation')
    duplicate_parser.add_argument('id', help='Conversation ID (full or partial)')
    duplicate_parser.add_argument('--db', '-d', required=True, help='Database path')
    duplicate_parser.add_argument('--title', help='Title for duplicated conversation')

    # tag
    tag_parser = conv_subparsers.add_parser('tag', help='Add tags to conversation')
    tag_parser.add_argument('id', help='Conversation ID (full or partial)')
    tag_parser.add_argument('tags', help='Comma-separated tags to add')
    tag_parser.add_argument('--db', '-d', required=True, help='Database path')

    # untag
    untag_parser = conv_subparsers.add_parser('untag', help='Remove tag from conversation')
    untag_parser.add_argument('id', help='Conversation ID (full or partial)')
    untag_parser.add_argument('tag', help='Tag to remove')
    untag_parser.add_argument('--db', '-d', required=True, help='Database path')

    return conv_parser


def dispatch_conv_command(args):
    """Dispatch to appropriate conv subcommand"""
    commands = {
        'show': cmd_show,
        'tree': cmd_tree,
        'paths': cmd_paths,
        'star': cmd_star,
        'pin': cmd_pin,
        'archive': cmd_archive,
        'title': cmd_title,
        'delete': cmd_delete,
        'duplicate': cmd_duplicate,
        'tag': cmd_tag,
        'untag': cmd_untag,
    }

    if hasattr(args, 'conv_command') and args.conv_command:
        if args.conv_command in commands:
            return commands[args.conv_command](args)
        else:
            print(f"Unknown conv command: {args.conv_command}")
            return 1
    else:
        print("Error: No conv command specified. Use 'ctk conv --help' for available commands.")
        return 1
