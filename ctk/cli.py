#!/usr/bin/env python3
"""
Conversation Toolkit CLI with automatic plugin discovery
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List
import logging

from ctk.core.database import ConversationDB
from ctk.core.plugin import registry
from ctk.core.sanitizer import Sanitizer


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_import(args):
    """Import conversations from file or auto-search"""
    registry.discover_plugins()

    # Handle auto-search for specific formats
    auto_search_formats = ['copilot', 'claude_code', 'cursor']

    # Check if we should auto-search
    if args.input == 'auto' and args.format in auto_search_formats:
        # Auto-search for the specified format
        print(f"Auto-searching for {args.format} data...")

        if args.format == 'copilot':
            from ctk.integrations.importers.copilot import CopilotImporter
            found_paths = CopilotImporter.find_copilot_data()

            if not found_paths:
                print(f"No Copilot data found in VS Code storage")
                print(f"Searched in:")
                import platform
                system = platform.system().lower()
                if system == 'windows':
                    system = 'win32'
                for path in CopilotImporter.STORAGE_PATHS.get(system, CopilotImporter.STORAGE_PATHS['linux']):
                    print(f"  {path}")
                return 1

            print(f"Found {len(found_paths)} Copilot storage location(s)")
            conversations = []
            importer = CopilotImporter()

            for path in found_paths:
                print(f"  Importing from: {path}")
                path_conversations = importer.import_data(str(path))
                conversations.extend(path_conversations)

        # Add more auto-search formats here as needed
        else:
            print(f"Auto-search not yet implemented for {args.format}")
            return 1

    else:
        # Normal file import
        input_path = Path(args.input)
        if not input_path.exists():
            # If file doesn't exist and format is searchable, suggest auto mode
            if args.format in auto_search_formats:
                print(f"Error: File not found: {input_path}")
                print(f"\nTip: Use 'ctk import auto --format {args.format}' to auto-search for {args.format} data")
            else:
                print(f"Error: File not found: {input_path}")
            return 1

        # Import conversations
        if args.format:
            importer = registry.get_importer(args.format)
            if not importer:
                print(f"Error: Unknown format: {args.format}")
                print(f"Available formats: {', '.join(registry.list_importers())}")
                return 1

            with open(input_path, 'r') as f:
                data = f.read()
                # Only try to parse as JSON if it's NOT a JSONL format
                # JSONL needs to be kept as string for line-by-line parsing
                if args.format not in ['jsonl', 'local', 'llama', 'mistral', 'alpaca']:
                    try:
                        data = json.loads(data)
                    except:
                        pass  # Keep as string if not JSON

            conversations = importer.import_data(data)
        else:
            # Auto-detect format
            conversations = registry.import_file(str(input_path))

    try:
        print(f"Imported {len(conversations)} conversation(s)")

        # Save to database if requested
        if args.db:
            try:
                db = ConversationDB(args.db)
            except (ValueError, Exception) as e:
                print(f"Error: Cannot open database: {e}")
                return 1

            with db:
                for conv in conversations:
                    # Add tags from command line
                    if args.tags:
                        conv.metadata.tags.extend(args.tags.split(','))

                    conv_id = db.save_conversation(conv)
                    print(f"  Saved: {conv.title or 'Untitled'} ({conv_id})")
        
        # Export to file if requested
        if args.output:
            output_format = args.output_format or 'jsonl'
            exporter = registry.get_exporter(output_format)
            if not exporter:
                print(f"Error: Unknown export format: {output_format}")
                return 1
            
            export_kwargs = {
                'sanitize': args.sanitize,
                'path_selection': args.path_selection,
            }
            
            exporter.export_to_file(conversations, args.output, **export_kwargs)
            print(f"Exported to {args.output} in {output_format} format")
        
        return 0
        
    except Exception as e:
        print(f"Error importing file: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_export(args):
    """Export conversations from database"""
    registry.discover_plugins()
    
    if not args.db:
        print("Error: Database path required for export")
        return 1

    try:
        db = ConversationDB(args.db)
    except (ValueError, Exception) as e:
        print(f"Error: Cannot open database: {e}")
        return 1

    with db:
        # Load conversations
        conversations = []
        
        if args.ids:
            # Export specific conversations
            for conv_id in args.ids:
                conv = db.load_conversation(conv_id)
                if conv:
                    conversations.append(conv)
                else:
                    print(f"Warning: Conversation {conv_id} not found")
        else:
            # Export all or filtered conversations
            conv_list = db.list_conversations(limit=args.limit)
            for conv_info in conv_list:
                conv = db.load_conversation(conv_info['id'])
                if conv:
                    # Apply filters
                    if args.filter_source and conv.metadata.source != args.filter_source:
                        continue
                    if args.filter_model and args.filter_model not in (conv.metadata.model or ''):
                        continue
                    if args.filter_tags:
                        required_tags = set(args.filter_tags.split(','))
                        if not required_tags.issubset(set(conv.metadata.tags)):
                            continue
                    
                    conversations.append(conv)
        
        if not conversations:
            print("No conversations found matching criteria")
            return 1
        
        print(f"Exporting {len(conversations)} conversation(s)")
        
        # Export
        format_name = args.format or 'jsonl'
        exporter = registry.get_exporter(format_name)
        if not exporter:
            print(f"Error: Unknown export format: {format_name}")
            print(f"Available formats: {', '.join(registry.list_exporters())}")
            return 1
        
        export_kwargs = {
            'sanitize': args.sanitize,
            'path_selection': args.path_selection,
            'include_metadata': args.include_metadata,
        }

        # Add HTML-specific options if present
        if hasattr(args, 'theme'):
            export_kwargs['theme'] = args.theme
        if hasattr(args, 'group_by'):
            export_kwargs['group_by'] = args.group_by
        if hasattr(args, 'show_tree'):
            export_kwargs['show_tree'] = args.show_tree

        exporter.export_to_file(conversations, args.output, **export_kwargs)
        print(f"Exported to {args.output}")
        
        return 0


def cmd_list(args):
    """List conversations in database"""
    if not args.db:
        print("Error: Database path required")
        return 1
    
    with ConversationDB(args.db) as db:
        conversations = db.list_conversations(limit=args.limit)
        
        if not conversations:
            print("No conversations found")
            return 0
        
        # Display format
        if args.json:
            print(json.dumps(conversations, indent=2))
        else:
            print(f"{'ID':<40} {'Title':<50} {'Model':<20} {'Updated'}")
            print("-" * 130)
            for conv in conversations:
                title = conv['title'] or 'Untitled'
                if len(title) > 47:
                    title = title[:47] + '...'
                model = conv['model'] or 'Unknown'
                if len(model) > 17:
                    model = model[:17] + '...'
                updated = conv['updated_at'] or 'Unknown'
                if len(updated) > 19:
                    updated = updated[:19]
                
                print(f"{conv['id']:<40} {title:<50} {model:<20} {updated}")
        
        return 0


def cmd_search(args):
    """Advanced search for conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1

    with ConversationDB(args.db) as db:
        # Parse date arguments
        date_from = None
        date_to = None
        if args.date_from:
            from datetime import datetime
            date_from = datetime.fromisoformat(args.date_from)
        if args.date_to:
            from datetime import datetime
            date_to = datetime.fromisoformat(args.date_to)

        # Parse tags
        tags = args.tags.split(',') if args.tags else None

        results = db.search_conversations(
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
            order_by=args.order_by,
            ascending=args.ascending
        )

        if not results:
            print("No conversations found matching criteria")
            return 0

        # Display results
        if args.format == 'json':
            import json
            print(json.dumps(results, indent=2, default=str))
        elif args.format == 'csv':
            print("ID,Title,Messages,Source,Model,Created,Updated")
            for conv in results:
                print(f"{conv['id']},{conv.get('title', 'Untitled')},{conv.get('message_count', 0)},"
                      f"{conv.get('source', '')},{conv.get('model', '')},"
                      f"{conv.get('created_at', '')},{conv.get('updated_at', '')}")
        else:  # default table format
            print(f"Found {len(results)} conversation(s):\n")
            print(f"{'ID':<40} {'Title':<50} {'Msgs':<6} {'Source':<10} {'Model':<15}")
            print("-" * 130)
            for conv in results:
                title = conv.get('title', 'Untitled')[:50]
                print(f"{conv['id']:<40} {title:<50} {conv.get('message_count', 0):<6} "
                      f"{conv.get('source', ''):<10} {conv.get('model', '')[:15]:<15}")

        return 0


