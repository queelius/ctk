"""
Library-level commands for CTK CLI.

Commands that operate on the conversation collection:
- list, search (discovery)
- import, export (I/O)
- stats, tags, models, sources (metadata)
"""

import argparse
import json
from pathlib import Path
from typing import List, Optional

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
            kwargs["limit"] = args.limit
        if args.starred:
            kwargs["starred"] = True
        if args.pinned:
            kwargs["pinned"] = True
        if args.archived:
            kwargs["archived"] = True
        elif not args.include_archived:
            kwargs["archived"] = False
        if args.source:
            kwargs["source"] = args.source
        if args.model:
            kwargs["model"] = args.model
        if args.tags:
            kwargs["tags"] = [t.strip() for t in args.tags.split(",")]

        conversations = db.list_conversations(**kwargs)

        if args.json:
            data = []
            for conv in conversations:
                data.append(
                    {
                        "id": conv.id,
                        "title": conv.title,
                        "created_at": str(conv.created_at) if conv.created_at else None,
                        "source": conv.source,
                        "model": conv.model,
                    }
                )
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
            if hasattr(conv, "starred_at") and conv.starred_at:
                flags += "⭐"
            if hasattr(conv, "pinned_at") and conv.pinned_at:
                flags += "📌"
            if hasattr(conv, "archived_at") and conv.archived_at:
                flags += "📦"

            title = conv.title or "Untitled"
            if len(title) > 40:
                title = title[:37] + "..."

            date = ""
            if hasattr(conv, "created_at") and conv.created_at:
                date = conv.created_at.strftime("%Y-%m-%d")

            table.add_row(conv.id[:8] + "...", flags, title, conv.model or "", date)

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
            "query_text": args.query,
            "limit": args.limit or 50,
        }
        if args.title_only:
            kwargs["title_only"] = True
        if args.content_only:
            kwargs["content_only"] = True
        if args.source:
            kwargs["source"] = args.source
        if args.model:
            kwargs["model"] = args.model

        results = db.search_conversations(**kwargs)

        # Filter by tags if specified (post-filter since DB doesn't support)
        if args.tags:
            tag_list = [t.strip() for t in args.tags.split(",")]
            results = [
                c for c in results if c.tags and any(t in c.tags for t in tag_list)
            ]

        if args.json:
            data = []
            for conv in results:
                data.append(
                    {
                        "id": conv.id,
                        "title": conv.title,
                        "source": conv.source,
                        "model": conv.model,
                    }
                )
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

            table.add_row(conv.id[:8] + "...", title, conv.model or "")

        console.print(table)
        console.print(f"\n[dim]{len(results)} result(s)[/dim]")
        return 0


def cmd_stats(args):
    """Show database statistics"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        stats = db.get_statistics()

        console.print(Panel("[bold cyan]Database Statistics[/bold cyan]"))

        console.print(f"📚 Conversations: {stats['total_conversations']:,}")
        console.print(f"💬 Messages: {stats['total_messages']:,}")
        console.print(f"🏷️  Tags: {stats['total_tags']:,}")

        if stats.get("messages_by_role"):
            console.print("\n[bold]Messages by Role:[/bold]")
            for role, count in sorted(
                stats["messages_by_role"].items(), key=lambda x: x[1], reverse=True
            ):
                console.print(f"  {role:12} {count:7,}")

        if stats.get("conversations_by_source"):
            console.print("\n[bold]Conversations by Source:[/bold]")
            for source, count in sorted(
                stats["conversations_by_source"].items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                console.print(f"  {source:20} {count:7,}")

        if stats.get("top_tags"):
            console.print("\n[bold]Top Tags:[/bold]")
            for tag in stats["top_tags"][:10]:
                console.print(f"  {tag['name']:30} {tag['count']:5,}")

        return 0


def cmd_tags(args):
    """List all tags, or conversations with a specific tag"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        # If a tag name is provided, show conversations with that tag
        if args.tag:
            conversations = db.list_conversations_by_tag(args.tag)

            if args.json:
                data = [
                    {"id": c.id, "title": c.title, "model": c.model}
                    for c in conversations
                ]
                print(json.dumps(data, indent=2))
                return 0

            if not conversations:
                console.print(
                    f"[dim]No conversations found with tag '{args.tag}'[/dim]"
                )
                return 0

            table = Table(title=f"Conversations tagged: {args.tag}")
            table.add_column("ID", style="dim", width=10)
            table.add_column("Title", style="cyan", max_width=50)
            table.add_column("Model", style="green")

            for conv in conversations:
                title = conv.title or "Untitled"
                if len(title) > 50:
                    title = title[:47] + "..."
                table.add_row(conv.id[:8] + "...", title, conv.model or "")

            console.print(table)
            console.print(f"\n[dim]{len(conversations)} conversation(s)[/dim]")
            return 0

        # Otherwise show all tags with counts
        tags = db.get_all_tags()

        if args.json:
            print(json.dumps(tags, indent=2))
            return 0

        table = Table(title="Tags")
        table.add_column("Tag", style="cyan")
        table.add_column("Count", justify="right")

        # Note: get_all_tags returns 'usage_count' not 'count'
        for tag in sorted(tags, key=lambda t: t.get("usage_count", 0), reverse=True):
            table.add_row(tag["name"], str(tag.get("usage_count", 0)))

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
            table.add_row(model["model"], str(model["count"]))

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
            table.add_row(source["source"], str(source["count"]))

        console.print(table)
        return 0


