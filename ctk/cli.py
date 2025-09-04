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
    """Import conversations from file"""
    registry.discover_plugins()
    
    # Read input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1
    
    # Import conversations
    try:
        if args.format:
            importer = registry.get_importer(args.format)
            if not importer:
                print(f"Error: Unknown format: {args.format}")
                print(f"Available formats: {', '.join(registry.list_importers())}")
                return 1
            
            with open(input_path, 'r') as f:
                data = f.read()
                try:
                    data = json.loads(data)
                except:
                    pass  # Keep as string if not JSON
            
            conversations = importer.import_data(data)
        else:
            # Auto-detect format
            conversations = registry.import_file(str(input_path))
        
        print(f"Imported {len(conversations)} conversation(s)")
        
        # Save to database if requested
        if args.db:
            with ConversationDB(args.db) as db:
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
    
    with ConversationDB(args.db) as db:
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
    """Search conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1
    
    with ConversationDB(args.db) as db:
        results = db.search_conversations(args.query, limit=args.limit)
        
        if not results:
            print(f"No conversations found matching '{args.query}'")
            return 0
        
        print(f"Found {len(results)} conversation(s):")
        for conv in results:
            print(f"  {conv['id']}: {conv['title'] or 'Untitled'}")
        
        return 0


def cmd_stats(args):
    """Show database statistics"""
    if not args.db:
        print("Error: Database path required")
        return 1
    
    with ConversationDB(args.db) as db:
        stats = db.get_statistics()
        
        print("Database Statistics:")
        print(f"  Total conversations: {stats['total_conversations']}")
        print(f"  Total messages: {stats['total_messages']}")
        
        if stats['messages_by_role']:
            print("\nMessages by role:")
            for role, count in stats['messages_by_role'].items():
                print(f"    {role}: {count}")
        
        if stats['conversations_by_source']:
            print("\nConversations by source:")
            for source, count in stats['conversations_by_source'].items():
                print(f"    {source}: {count}")
        
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


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Conversation Toolkit - Manage conversation trees from multiple sources'
    )
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import conversations')
    import_parser.add_argument('input', help='Input file path')
    import_parser.add_argument('--format', '-f', help='Input format (auto-detect if not specified)')
    import_parser.add_argument('--db', '-d', help='Database path to save to')
    import_parser.add_argument('--output', '-o', help='Output file path (for conversion)')
    import_parser.add_argument('--output-format', help='Output format for conversion')
    import_parser.add_argument('--tags', '-t', help='Comma-separated tags to add')
    import_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    import_parser.add_argument('--path-selection', default='longest', 
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy for tree conversations')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export conversations')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('--db', '-d', required=True, help='Database path')
    export_parser.add_argument('--format', '-f', default='jsonl', help='Export format')
    export_parser.add_argument('--ids', nargs='+', help='Specific conversation IDs to export')
    export_parser.add_argument('--limit', type=int, default=1000, help='Maximum conversations')
    export_parser.add_argument('--filter-source', help='Filter by source')
    export_parser.add_argument('--filter-model', help='Filter by model')
    export_parser.add_argument('--filter-tags', help='Filter by tags (comma-separated)')
    export_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    export_parser.add_argument('--path-selection', default='longest',
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy')
    export_parser.add_argument('--include-metadata', action='store_true', 
                               help='Include metadata in export')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List conversations')
    list_parser.add_argument('--db', '-d', required=True, help='Database path')
    list_parser.add_argument('--limit', type=int, default=100, help='Maximum results')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search conversations')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--db', '-d', required=True, help='Database path')
    search_parser.add_argument('--limit', type=int, default=100, help='Maximum results')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')
    stats_parser.add_argument('--db', '-d', required=True, help='Database path')
    
    # Plugins command
    plugins_parser = subparsers.add_parser('plugins', help='List available plugins')
    
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
    }
    
    return commands[args.command](args)


def _setup_import_parser(subparsers):
    """Setup the import command parser"""
    import_parser = subparsers.add_parser('import', help='Import conversations')
    import_parser.add_argument('input', help='Input file path')
    import_parser.add_argument('--format', '-f', help='Input format (auto-detect if not specified)')
    import_parser.add_argument('--db', '-d', help='Database path to save to')
    import_parser.add_argument('--output', '-o', help='Output file path (for conversion)')
    import_parser.add_argument('--output-format', help='Output format for conversion')
    import_parser.add_argument('--tags', '-t', help='Comma-separated tags to add')
    import_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    import_parser.add_argument('--path-selection', default='longest', 
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy for tree conversations')
    return import_parser


def _setup_export_parser(subparsers):
    """Setup the export command parser"""
    export_parser = subparsers.add_parser('export', help='Export conversations')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('--db', '-d', required=True, help='Database path')
    export_parser.add_argument('--format', '-f', default='jsonl', help='Export format')
    export_parser.add_argument('--ids', nargs='+', help='Specific conversation IDs to export')
    export_parser.add_argument('--limit', type=int, default=1000, help='Maximum conversations')
    export_parser.add_argument('--filter-source', help='Filter by source')
    export_parser.add_argument('--filter-model', help='Filter by model')
    export_parser.add_argument('--filter-tag', help='Filter by tag')
    export_parser.add_argument('--sanitize', action='store_true', help='Sanitize sensitive data')
    export_parser.add_argument('--path-selection', default='longest',
                               choices=['longest', 'first', 'last'],
                               help='Path selection strategy')
    export_parser.add_argument('--include-metadata', action='store_true', 
                               help='Include metadata in export')
    return export_parser


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