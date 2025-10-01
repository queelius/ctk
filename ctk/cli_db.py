#!/usr/bin/env python3
"""
Database operations CLI commands for CTK
Implements Unix-philosophy database manipulation tools
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import logging
import json
from glob import glob

from ctk.core.db_operations import (
    DatabaseOperations,
    DuplicateStrategy,
    MergeStrategy,
    ConversationComparator
)
from ctk.core.database import ConversationDB

logger = logging.getLogger(__name__)


def add_db_commands(subparsers):
    """Add database operation commands to CLI"""

    db_parser = subparsers.add_parser(
        'db',
        help='Database operations (merge, diff, intersect, filter, etc.)'
    )

    db_subparsers = db_parser.add_subparsers(
        dest='db_command',
        help='Database operation to perform'
    )

    # MERGE command
    merge_parser = db_subparsers.add_parser(
        'merge',
        help='Merge multiple databases into one'
    )
    merge_parser.add_argument(
        'inputs',
        nargs='+',
        help='Input database files (supports glob patterns)'
    )
    merge_parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output database file'
    )
    merge_parser.add_argument(
        '--strategy',
        choices=['newest', 'oldest', 'longest', 'skip'],
        default='newest',
        help='Conflict resolution strategy (default: newest)'
    )
    merge_parser.add_argument(
        '--dedupe',
        choices=['exact', 'hash', 'similarity', 'smart'],
        default='exact',
        help='Deduplication strategy (default: exact)'
    )
    merge_parser.add_argument(
        '--progress',
        action='store_true',
        help='Show progress during merge'
    )
    merge_parser.set_defaults(func=cmd_merge)

    # DIFF command
    diff_parser = db_subparsers.add_parser(
        'diff',
        help='Find differences between databases'
    )
    diff_parser.add_argument(
        'left',
        help='Left database file'
    )
    diff_parser.add_argument(
        'right',
        help='Right database file'
    )
    diff_parser.add_argument(
        '-o', '--output',
        help='Output database for unique conversations'
    )
    diff_parser.add_argument(
        '--symmetric',
        action='store_true',
        help='Show differences from both sides'
    )
    diff_parser.add_argument(
        '--comparison',
        choices=['exact', 'hash', 'similarity'],
        default='exact',
        help='Comparison method (default: exact)'
    )
    diff_parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show statistics, don\'t save output'
    )
    diff_parser.set_defaults(func=cmd_diff)

    # INTERSECT command
    intersect_parser = db_subparsers.add_parser(
        'intersect',
        help='Find conversations common to multiple databases'
    )
    intersect_parser.add_argument(
        'inputs',
        nargs='+',
        help='Input database files (supports glob patterns)'
    )
    intersect_parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output database file'
    )
    intersect_parser.add_argument(
        '--min-count',
        type=int,
        help='Minimum databases conversation must appear in (default: all)'
    )
    intersect_parser.add_argument(
        '--comparison',
        choices=['exact', 'hash', 'similarity'],
        default='exact',
        help='Comparison method (default: exact)'
    )
    intersect_parser.set_defaults(func=cmd_intersect)

    # FILTER command
    filter_parser = db_subparsers.add_parser(
        'filter',
        help='Filter conversations based on criteria'
    )
    filter_parser.add_argument(
        'input',
        help='Input database file'
    )
    filter_parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output database file'
    )
    filter_parser.add_argument(
        '--source',
        help='Filter by source (chatgpt, claude, copilot, etc.)'
    )
    filter_parser.add_argument(
        '--after',
        type=lambda s: datetime.fromisoformat(s),
        help='Only conversations after date (YYYY-MM-DD)'
    )
    filter_parser.add_argument(
        '--before',
        type=lambda s: datetime.fromisoformat(s),
        help='Only conversations before date (YYYY-MM-DD)'
    )
    filter_parser.add_argument(
        '--tags',
        help='Required tags (comma-separated)'
    )
    filter_parser.add_argument(
        '--min-messages',
        type=int,
        help='Minimum message count'
    )
    filter_parser.add_argument(
        '--max-messages',
        type=int,
        help='Maximum message count'
    )
    filter_parser.add_argument(
        '--query',
        help='SQL WHERE clause for advanced filtering'
    )
    filter_parser.set_defaults(func=cmd_filter)

    # SPLIT command
    split_parser = db_subparsers.add_parser(
        'split',
        help='Split database into multiple databases'
    )
    split_parser.add_argument(
        'input',
        help='Input database file'
    )
    split_parser.add_argument(
        '-o', '--output-dir',
        default='./split',
        help='Output directory for split databases (default: ./split)'
    )
    split_group = split_parser.add_mutually_exclusive_group()
    split_group.add_argument(
        '--by',
        choices=['source', 'month', 'model', 'project'],
        default='source',
        help='Field to split by (default: source)'
    )
    split_group.add_argument(
        '--chunks',
        type=int,
        help='Split into N equal-sized chunks'
    )
    split_parser.set_defaults(func=cmd_split)

    # DEDUPE command
    dedupe_parser = db_subparsers.add_parser(
        'dedupe',
        help='Remove duplicate conversations from database'
    )
    dedupe_parser.add_argument(
        'input',
        help='Input database file'
    )
    dedupe_parser.add_argument(
        '-o', '--output',
        help='Output database file (if not specified, modifies input)'
    )
    dedupe_parser.add_argument(
        '--strategy',
        choices=['exact', 'hash', 'similarity'],
        default='exact',
        help='Deduplication strategy (default: exact)'
    )
    dedupe_parser.add_argument(
        '--similarity',
        type=float,
        default=0.95,
        help='Similarity threshold for fuzzy matching (0-1, default: 0.95)'
    )
    dedupe_parser.add_argument(
        '--keep',
        choices=['newest', 'oldest', 'longest'],
        default='newest',
        help='Which duplicate to keep (default: newest)'
    )
    dedupe_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be removed without actually removing'
    )
    dedupe_parser.set_defaults(func=cmd_dedupe)

    # STATS command
    stats_parser = db_subparsers.add_parser(
        'stats',
        help='Show database statistics and analysis'
    )
    stats_parser.add_argument(
        'inputs',
        nargs='+',
        help='Database files to analyze (supports glob patterns)'
    )
    stats_parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare databases'
    )
    stats_parser.add_argument(
        '--overlap',
        action='store_true',
        help='Show overlap matrix between databases'
    )
    stats_parser.add_argument(
        '--format',
        choices=['text', 'json', 'csv'],
        default='text',
        help='Output format (default: text)'
    )
    stats_parser.set_defaults(func=cmd_stats)

    # VALIDATE command
    validate_parser = db_subparsers.add_parser(
        'validate',
        help='Check database integrity'
    )
    validate_parser.add_argument(
        'input',
        help='Database file to validate'
    )
    validate_parser.add_argument(
        '--repair',
        action='store_true',
        help='Attempt to repair issues'
    )
    validate_parser.add_argument(
        '-o', '--output',
        help='Output file for repaired database'
    )
    validate_parser.set_defaults(func=cmd_validate)

    # QUERY command (advanced SQL-like queries)
    query_parser = db_subparsers.add_parser(
        'query',
        help='Execute SQL-like queries on database'
    )
    query_parser.add_argument(
        'input',
        help='Database file to query'
    )
    query_parser.add_argument(
        'query',
        help='SQL query to execute'
    )
    query_parser.add_argument(
        '--format',
        choices=['text', 'json', 'csv'],
        default='text',
        help='Output format (default: text)'
    )
    query_parser.set_defaults(func=cmd_query)


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
            progress_callback=callback
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
            comparison=comparison
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
            input_files,
            args.output,
            min_count=args.min_count,
            comparison=comparison
        )

        print(f"\nIntersect results:")
        print(f"  Total unique conversations: {stats['total_unique']}")
        print(f"  Common to all databases: {stats['common_to_all']}")

        if args.min_count:
            print(f"  Common to at least {args.min_count} databases: {stats['common_to_min']}")

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
    tags = args.tags.split(',') if args.tags else None

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
            query=args.query
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
            args.input,
            args.output_dir,
            by=args.by,
            chunks=args.chunks
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
            dry_run=args.dry_run
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
    # Expand glob patterns
    input_files = expand_globs(args.inputs)

    print(f"Analyzing {len(input_files)} database(s)...")

    all_stats = {}

    for db_file in input_files:
        try:
            with ConversationDB(db_file) as db:
                stats = db.get_statistics()
                all_stats[db_file] = stats

                if args.format == 'text':
                    print(f"\n{db_file}:")
                    print(f"  Total conversations: {stats['total_conversations']}")
                    print(f"  Total messages: {stats['total_messages']}")
                    print(f"  Messages by role: {stats['messages_by_role']}")

                    if 'sources' in stats:
                        print(f"  Sources: {stats['sources']}")
                    if 'date_range' in stats:
                        print(f"  Date range: {stats['date_range']}")

        except Exception as e:
            print(f"Error reading {db_file}: {e}")

    if args.format == 'json':
        print(json.dumps(all_stats, indent=2, default=str))

    elif args.format == 'csv':
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


def cmd_query(args):
    """Execute query command"""
    print(f"Executing query on {args.input}...")

    try:
        with ConversationDB(args.input) as db:
            with db.session_scope() as session:
                # Execute raw SQL query
                result = session.execute(text(args.query))

                rows = result.fetchall()

                if args.format == 'json':
                    # Convert to JSON-serializable format
                    data = []
                    for row in rows:
                        if hasattr(row, '_asdict'):
                            data.append(row._asdict())
                        else:
                            data.append(list(row))
                    print(json.dumps(data, indent=2, default=str))

                elif args.format == 'csv':
                    # Simple CSV output
                    for row in rows:
                        print(','.join(str(v) for v in row))

                else:  # text
                    for row in rows:
                        print(row)

                print(f"\n{len(rows)} row(s) returned")

        return 0

    except Exception as e:
        print(f"Query failed: {e}")
        logger.exception("Query execution failed")
        return 1