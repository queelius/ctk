"""
Library-level commands for CTK CLI.

Commands that operate on the conversation collection:
- list, search (discovery)
- import, export (I/O)
- stats, tags, models, sources (metadata)
"""

import argparse
import json
from typing import Optional, List
from pathlib import Path

from ctk.core.database import ConversationDB
from ctk.core.plugin import registry


def cmd_list(args):
    """List conversations in the database"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        # Build filters
        kwargs = {}
        if args.limit:
            kwargs['limit'] = args.limit
        if args.starred:
            kwargs['starred'] = True
        if args.pinned:
            kwargs['pinned'] = True
        if args.archived:
            kwargs['archived'] = True
        elif not args.include_archived:
            kwargs['archived'] = False
        if args.source:
            kwargs['source'] = args.source
        if args.model:
            kwargs['model'] = args.model

        conversations = db.list_conversations(**kwargs)

        if args.json:
            data = []
            for conv in conversations:
                data.append({
                    'id': conv.id,
                    'title': conv.title,
                    'created_at': str(conv.created_at) if conv.created_at else None,
                    'source': conv.source,
                    'model': conv.model,
                })
            print(json.dumps(data, indent=2))
            return 0

        # Rich table output
        table = Table(title="Conversations")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Flags", width=4)
        table.add_column("Title", style="cyan", max_width=40)
        table.add_column("Model", style="green")
        table.add_column("Date", style="dim")

        for conv in conversations:
            flags = ""
            if hasattr(conv, 'starred_at') and conv.starred_at:
                flags += "⭐"
            if hasattr(conv, 'pinned_at') and conv.pinned_at:
                flags += "📌"
            if hasattr(conv, 'archived_at') and conv.archived_at:
                flags += "📦"

            title = conv.title or "Untitled"
            if len(title) > 40:
                title = title[:37] + "..."

            date = ""
            if hasattr(conv, 'created_at') and conv.created_at:
                date = conv.created_at.strftime("%Y-%m-%d")

            table.add_row(
                conv.id[:8] + "...",
                flags,
                title,
                conv.model or "",
                date
            )

        console.print(table)
        console.print(f"\n[dim]{len(conversations)} conversation(s)[/dim]")
        return 0


def cmd_search(args):
    """Search conversations"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        # Build search parameters
        kwargs = {
            'query': args.query,
            'limit': args.limit or 50,
        }
        if args.title_only:
            kwargs['search_content'] = False
        if args.content_only:
            kwargs['search_title'] = False
        if args.source:
            kwargs['source'] = args.source
        if args.model:
            kwargs['model'] = args.model
        if args.tags:
            kwargs['tags'] = [t.strip() for t in args.tags.split(',')]

        results = db.search_conversations(**kwargs)

        if args.json:
            data = []
            for conv in results:
                data.append({
                    'id': conv.id,
                    'title': conv.title,
                    'source': conv.source,
                    'model': conv.model,
                })
            print(json.dumps(data, indent=2))
            return 0

        # Rich table output
        table = Table(title=f"Search: {args.query}")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Model", style="green")

        for conv in results:
            title = conv.title or "Untitled"
            if len(title) > 50:
                title = title[:47] + "..."

            table.add_row(
                conv.id[:8] + "...",
                title,
                conv.model or ""
            )

        console.print(table)
        console.print(f"\n[dim]{len(results)} result(s)[/dim]")
        return 0


def cmd_stats(args):
    """Show database statistics"""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    with ConversationDB(args.db) as db:
        stats = db.get_statistics()

        console.print(Panel("[bold cyan]Database Statistics[/bold cyan]"))

        console.print(f"📚 Conversations: {stats['total_conversations']:,}")
        console.print(f"💬 Messages: {stats['total_messages']:,}")
        console.print(f"🏷️  Tags: {stats['total_tags']:,}")

        if stats.get('messages_by_role'):
            console.print("\n[bold]Messages by Role:[/bold]")
            for role, count in sorted(stats['messages_by_role'].items(), key=lambda x: x[1], reverse=True):
                console.print(f"  {role:12} {count:7,}")

        if stats.get('conversations_by_source'):
            console.print("\n[bold]Conversations by Source:[/bold]")
            for source, count in sorted(stats['conversations_by_source'].items(), key=lambda x: x[1], reverse=True):
                console.print(f"  {source:20} {count:7,}")

        if stats.get('top_tags'):
            console.print("\n[bold]Top Tags:[/bold]")
            for tag in stats['top_tags'][:10]:
                console.print(f"  {tag['name']:30} {tag['count']:5,}")

        return 0