def cmd_stats(args):
    """Show enhanced database statistics"""
    if not args.db:
        print("Error: Database path required")
        return 1

    with ConversationDB(args.db) as db:
        stats = db.get_statistics()

        print("═" * 60)
        print(f"{'📊 Database Statistics':^60}")
        print("═" * 60)

        print(f"\n📚 Conversations: {stats['total_conversations']:,}")
        print(f"💬 Messages: {stats['total_messages']:,}")
        print(f"🏷️  Tags: {stats['total_tags']:,}")

        if stats['messages_by_role']:
            print("\n📝 Messages by Role:")
            for role, count in sorted(stats['messages_by_role'].items(), key=lambda x: x[1], reverse=True):
                bar = '█' * min(40, count // (max(stats['messages_by_role'].values()) // 40 + 1))
                print(f"  {role:12} {count:7,} {bar}")

        if stats['conversations_by_source']:
            print("\n🌐 Conversations by Source:")
            for source, count in sorted(stats['conversations_by_source'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {source:20} {count:7,}")

        if stats.get('top_tags'):
            print("\n🏆 Top Tags:")
            for tag in stats['top_tags'][:10]:
                print(f"  {tag['name']:30} {tag['count']:5,} uses")

        # Add timeline if requested
        if args.timeline:
            timeline = db.get_conversation_timeline(granularity=args.timeline, limit=10)
            print(f"\n📅 Recent Activity ({args.timeline}):")
            for entry in timeline:
                print(f"  {entry['period']:15} {entry['count']:5,} conversations")

        # Add models breakdown
        if args.show_models:
            models = db.get_models()
            print("\n🤖 Models Used:")
            for model_info in models[:10]:
                print(f"  {model_info['model']:30} {model_info['count']:5,} conversations")

        return 0


def cmd_plugins(args):
    """List available plugins"""
    registry.discover_plugins()

    print("Available Importers:")
    for name in registry.list_importers():
        importer = registry.get_importer(name)
        print(f"  {name}: {importer.description}")

    print("\nAvailable Exporters:")
    for name in registry.list_exporters():
        exporter = registry.get_exporter(name)
        print(f"  {name}: {exporter.description}")

    return 0


def cmd_tags(args):
    """Manage and view tags"""
    if not args.db:
        print("Error: Database path required")
        return 1

    with ConversationDB(args.db) as db:
        if args.add and args.conversation_id:
            # Add tags to a conversation
            conv = db.load_conversation(args.conversation_id)
            if not conv:
                print(f"Error: Conversation {args.conversation_id} not found")
                return 1

            new_tags = args.add.split(',')
            conv.metadata.tags.extend(new_tags)
            db.save_conversation(conv)
            print(f"Added tags to conversation: {', '.join(new_tags)}")

        elif args.remove and args.conversation_id:
            # Remove tags from a conversation
            conv = db.load_conversation(args.conversation_id)
            if not conv:
                print(f"Error: Conversation {args.conversation_id} not found")
                return 1

            tags_to_remove = set(args.remove.split(','))
            conv.metadata.tags = [t for t in conv.metadata.tags if t not in tags_to_remove]
            db.save_conversation(conv)
            print(f"Removed tags from conversation: {', '.join(tags_to_remove)}")

        else:
            # List all tags
            tags = db.get_all_tags(with_counts=True)

            if not tags:
                print("No tags found in database")
                return 0

            # Group by category if present
            categorized = {}
            uncategorized = []

            for tag in tags:
                if tag.get('category'):
                    if tag['category'] not in categorized:
                        categorized[tag['category']] = []
                    categorized[tag['category']].append(tag)
                else:
                    uncategorized.append(tag)

            print(f"📏 Total Tags: {len(tags)}\n")

            # Show categorized tags
            for category, cat_tags in sorted(categorized.items()):
                print(f"\n📁 {category.upper()}:")
                for tag in sorted(cat_tags, key=lambda x: x.get('usage_count', 0), reverse=True):
                    count = tag.get('usage_count', 0)
                    bar = '█' * min(30, count // 10 + 1)
                    print(f"  {tag['name']:30} {count:5} {bar}")

            # Show uncategorized tags
            if uncategorized:
                print(f"\n🏷️  UNCATEGORIZED:")
                for tag in sorted(uncategorized, key=lambda x: x.get('usage_count', 0), reverse=True)[:20]:
                    count = tag.get('usage_count', 0)
                    bar = '█' * min(30, count // 10 + 1)
                    print(f"  {tag['name']:30} {count:5} {bar}")

    return 0


def cmd_models(args):
    """List all models used in conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1

    with ConversationDB(args.db) as db:
        models = db.get_models()

        if not models:
            print("No models found in database")
            return 0

        print(f"🤖 Models Used ({len(models)} total):\n")
        print(f"{'Model':<40} {'Count':<10} Distribution")
        print("-" * 80)

        total = sum(m['count'] for m in models)
        for model_info in models:
            percentage = (model_info['count'] / total) * 100
            bar = '█' * int(percentage / 2)
            print(f"{model_info['model']:<40} {model_info['count']:<10} {bar} {percentage:.1f}%")

    return 0


def cmd_sources(args):
    """List all sources of conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1

    with ConversationDB(args.db) as db:
        sources = db.get_sources()

        if not sources:
            print("No sources found in database")
            return 0

        print(f"🌐 Conversation Sources ({len(sources)} total):\n")
        print(f"{'Source':<30} {'Count':<10} Distribution")
        print("-" * 70)

        total = sum(s['count'] for s in sources)
        for source_info in sources:
            percentage = (source_info['count'] / total) * 100
            bar = '█' * int(percentage / 2)
            print(f"{source_info['source']:<30} {source_info['count']:<10} {bar} {percentage:.1f}%")

    return 0


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Conversation Toolkit - Manage conversation trees from multiple sources'
    )
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import conversations')
    import_parser.add_argument('input', help='Input file path (or "auto" for auto-search with copilot/claude_code/cursor)')
    import_parser.add_argument('--format', '-f',
                               help='Input format: openai, anthropic, copilot, gemini, jsonl, filesystem_coding (auto-detect if not specified)')
    import_parser.add_argument('--db', '-d', help='Database path to save to')
    import_parser.add_argument('--output', '-o', help='Output file path (for conversion)')
    import_parser.add_argument('--output-format', help='Output format for conversion: json, markdown, jsonl')
    import_parser.add_argument('--tags', '-t', help='Comma-separated tags to add')
    import_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    import_parser.add_argument('--path-selection', default='longest',
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy for tree conversations (default: longest)')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export conversations')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('--db', '-d', required=True, help='Database path')
    export_parser.add_argument('--format', '-f', default='jsonl',
                               help='Export format: json, markdown, jsonl, html, html5 (default: jsonl)')
    export_parser.add_argument('--ids', nargs='+', help='Specific conversation IDs to export')
    export_parser.add_argument('--limit', type=int, default=1000, help='Maximum conversations (default: 1000)')
    export_parser.add_argument('--filter-source', help='Filter by source (e.g., ChatGPT, Claude, GitHub Copilot)')
    export_parser.add_argument('--filter-model', help='Filter by model (e.g., gpt-4, claude-3)')
    export_parser.add_argument('--filter-tags', help='Filter by tags (comma-separated)')
    export_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    export_parser.add_argument('--path-selection', default='longest',
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy for tree conversations (default: longest)')
    export_parser.add_argument('--include-metadata', action='store_true',
                               help='Include metadata in export')
    # HTML-specific options
    export_parser.add_argument('--theme', default='auto', choices=['light', 'dark', 'auto'],
                               help='Theme for HTML export (default: auto)')
    export_parser.add_argument('--group-by', default='date', choices=['date', 'source', 'model', 'tag'],
                               help='Grouping strategy for HTML export (default: date)')
    export_parser.add_argument('--show-tree', action='store_true', default=True,
                               help='Show conversation tree structure in HTML export')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List conversations')
    list_parser.add_argument('--db', '-d', required=True, help='Database path')
    list_parser.add_argument('--limit', type=int, default=100, help='Maximum results')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # Search command with advanced options
    search_parser = subparsers.add_parser('search', help='Advanced search for conversations')
    search_parser.add_argument('query', nargs='?', help='Search query text')
    search_parser.add_argument('--db', '-d', required=True, help='Database path')
    search_parser.add_argument('--limit', type=int, default=100, help='Maximum results')
    search_parser.add_argument('--offset', type=int, default=0, help='Number of results to skip')
    search_parser.add_argument('--title-only', action='store_true', help='Search only in titles')
    search_parser.add_argument('--content-only', action='store_true', help='Search only in message content')
    search_parser.add_argument('--date-from', help='Filter by created after (YYYY-MM-DD)')
    search_parser.add_argument('--date-to', help='Filter by created before (YYYY-MM-DD)')
    search_parser.add_argument('--source', help='Filter by source platform')
    search_parser.add_argument('--model', help='Filter by model used')
    search_parser.add_argument('--tags', help='Filter by tags (comma-separated)')
    search_parser.add_argument('--min-messages', type=int, help='Minimum number of messages')
    search_parser.add_argument('--max-messages', type=int, help='Maximum number of messages')
    search_parser.add_argument('--has-branches', action='store_true', help='Only branching conversations')
    search_parser.add_argument('--order-by', choices=['created_at', 'updated_at', 'title', 'message_count'],
                              default='updated_at', help='Field to order by')
    search_parser.add_argument('--ascending', action='store_true', help='Sort in ascending order')
    search_parser.add_argument('--format', choices=['table', 'json', 'csv'], default='table',
                              help='Output format')

    # Stats command with enhancements
    stats_parser = subparsers.add_parser('stats', help='Show enhanced database statistics')
    stats_parser.add_argument('--db', '-d', required=True, help='Database path')
    stats_parser.add_argument('--timeline', choices=['day', 'week', 'month', 'year'],
                             help='Show activity timeline')
    stats_parser.add_argument('--show-models', action='store_true',
                             help='Show model breakdown')
    
    # Plugins command
    plugins_parser = subparsers.add_parser('plugins', help='List available plugins')

    # Tags command
    tags_parser = subparsers.add_parser('tags', help='Manage and view tags')
    tags_parser.add_argument('--db', '-d', required=True, help='Database path')
    tags_parser.add_argument('--conversation-id', '-c', help='Conversation ID for tag operations')
    tags_parser.add_argument('--add', help='Add tags (comma-separated)')
    tags_parser.add_argument('--remove', help='Remove tags (comma-separated)')

    # Models command
    models_parser = subparsers.add_parser('models', help='List all models used')
    models_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Sources command
    sources_parser = subparsers.add_parser('sources', help='List all conversation sources')
    sources_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Database operations command
    from ctk.cli_db import add_db_commands
    add_db_commands(subparsers)

    args = parser.parse_args()
    
    if args.verbose:
        setup_logging(verbose=True)
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Dispatch to command handler
    commands = {
        'import': cmd_import,
        'export': cmd_export,
        'list': cmd_list,
        'search': cmd_search,
        'stats': cmd_stats,
        'plugins': cmd_plugins,
        'tags': cmd_tags,
        'models': cmd_models,
        'sources': cmd_sources,
    }

    # Special handling for db subcommands
    if args.command == 'db':
        from ctk.cli_db import (
            cmd_merge, cmd_diff, cmd_intersect, cmd_filter,
            cmd_split, cmd_dedupe, cmd_stats as cmd_db_stats,
            cmd_validate, cmd_query
        )

        db_commands = {
            'merge': cmd_merge,
            'diff': cmd_diff,
            'intersect': cmd_intersect,
            'filter': cmd_filter,
            'split': cmd_split,
            'dedupe': cmd_dedupe,
            'stats': cmd_db_stats,
            'validate': cmd_validate,
            'query': cmd_query,
        }

        if hasattr(args, 'db_command') and args.db_command:
            return db_commands[args.db_command](args)
        else:
            print("Error: No database operation specified")
            return 1

    return commands[args.command](args)


def _get_command_handlers():
    """Get mapping of command names to handler functions"""
    return {
        'import': cmd_import,
        'export': cmd_export,
        'list': cmd_list,
        'search': cmd_search,
        'stats': cmd_stats,
        'plugins': cmd_plugins,
    }


if __name__ == '__main__':
    sys.exit(main())