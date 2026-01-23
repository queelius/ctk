#!/usr/bin/env python3
"""
Database operations CLI commands for CTK
Implements Unix-philosophy database manipulation tools
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.db_operations import (ConversationComparator, DatabaseOperations,
                                    DuplicateStrategy, MergeStrategy)

logger = logging.getLogger(__name__)


def get_db_size(db_path: str) -> int:
    """Get database file size in bytes"""
    path = Path(db_path)
    if path.exists():
        return path.stat().st_size
    return 0


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def add_db_commands(subparsers):
    """Add database operation commands to CLI"""

    db_parser = subparsers.add_parser(
        "db", help="Database operations (merge, diff, intersect, filter, etc.)"
    )

    db_subparsers = db_parser.add_subparsers(
        dest="db_command", help="Database operation to perform"
    )

    # INIT command
    init_parser = db_subparsers.add_parser("init", help="Initialize a new database")
    init_parser.add_argument(
        "path", nargs="?", help="Path for new database (default: uses configured path)"
    )
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing database"
    )
    init_parser.set_defaults(func=cmd_init)

    # INFO command
    info_parser = db_subparsers.add_parser("info", help="Show database information")
    info_parser.add_argument(
        "path", nargs="?", help="Database path (default: uses configured path)"
    )
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")
    info_parser.set_defaults(func=cmd_info)

    # VACUUM command
    vacuum_parser = db_subparsers.add_parser(
        "vacuum", help="Reclaim unused space and optimize database"
    )
    vacuum_parser.add_argument(
        "path", nargs="?", help="Database path (default: uses configured path)"
    )
    vacuum_parser.add_argument(
        "--analyze",
        action="store_true",
        help="Also run ANALYZE to update query statistics",
    )
    vacuum_parser.set_defaults(func=cmd_vacuum)

    # BACKUP command
    backup_parser = db_subparsers.add_parser(
        "backup", help="Create a backup of the database"
    )
    backup_parser.add_argument(
        "output", nargs="?", help="Backup destination (default: timestamped file)"
    )
    backup_parser.add_argument(
        "--source", help="Source database (default: uses configured path)"
    )
    backup_parser.add_argument(
        "--compress", action="store_true", help="Compress backup with gzip"
    )
    backup_parser.set_defaults(func=cmd_backup)

    # MERGE command
    merge_parser = db_subparsers.add_parser(
        "merge", help="Merge multiple databases into one"
    )
    merge_parser.add_argument(
        "inputs", nargs="+", help="Input database files (supports glob patterns)"
    )
    merge_parser.add_argument(
        "-o", "--output", required=True, help="Output database file"
    )
    merge_parser.add_argument(
        "--strategy",
        choices=["newest", "oldest", "longest", "skip"],
        default="newest",
        help="Conflict resolution strategy (default: newest)",
    )
    merge_parser.add_argument(
        "--dedupe",
        choices=["exact", "hash", "similarity", "smart"],
        default="exact",
        help="Deduplication strategy (default: exact)",
    )
    merge_parser.add_argument(
        "--progress", action="store_true", help="Show progress during merge"
    )
    merge_parser.set_defaults(func=cmd_merge)

    # DIFF command
    diff_parser = db_subparsers.add_parser(
        "diff", help="Find differences between databases"
    )
    diff_parser.add_argument("left", help="Left database file")
    diff_parser.add_argument("right", help="Right database file")
    diff_parser.add_argument(
        "-o", "--output", help="Output database for unique conversations"
    )
    diff_parser.add_argument(
        "--symmetric", action="store_true", help="Show differences from both sides"
    )
    diff_parser.add_argument(
        "--comparison",
        choices=["exact", "hash", "similarity"],
        default="exact",
        help="Comparison method (default: exact)",
    )
    diff_parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, don't save output",
    )
    diff_parser.set_defaults(func=cmd_diff)

    # INTERSECT command
    intersect_parser = db_subparsers.add_parser(
        "intersect", help="Find conversations common to multiple databases"
    )
    intersect_parser.add_argument(
        "inputs", nargs="+", help="Input database files (supports glob patterns)"
    )
    intersect_parser.add_argument(
        "-o", "--output", required=True, help="Output database file"
    )
    intersect_parser.add_argument(
        "--min-count",
        type=int,
        help="Minimum databases conversation must appear in (default: all)",
    )
    intersect_parser.add_argument(
        "--comparison",
        choices=["exact", "hash", "similarity"],
        default="exact",
        help="Comparison method (default: exact)",
    )
    intersect_parser.set_defaults(func=cmd_intersect)

    # FILTER command
    filter_parser = db_subparsers.add_parser(
        "filter", help="Filter conversations based on criteria"
    )
    filter_parser.add_argument("input", help="Input database file")
    filter_parser.add_argument(
        "-o", "--output", required=True, help="Output database file"
    )
    filter_parser.add_argument(
        "--source", help="Filter by source (chatgpt, claude, copilot, etc.)"
    )
    filter_parser.add_argument(
        "--after",
        type=lambda s: datetime.fromisoformat(s),
        help="Only conversations after date (YYYY-MM-DD)",
    )
    filter_parser.add_argument(
        "--before",
        type=lambda s: datetime.fromisoformat(s),
        help="Only conversations before date (YYYY-MM-DD)",
    )
    filter_parser.add_argument("--tags", help="Required tags (comma-separated)")
    filter_parser.add_argument("--min-messages", type=int, help="Minimum message count")
    filter_parser.add_argument("--max-messages", type=int, help="Maximum message count")
    filter_parser.add_argument(
        "--query", help="SQL WHERE clause for advanced filtering"
    )
    filter_parser.set_defaults(func=cmd_filter)

    # SPLIT command
    split_parser = db_subparsers.add_parser(
        "split", help="Split database into multiple databases"
    )
    split_parser.add_argument("input", help="Input database file")
    split_parser.add_argument(
        "-o",
        "--output-dir",
        default="./split",
        help="Output directory for split databases (default: ./split)",
    )
    split_group = split_parser.add_mutually_exclusive_group()
    split_group.add_argument(
        "--by",
        choices=["source", "month", "model", "project"],
        default="source",
        help="Field to split by (default: source)",
    )
    split_group.add_argument(
        "--chunks", type=int, help="Split into N equal-sized chunks"
    )
    split_parser.set_defaults(func=cmd_split)

    # DEDUPE command
    dedupe_parser = db_subparsers.add_parser(
        "dedupe", help="Remove duplicate conversations from database"
    )
    dedupe_parser.add_argument("input", help="Input database file")
    dedupe_parser.add_argument(
        "-o", "--output", help="Output database file (if not specified, modifies input)"
    )
    dedupe_parser.add_argument(
        "--strategy",
        choices=["exact", "hash", "similarity"],
        default="exact",
        help="Deduplication strategy (default: exact)",
    )
    dedupe_parser.add_argument(
        "--similarity",
        type=float,
        default=0.95,
        help="Similarity threshold for fuzzy matching (0-1, default: 0.95)",
    )
    dedupe_parser.add_argument(
        "--keep",
        choices=["newest", "oldest", "longest"],
        default="newest",
        help="Which duplicate to keep (default: newest)",
    )
    dedupe_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually removing",
    )
    dedupe_parser.set_defaults(func=cmd_dedupe)

    # STATS command
    stats_parser = db_subparsers.add_parser(
        "stats", help="Show database statistics and analysis"
    )
    stats_parser.add_argument(
        "inputs", nargs="+", help="Database files to analyze (supports glob patterns)"
    )
    stats_parser.add_argument(
        "--compare", action="store_true", help="Compare databases"
    )
    stats_parser.add_argument(
        "--overlap", action="store_true", help="Show overlap matrix between databases"
    )
    stats_parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )
    stats_parser.set_defaults(func=cmd_stats)

    # VALIDATE command
    validate_parser = db_subparsers.add_parser(
        "validate", help="Check database integrity"
    )
    validate_parser.add_argument("input", help="Database file to validate")
    validate_parser.add_argument(
        "--repair", action="store_true", help="Attempt to repair issues"
    )
    validate_parser.add_argument(
        "-o", "--output", help="Output file for repaired database"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # NOTE: ctk db query removed - use 'ctk sql' instead for raw SQL queries


def expand_globs(patterns: List[str]) -> List[str]:
    """Expand glob patterns to actual file paths"""
    files = []
    for pattern in patterns:
        matches = glob(pattern)
        if matches:
            files.extend(matches)
        else:
            # If no matches, treat as literal filename
            files.append(pattern)
    return files


def print_progress(stats: dict):
    """Print progress update"""
    sys.stderr.write(
        f"\rProcessed: {stats.get('total_input', 0)} | "
        f"Output: {stats.get('total_output', 0)} | "
        f"Duplicates: {stats.get('duplicates_found', 0)}"
    )
    sys.stderr.flush()


def cmd_merge(args):
    """Execute merge command"""
    db_ops = DatabaseOperations()

    # Expand glob patterns
    input_files = expand_globs(args.inputs)

    if len(input_files) < 2:
        print("Error: Need at least 2 databases to merge")
        return 1

    print(f"Merging {len(input_files)} databases...")

    # Convert string strategies to enums
    strategy = MergeStrategy[args.strategy.upper()]
    dedupe = DuplicateStrategy[args.dedupe.upper()]

    # Setup progress callback if requested
    callback = print_progress if args.progress else None

    try:
        stats = db_ops.merge(
            input_files,
            args.output,
            strategy=strategy,
            dedupe=dedupe,
            progress_callback=callback,
        )

        if args.progress:
            print()  # New line after progress

        print(f"\nMerge completed:")
        print(f"  Total input conversations: {stats['total_input']}")
        print(f"  Total output conversations: {stats['total_output']}")
        print(f"  Duplicates found: {stats['duplicates_found']}")
        print(f"  Conflicts resolved: {stats['conflicts_resolved']}")
        print(f"  Output saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error during merge: {e}")
        logger.exception("Merge failed")
        return 1


def cmd_diff(args):
    """Execute diff command"""
    db_ops = DatabaseOperations()

    print(f"Comparing {args.left} vs {args.right}...")

    # Convert string comparison to enum
    comparison = DuplicateStrategy[args.comparison.upper()]

    try:
        stats = db_ops.diff(
            args.left,
            args.right,
            output_db=args.output if not args.stats_only else None,
            symmetric=args.symmetric,
            comparison=comparison,
        )

        print(f"\nDiff results:")
        print(f"  Left database total: {stats['left_total']}")
        print(f"  Right database total: {stats['right_total']}")
        print(f"  Common conversations: {stats['common']}")
        print(f"  Unique to left: {stats['left_unique']}")

        if args.symmetric:
            print(f"  Unique to right: {stats['right_unique']}")

        if args.output and not args.stats_only:
            print(f"  Unique conversations saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error during diff: {e}")
        logger.exception("Diff failed")
        return 1


def cmd_intersect(args):
    """Execute intersect command"""
    db_ops = DatabaseOperations()

    # Expand glob patterns
    input_files = expand_globs(args.inputs)

    if len(input_files) < 2:
        print("Error: Need at least 2 databases to intersect")
        return 1

    print(f"Finding common conversations across {len(input_files)} databases...")

    # Convert string comparison to enum
    comparison = DuplicateStrategy[args.comparison.upper()]

    try:
        stats = db_ops.intersect(
            input_files, args.output, min_count=args.min_count, comparison=comparison
        )

        print(f"\nIntersect results:")
        print(f"  Total unique conversations: {stats['total_unique']}")
        print(f"  Common to all databases: {stats['common_to_all']}")

        if args.min_count:
            print(
                f"  Common to at least {args.min_count} databases: {stats['common_to_min']}"
            )

        print(f"  Output saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error during intersect: {e}")
        logger.exception("Intersect failed")
        return 1


def cmd_filter(args):
    """Execute filter command"""
    db_ops = DatabaseOperations()

    print(f"Filtering {args.input}...")

    # Parse tags if provided
    tags = args.tags.split(",") if args.tags else None

    try:
        stats = db_ops.filter(
            args.input,
            args.output,
            source=args.source,
            after=args.after,
            before=args.before,
            tags=tags,
            min_messages=args.min_messages,
            max_messages=args.max_messages,
            query=args.query,
        )

        print(f"\nFilter results:")
        print(f"  Total input conversations: {stats['total_input']}")
        print(f"  Filtered out: {stats['filtered_out']}")
        print(f"  Output conversations: {stats['total_output']}")
        print(f"  Output saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error during filter: {e}")
        logger.exception("Filter failed")
        return 1


def cmd_split(args):
    """Execute split command"""
    db_ops = DatabaseOperations()

    if args.chunks:
        print(f"Splitting {args.input} into {args.chunks} chunks...")
    else:
        print(f"Splitting {args.input} by {args.by}...")

    try:
        stats = db_ops.split(
            args.input, args.output_dir, by=args.by, chunks=args.chunks
        )

        print(f"\nSplit results:")
        print(f"  Total conversations: {stats['total_conversations']}")
        print(f"  Databases created: {stats['databases_created']}")
        print(f"  Split by: {stats['split_by']}")
        print(f"  Output directory: {args.output_dir}")

        return 0

    except Exception as e:
        print(f"Error during split: {e}")
        logger.exception("Split failed")
        return 1


def cmd_dedupe(args):
    """Execute dedupe command"""
    db_ops = DatabaseOperations()

    if args.dry_run:
        print(f"Analyzing duplicates in {args.input} (dry run)...")
    else:
        print(f"Removing duplicates from {args.input}...")

    # Convert string strategy to enum
    strategy = DuplicateStrategy[args.strategy.upper()]

    try:
        stats = db_ops.dedupe(
            args.input,
            output_db=args.output,
            strategy=strategy,
            similarity_threshold=args.similarity,
            keep=args.keep,
            dry_run=args.dry_run,
        )

        print(f"\nDedupe results:")
        print(f"  Total conversations: {stats['total_conversations']}")
        print(f"  Duplicate groups found: {stats['groups_found']}")
        print(f"  Duplicates found: {stats['duplicates_found']}")

        if args.dry_run:
            print(f"  Would keep: {stats['conversations_kept']}")
            print(f"  Would remove: {stats['duplicates_found']}")
        else:
            print(f"  Conversations kept: {stats['conversations_kept']}")
            print(f"  Conversations removed: {stats['conversations_removed']}")

            if args.output:
                print(f"  Output saved to: {args.output}")
            else:
                print(f"  Database modified in place: {args.input}")

        return 0

    except Exception as e:
        print(f"Error during dedupe: {e}")
        logger.exception("Dedupe failed")
        return 1


def cmd_stats(args):
    """Execute stats command"""
    import sys

    print(
        "[DEPRECATED] 'ctk db stats' is deprecated. Use 'ctk lib stats' instead.",
        file=sys.stderr,
    )

    # Expand glob patterns
    input_files = expand_globs(args.inputs)

    print(f"Analyzing {len(input_files)} database(s)...")

    all_stats = {}

    for db_file in input_files:
        try:
            with ConversationDB(db_file) as db:
                stats = db.get_statistics()
                all_stats[db_file] = stats

                if args.format == "text":
                    print(f"\n{db_file}:")
                    print(f"  Total conversations: {stats['total_conversations']}")
                    print(f"  Total messages: {stats['total_messages']}")
                    print(f"  Messages by role: {stats['messages_by_role']}")

                    if "sources" in stats:
                        print(f"  Sources: {stats['sources']}")
                    if "date_range" in stats:
                        print(f"  Date range: {stats['date_range']}")

        except Exception as e:
            print(f"Error reading {db_file}: {e}")

    if args.format == "json":
        print(json.dumps(all_stats, indent=2, default=str))

    elif args.format == "csv":
        # Simple CSV output
        print("database,conversations,messages")
        for db, stats in all_stats.items():
            print(f"{db},{stats['total_conversations']},{stats['total_messages']}")

    if args.overlap and len(input_files) > 1:
        print("\n[Overlap analysis would go here - not yet implemented]")

    return 0


def cmd_validate(args):
    """Execute validate command"""
    print(f"Validating {args.input}...")

    try:
        with ConversationDB(args.input) as db:
            # Basic validation - try to get statistics
            stats = db.get_statistics()
            print(f"Database appears valid:")
            print(f"  Conversations: {stats['total_conversations']}")
            print(f"  Messages: {stats['total_messages']}")

            # Check for orphaned messages, invalid references, etc.
            # This would require additional methods in ConversationDB

            if args.repair and args.output:
                print(f"Repair functionality not yet implemented")
                # Would copy valid data to new database

        return 0

    except Exception as e:
        print(f"Database validation failed: {e}")

        if args.repair and args.output:
            print("Attempting repair...")
            # Would attempt to recover what we can

        return 1


def get_default_db_path() -> str:
    """Get default database path from config"""
    from ctk.core.config import get_config

    config = get_config()
    db_path = config.get("database.default_path", "~/.ctk/conversations.db")
    return str(Path(db_path).expanduser())


def resolve_db_path(path_arg: Optional[str]) -> tuple[Path, Path]:
    """
    Resolve database path, handling directory structure.

    ConversationDB expects a directory for SQLite, which will contain:
    - conversations.db (the actual SQLite file)
    - media/ (for attachments)

    Returns:
        Tuple of (db_dir, db_file) paths
    """
    db_path = path_arg if path_arg else get_default_db_path()
    path = Path(db_path).expanduser()

    # If it looks like a file path (has .db suffix), use parent as dir
    if path.suffix == ".db":
        db_dir = path.parent
        db_file = path
    else:
        # It's a directory path
        db_dir = path
        db_file = path / "conversations.db"

    return db_dir, db_file


def cmd_init(args):
    """Initialize a new database"""
    import shutil

    from rich.console import Console

    console = Console()

    # Get database path
    db_dir, db_file = resolve_db_path(args.path)

    # Check if exists
    if db_file.exists() and not args.force:
        console.print(f"[yellow]Database already exists:[/yellow] {db_file}")
        console.print("Use --force to overwrite")
        return 1

    # Remove existing if force
    if db_dir.exists() and args.force:
        shutil.rmtree(db_dir)
        console.print(f"[yellow]Removed existing database directory[/yellow]")

    try:
        # Create new database (ConversationDB handles directory creation)
        with ConversationDB(str(db_dir)) as db:
            stats = db.get_statistics()

        console.print(f"[green]✓ Initialized database:[/green] {db_file}")
        console.print(f"  Directory: {db_dir}")
        console.print(f"  Size: {format_size(get_db_size(str(db_file)))}")
        return 0

    except Exception as e:
        console.print(f"[red]Error initializing database:[/red] {e}")
        logger.exception("Database initialization failed")
        return 1


def cmd_info(args):
    """Show database information"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Get database path
    db_dir, db_file = resolve_db_path(args.path)

    if not db_file.exists():
        console.print(f"[red]Database not found:[/red] {db_file}")
        return 1

    try:
        with ConversationDB(str(db_dir)) as db:
            stats = db.get_statistics()

            # Get additional info via raw SQL
            with db.session_scope() as session:
                # Get table sizes
                table_info = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                ).fetchall()

                # Get SQLite version
                sqlite_version = session.execute(
                    text("SELECT sqlite_version()")
                ).fetchone()[0]

                # Get page size and count
                page_size = session.execute(text("PRAGMA page_size")).fetchone()[0]
                page_count = session.execute(text("PRAGMA page_count")).fetchone()[0]

                # Get freelist count (unused pages)
                freelist = session.execute(text("PRAGMA freelist_count")).fetchone()[0]

        if args.json:
            info = {
                "path": str(db_file),
                "size_bytes": get_db_size(str(db_file)),
                "size_human": format_size(get_db_size(str(db_file))),
                "sqlite_version": sqlite_version,
                "page_size": page_size,
                "page_count": page_count,
                "freelist_pages": freelist,
                "tables": [t[0] for t in table_info],
                **stats,
            }
            print(json.dumps(info, indent=2, default=str))
            return 0

        # Rich table output
        console.print(f"\n[bold cyan]Database Information[/bold cyan]")
        console.print(f"  Path: {db_file}")
        console.print(f"  Size: {format_size(get_db_size(str(db_file)))}")
        console.print(f"  SQLite version: {sqlite_version}")
        console.print()

        console.print("[bold]Content Statistics:[/bold]")
        console.print(f"  Conversations: {stats.get('total_conversations', 0)}")
        console.print(f"  Messages: {stats.get('total_messages', 0)}")
        if stats.get("messages_by_role"):
            for role, count in stats["messages_by_role"].items():
                console.print(f"    {role}: {count}")
        console.print()

        console.print("[bold]Storage Details:[/bold]")
        console.print(f"  Page size: {page_size} bytes")
        console.print(f"  Total pages: {page_count}")
        console.print(
            f"  Used space: {format_size(page_size * (page_count - freelist))}"
        )
        console.print(f"  Free pages: {freelist} ({format_size(page_size * freelist)})")
        console.print()

        console.print("[bold]Tables:[/bold]")
        for table in table_info:
            console.print(f"  • {table[0]}")

        return 0

    except Exception as e:
        console.print(f"[red]Error reading database:[/red] {e}")
        logger.exception("Database info failed")
        return 1