def cmd_tags(args):
    """List all tags"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        tags = db.get_all_tags()

        if args.json:
            print(json.dumps(tags, indent=2))
            return 0

        table = Table(title="Tags")
        table.add_column("Tag", style="cyan")
        table.add_column("Count", justify="right")

        # Note: get_all_tags returns 'usage_count' not 'count'
        for tag in sorted(tags, key=lambda t: t.get('usage_count', 0), reverse=True):
            table.add_row(tag['name'], str(tag.get('usage_count', 0)))

        console.print(table)
        return 0


def cmd_models(args):
    """List all models used"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        models = db.get_models()

        if args.json:
            print(json.dumps(models, indent=2))
            return 0

        table = Table(title="Models")
        table.add_column("Model", style="cyan")
        table.add_column("Conversations", justify="right")

        for model in models:
            table.add_row(model['model'], str(model['count']))

        console.print(table)
        return 0


def cmd_sources(args):
    """List all sources"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        sources = db.get_sources()

        if args.json:
            print(json.dumps(sources, indent=2))
            return 0

        table = Table(title="Sources")
        table.add_column("Source", style="cyan")
        table.add_column("Conversations", justify="right")

        for source in sources:
            table.add_row(source['source'], str(source['count']))

        console.print(table)
        return 0


def add_lib_commands(subparsers):
    """Add library command group to parser"""
    lib_parser = subparsers.add_parser('lib', help='Library operations')
    lib_subparsers = lib_parser.add_subparsers(dest='lib_command', help='Library commands')

    # list
    list_parser = lib_subparsers.add_parser('list', help='List conversations')
    list_parser.add_argument('--db', '-d', required=True, help='Database path')
    list_parser.add_argument('--limit', '-n', type=int, help='Maximum results')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--starred', action='store_true', help='Show only starred')
    list_parser.add_argument('--pinned', action='store_true', help='Show only pinned')
    list_parser.add_argument('--archived', action='store_true', help='Show only archived')
    list_parser.add_argument('--include-archived', action='store_true', help='Include archived')
    list_parser.add_argument('--source', help='Filter by source')
    list_parser.add_argument('--model', help='Filter by model')

    # search
    search_parser = lib_subparsers.add_parser('search', help='Search conversations')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--db', '-d', required=True, help='Database path')
    search_parser.add_argument('--limit', '-n', type=int, help='Maximum results')
    search_parser.add_argument('--json', action='store_true', help='Output as JSON')
    search_parser.add_argument('--title-only', action='store_true', help='Search titles only')
    search_parser.add_argument('--content-only', action='store_true', help='Search content only')
    search_parser.add_argument('--source', help='Filter by source')
    search_parser.add_argument('--model', help='Filter by model')
    search_parser.add_argument('--tags', help='Filter by tags (comma-separated)')

    # stats
    stats_parser = lib_subparsers.add_parser('stats', help='Show database statistics')
    stats_parser.add_argument('--db', '-d', required=True, help='Database path')

    # tags
    tags_parser = lib_subparsers.add_parser('tags', help='List all tags')
    tags_parser.add_argument('--db', '-d', required=True, help='Database path')
    tags_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # models
    models_parser = lib_subparsers.add_parser('models', help='List all models')
    models_parser.add_argument('--db', '-d', required=True, help='Database path')
    models_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # sources
    sources_parser = lib_subparsers.add_parser('sources', help='List all sources')
    sources_parser.add_argument('--db', '-d', required=True, help='Database path')
    sources_parser.add_argument('--json', action='store_true', help='Output as JSON')

    return lib_parser


def dispatch_lib_command(args):
    """Dispatch to appropriate lib subcommand"""
    commands = {
        'list': cmd_list,
        'search': cmd_search,
        'stats': cmd_stats,
        'tags': cmd_tags,
        'models': cmd_models,
        'sources': cmd_sources,
    }

    if hasattr(args, 'lib_command') and args.lib_command:
        if args.lib_command in commands:
            return commands[args.lib_command](args)
        else:
            print(f"Unknown lib command: {args.lib_command}")
            return 1
    else:
        print("Error: No lib command specified. Use 'ctk lib --help' for available commands.")
        return 1