def cmd_recent(args):
    """Show recently updated/created conversations"""
    from datetime import datetime, timedelta

    from rich.console import Console
    from rich.table import Table

    console = Console()

    with ConversationDB(args.db) as db:
        # Get conversations sorted by updated_at or created_at
        limit = args.limit or 20

        conversations = db.list_conversations(
            limit=limit,
            include_archived=args.include_archived,
            order_by="updated_at" if args.updated else "created_at",
            order_desc=True,
        )

        if args.json:
            data = []
            for conv in conversations:
                data.append(
                    {
                        "id": conv.id,
                        "title": conv.title,
                        "slug": getattr(conv, "slug", None),
                        "created_at": str(conv.created_at) if conv.created_at else None,
                        "updated_at": (
                            str(getattr(conv, "updated_at", None))
                            if hasattr(conv, "updated_at")
                            else None
                        ),
                        "source": conv.source,
                        "model": conv.model,
                    }
                )
            print(json.dumps(data, indent=2))
            return 0

        # Rich table output
        time_label = "Updated" if args.updated else "Created"
        table = Table(title=f"Recent Conversations (by {time_label})")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Flags", width=4)
        table.add_column("Title", style="cyan", max_width=40)
        table.add_column("Slug", style="yellow", max_width=25)
        table.add_column(time_label, style="dim")

        for conv in conversations:
            flags = ""
            if hasattr(conv, "starred_at") and conv.starred_at:
                flags += "⭐"
            if hasattr(conv, "pinned_at") and conv.pinned_at:
                flags += "📌"
            if hasattr(conv, "archived_at") and conv.archived_at:
                flags += "📦"

            title = conv.title or "Untitled"
            if len(title) > 40:
                title = title[:37] + "..."

            slug = getattr(conv, "slug", "") or ""
            if len(slug) > 25:
                slug = slug[:22] + "..."

            timestamp = ""
            if args.updated and hasattr(conv, "updated_at") and conv.updated_at:
                timestamp = conv.updated_at.strftime("%Y-%m-%d %H:%M")
            elif hasattr(conv, "created_at") and conv.created_at:
                timestamp = conv.created_at.strftime("%Y-%m-%d %H:%M")

            table.add_row(conv.id[:8] + "...", flags, title, slug, timestamp)

        console.print(table)
        console.print(f"\n[dim]{len(conversations)} conversation(s)[/dim]")
        return 0


def cmd_count(args):
    """Show count of conversations with optional filters"""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    with ConversationDB(args.db) as db:
        # Build filter kwargs
        kwargs = {"include_archived": args.include_archived}
        if args.starred:
            kwargs["starred"] = True
        if args.pinned:
            kwargs["pinned"] = True
        if args.archived:
            kwargs["archived"] = True
        if args.source:
            kwargs["source"] = args.source
        if args.model:
            kwargs["model"] = args.model
        if args.tags:
            kwargs["tags"] = [t.strip() for t in args.tags.split(",")]

        # For count, we use list with no limit and count the results
        # A more efficient approach would be a dedicated count method
        conversations = db.list_conversations(limit=None, **kwargs)
        count = len(conversations)

        if args.json:
            result = {"count": count}
            if args.starred:
                result["filter"] = "starred"
            elif args.pinned:
                result["filter"] = "pinned"
            elif args.archived:
                result["filter"] = "archived"
            elif args.source:
                result["filter"] = f"source={args.source}"
            elif args.model:
                result["filter"] = f"model={args.model}"
            elif args.tags:
                result["filter"] = f"tags={args.tags}"
            print(json.dumps(result, indent=2))
            return 0

        # Build label
        filter_desc = ""
        if args.starred:
            filter_desc = " (starred)"
        elif args.pinned:
            filter_desc = " (pinned)"
        elif args.archived:
            filter_desc = " (archived)"
        elif args.source:
            filter_desc = f" (source: {args.source})"
        elif args.model:
            filter_desc = f" (model: {args.model})"
        elif args.tags:
            filter_desc = f" (tags: {args.tags})"

        console.print(
            f"[bold]{count:,}[/bold] conversation{'' if count == 1 else 's'}{filter_desc}"
        )
        return 0