def cmd_vacuum(args):
    """Vacuum database to reclaim space"""
    from rich.console import Console

    console = Console()

    # Get database path
    db_dir, db_file = resolve_db_path(args.path)

    if not db_file.exists():
        console.print(f"[red]Database not found:[/red] {db_file}")
        return 1

    size_before = get_db_size(str(db_file))

    try:
        console.print(f"Vacuuming {db_file}...")

        with ConversationDB(str(db_dir)) as db:
            with db.session_scope() as session:
                # Run VACUUM
                session.execute(text("VACUUM"))

                if args.analyze:
                    console.print("Running ANALYZE...")
                    session.execute(text("ANALYZE"))

        size_after = get_db_size(str(db_file))
        saved = size_before - size_after

        console.print(f"\n[green]✓ Vacuum completed[/green]")
        console.print(f"  Before: {format_size(size_before)}")
        console.print(f"  After:  {format_size(size_after)}")

        if saved > 0:
            console.print(
                f"  Saved:  {format_size(saved)} ({100 * saved / size_before:.1f}%)"
            )
        else:
            console.print(f"  [dim]No space reclaimed[/dim]")

        return 0

    except Exception as e:
        console.print(f"[red]Error during vacuum:[/red] {e}")
        logger.exception("Vacuum failed")
        return 1


