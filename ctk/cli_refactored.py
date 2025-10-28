"""
Refactored CLI using command handlers.

This demonstrates how the CLI should use the new command handler architecture.
"""

import argparse
from pathlib import Path
from datetime import datetime

from ctk.core.database import ConversationDB
from ctk.core.commands import (
    ListCommand, SearchCommand, DeleteCommand, ShowCommand,
    ArchiveCommand, StarCommand, PinCommand, TitleCommand,
    DuplicateCommand, CommandError
)
from ctk.core.formatters import CLIFormatter


def cmd_list_refactored(args):
    """List conversations using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter(json_output=args.json)

    try:
        # Parse tags if provided
        tags = None
        if hasattr(args, 'tags') and args.tags:
            tags = [t.strip() for t in args.tags.split(',')]

        # Execute command
        conversations = ListCommand.execute(
            db=db,
            limit=args.limit,
            source=getattr(args, 'source', None),
            model=getattr(args, 'model', None),
            tags=tags,
            archived=getattr(args, 'archived', None) if hasattr(args, 'archived') and args.archived else None,
            starred=getattr(args, 'starred', None) if hasattr(args, 'starred') and args.starred else None,
            pinned=getattr(args, 'pinned', None) if hasattr(args, 'pinned') and args.pinned else None,
            include_archived=getattr(args, 'include_archived', False)
        )

        # Format output
        formatter.format_conversation_list(conversations)
        return 0

    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_search_refactored(args):
    """Search conversations using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter(json_output=(args.format == 'json'))

    try:
        # Parse date arguments
        date_from = None
        date_to = None
        if args.date_from:
            date_from = datetime.fromisoformat(args.date_from)
        if args.date_to:
            date_to = datetime.fromisoformat(args.date_to)

        # Parse tags
        tags = args.tags.split(',') if args.tags else None

        # Execute command
        results = SearchCommand.execute(
            db=db,
            query_text=args.query,
            limit=args.limit,
            offset=args.offset,
            title_only=args.title_only,
            content_only=args.content_only,
            date_from=date_from,
            date_to=date_to,
            source=args.source,
            model=args.model,
            tags=tags,
            min_messages=args.min_messages,
            max_messages=args.max_messages,
            has_branches=args.has_branches,
            archived=getattr(args, 'archived', None) if hasattr(args, 'archived') and args.archived else None,
            starred=getattr(args, 'starred', None) if hasattr(args, 'starred') and args.starred else None,
            pinned=getattr(args, 'pinned', None) if hasattr(args, 'pinned') and args.pinned else None,
            include_archived=getattr(args, 'include_archived', False),
            order_by=args.order_by,
            ascending=args.ascending
        )

        # Format output based on format arg
        if args.format == 'csv':
            print("ID,Title,Messages,Source,Model,Created,Updated")
            for conv in results:
                conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
                print(f"{conv_dict['id']},{conv_dict.get('title', 'Untitled')},{conv_dict.get('message_count', 0)},"
                      f"{conv_dict.get('source', '')},{conv_dict.get('model', '')},"
                      f"{conv_dict.get('created_at', '')},{conv_dict.get('updated_at', '')}")
        else:
            formatter.format_search_results(results, args.query or "")

        return 0

    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_delete_refactored(args):
    """Delete conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        # Define confirmation function
        def confirm_deletion(tree):
            if args.yes:
                return True

            print(f"\nAbout to delete conversation:")
            print(f"  ID: {tree.id[:8]}...")
            print(f"  Title: {tree.title}")
            print(f"  Messages: {len(tree.message_map)}")

            return formatter.confirm("Type 'yes' to confirm deletion")

        # Execute command
        deleted_tree = DeleteCommand.execute(
            db=db,
            conv_id=args.id,
            confirm_fn=confirm_deletion,
            skip_confirmation=args.yes
        )

        formatter.format_success(f"Deleted conversation: {deleted_tree.title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_show_refactored(args):
    """Show conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        # Execute command
        tree = ShowCommand.execute(db=db, conv_id=args.id)

        # Format output
        formatter.format_conversation_detail(tree)
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_archive_refactored(args):
    """Archive/unarchive conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        tree = ArchiveCommand.execute(
            db=db,
            conv_id=args.id,
            archive=not args.unarchive
        )

        action = "Unarchived" if args.unarchive else "Archived"
        formatter.format_success(f"{action} conversation: {tree.title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_star_refactored(args):
    """Star/unstar conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        tree = StarCommand.execute(
            db=db,
            conv_id=args.id,
            star=not args.unstar
        )

        action = "Unstarred" if args.unstar else "Starred"
        formatter.format_success(f"{action} conversation: {tree.title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_pin_refactored(args):
    """Pin/unpin conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        tree = PinCommand.execute(
            db=db,
            conv_id=args.id,
            pin=not args.unpin
        )

        action = "Unpinned" if args.unpin else "Pinned"
        formatter.format_success(f"{action} conversation: {tree.title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_title_refactored(args):
    """Rename conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        tree, old_title = TitleCommand.execute(
            db=db,
            conv_id=args.id,
            new_title=args.new_title
        )

        formatter.format_success("Renamed conversation")
        print(f"  Old title: {old_title}")
        print(f"  New title: {args.new_title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


def cmd_duplicate_refactored(args):
    """Duplicate conversation using command handler"""
    if not args.db:
        print("Error: Database path required")
        return 1

    db = ConversationDB(args.db)
    formatter = CLIFormatter()

    try:
        new_id, new_tree = DuplicateCommand.execute(
            db=db,
            conv_id=args.id,
            new_title=args.title
        )

        formatter.format_success("Duplicated conversation")
        print(f"  New ID: {new_id[:8]}...")
        print(f"  New title: {new_tree.title}")
        return 0

    except CommandError as e:
        formatter.format_error(str(e))
        return 1
    except Exception as e:
        formatter.format_error(str(e))
        return 1


# Example of how the main() function would look:
"""
def main():
    parser = argparse.ArgumentParser(description='CTK - Conversation Toolkit')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List command
    list_parser = subparsers.add_parser('list', help='List conversations')
    list_parser.add_argument('--db', '-d', required=True, help='Database path')
    list_parser.add_argument('--limit', type=int, default=100)
    list_parser.add_argument('--json', action='store_true')
    # ... other args

    # Map commands to refactored handlers
    commands = {
        'list': cmd_list_refactored,
        'search': cmd_search_refactored,
        'delete': cmd_delete_refactored,
        'show': cmd_show_refactored,
        'archive': cmd_archive_refactored,
        'star': cmd_star_refactored,
        'pin': cmd_pin_refactored,
        'title': cmd_title_refactored,
        'duplicate': cmd_duplicate_refactored,
    }

    args = parser.parse_args()
    return commands[args.command](args)
"""