def add_lib_commands(subparsers):
    """Add library command group to parser"""
    lib_parser = subparsers.add_parser("lib", help="Library operations")
    lib_subparsers = lib_parser.add_subparsers(
        dest="lib_command", help="Library commands"
    )

    # list
    list_parser = lib_subparsers.add_parser("list", help="List conversations")
    list_parser.add_argument("--db", "-d", required=True, help="Database path")
    list_parser.add_argument("--limit", "-n", type=int, help="Maximum results")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.add_argument("--starred", action="store_true", help="Show only starred")
    list_parser.add_argument("--pinned", action="store_true", help="Show only pinned")
    list_parser.add_argument(
        "--archived", action="store_true", help="Show only archived"
    )
    list_parser.add_argument(
        "--include-archived", action="store_true", help="Include archived"
    )
    list_parser.add_argument("--source", help="Filter by source")
    list_parser.add_argument("--model", help="Filter by model")
    list_parser.add_argument("--tags", help="Filter by tags (comma-separated)")

    # search
    search_parser = lib_subparsers.add_parser("search", help="Search conversations")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--db", "-d", required=True, help="Database path")
    search_parser.add_argument("--limit", "-n", type=int, help="Maximum results")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")
    search_parser.add_argument(
        "--title-only", action="store_true", help="Search titles only"
    )
    search_parser.add_argument(
        "--content-only", action="store_true", help="Search content only"
    )
    search_parser.add_argument("--source", help="Filter by source")
    search_parser.add_argument("--model", help="Filter by model")
    search_parser.add_argument("--tags", help="Filter by tags (comma-separated)")

    # stats
    stats_parser = lib_subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.add_argument("--db", "-d", required=True, help="Database path")

    # tags
    tags_parser = lib_subparsers.add_parser(
        "tags", help="List all tags, or show conversations with a specific tag"
    )
    tags_parser.add_argument("tag", nargs="?", help="Show conversations with this tag")
    tags_parser.add_argument("--db", "-d", required=True, help="Database path")
    tags_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # models
    models_parser = lib_subparsers.add_parser("models", help="List all models")
    models_parser.add_argument("--db", "-d", required=True, help="Database path")
    models_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # sources
    sources_parser = lib_subparsers.add_parser("sources", help="List all sources")
    sources_parser.add_argument("--db", "-d", required=True, help="Database path")
    sources_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # recent
    recent_parser = lib_subparsers.add_parser(
        "recent", help="Show recently updated/created conversations"
    )
    recent_parser.add_argument("--db", "-d", required=True, help="Database path")
    recent_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Maximum results (default: 20)"
    )
    recent_parser.add_argument(
        "--updated",
        "-u",
        action="store_true",
        help="Sort by updated time (default: created)",
    )
    recent_parser.add_argument(
        "--include-archived", action="store_true", help="Include archived conversations"
    )
    recent_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # count
    count_parser = lib_subparsers.add_parser(
        "count", help="Show count of conversations"
    )
    count_parser.add_argument("--db", "-d", required=True, help="Database path")
    count_parser.add_argument(
        "--starred", action="store_true", help="Count only starred"
    )
    count_parser.add_argument("--pinned", action="store_true", help="Count only pinned")
    count_parser.add_argument(
        "--archived", action="store_true", help="Count only archived"
    )
    count_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived in total count",
    )
    count_parser.add_argument("--source", help="Count by source")
    count_parser.add_argument("--model", help="Count by model")
    count_parser.add_argument("--tags", help="Count by tags (comma-separated)")
    count_parser.add_argument("--json", action="store_true", help="Output as JSON")

    return lib_parser


def dispatch_lib_command(args):
    """Dispatch to appropriate lib subcommand"""
    commands = {
        "list": cmd_list,
        "search": cmd_search,
        "stats": cmd_stats,
        "tags": cmd_tags,
        "models": cmd_models,
        "sources": cmd_sources,
        "recent": cmd_recent,
        "count": cmd_count,
    }

    if hasattr(args, "lib_command") and args.lib_command:
        if args.lib_command in commands:
            return commands[args.lib_command](args)
        else:
            print(f"Unknown lib command: {args.lib_command}")
            return 1
    else:
        print(
            "Error: No lib command specified. Use 'ctk lib --help' for available commands."
        )
        return 1