def cmd_backup(args):
    """Create database backup"""
    import gzip
    import shutil

    from rich.console import Console

    console = Console()

    # Get source database path
    source_dir, source_file = resolve_db_path(args.source)

    if not source_file.exists():
        console.print(f"[red]Source database not found:[/red] {source_file}")
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output).expanduser()
        # If output looks like a directory, append filename
        if not output_path.suffix:
            output_path = output_path / source_file.name
        if args.compress and not output_path.suffix.endswith(".gz"):
            output_path = Path(str(output_path) + ".gz")
        output_file = output_path
    else:
        # Generate timestamped backup name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{source_file.stem}_backup_{timestamp}{source_file.suffix}"
        if args.compress:
            backup_name += ".gz"
        output_file = source_file.parent / backup_name

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        console.print(f"Backing up {source_file}...")

        if args.compress:
            # Compressed backup
            with open(source_file, "rb") as f_in:
                with gzip.open(output_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            # Simple copy
            shutil.copy2(source_file, output_file)

        source_size = get_db_size(str(source_file))
        output_size = get_db_size(str(output_file))

        console.print(f"\n[green]✓ Backup created[/green]")
        console.print(f"  Source: {source_file} ({format_size(source_size)})")
        console.print(f"  Backup: {output_file} ({format_size(output_size)})")

        if args.compress and output_size < source_size:
            ratio = 100 * (1 - output_size / source_size)
            console.print(f"  Compression: {ratio:.1f}% reduction")

        return 0

    except Exception as e:
        console.print(f"[red]Error creating backup:[/red] {e}")
        logger.exception("Backup failed")
        return 1
