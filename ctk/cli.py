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
from datetime import datetime

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

        # Handle directory imports (e.g., OpenAI export directories)
        if input_path.is_dir():
            # Look for standard data files in the directory
            possible_files = ['conversations.json', 'data.json', 'export.json']
            data_file = None
            for filename in possible_files:
                candidate = input_path / filename
                if candidate.exists():
                    data_file = candidate
                    break

            if not data_file:
                print(f"Error: Directory '{input_path}' does not contain a recognizable data file")
                print(f"  Looked for: {', '.join(possible_files)}")
                return 1

            # Read from the found file
            with open(data_file, 'r') as f:
                data = f.read()
        else:
            # Read input file
            with open(input_path, 'r') as f:
                data = f.read()

        # Import conversations - get importer first (explicit or auto-detect)
        if args.format:
            importer = registry.get_importer(args.format)
            if not importer:
                print(f"Error: Unknown format: {args.format}")
                print(f"Available formats: {', '.join(registry.list_importers())}")
                return 1

            # Only try to parse as JSON if it's NOT a JSONL format
            if args.format not in ['jsonl', 'local', 'llama', 'mistral', 'alpaca']:
                try:
                    data = json.loads(data)
                except:
                    pass  # Keep as string if not JSON
        else:
            # Auto-detect format
            try:
                data_parsed = json.loads(data)
            except json.JSONDecodeError:
                data_parsed = data

            importer = registry.auto_detect_importer(data_parsed)
            if not importer:
                print("Error: Could not auto-detect format")
                return 1
            data = data_parsed

        # Prepare import kwargs (for both explicit and auto-detected formats)
        import_kwargs = {}

        # Detect if this is an OpenAI format importer
        is_openai_format = (
            (args.format and args.format in ['openai', 'chatgpt', 'gpt']) or
            (importer.name in ['openai', 'chatgpt', 'gpt'])
        )

        # If importing OpenAI format, pass source_dir for image resolution
        if is_openai_format:
            if input_path.is_dir():
                import_kwargs['source_dir'] = str(input_path)
            else:
                # Input is a file, use parent directory as source_dir
                import_kwargs['source_dir'] = str(input_path.parent)

        # If saving to database, pass media_dir for image storage
        if args.db:
            try:
                db_temp = ConversationDB(args.db)
                if hasattr(db_temp, 'media_dir'):
                    import_kwargs['media_dir'] = str(db_temp.media_dir)
            except (ValueError, PermissionError, OSError) as e:
                print(f"Error: Cannot open database: {e}")
                return 1

        # Import with kwargs
        conversations = importer.import_data(data, **import_kwargs)

    try:
        print(f"Imported {len(conversations)} conversation(s)")

        # If no conversations were imported, treat as an error
        # (unless explicitly told to ignore this via a flag)
        if not conversations:
            print("Warning: No valid conversations found in the input file")
            if not args.db and not args.output:
                # No output destination, this is definitely an error
                return 1

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
        # CLI convention: --limit 0 means "no limit"
        export_limit = None if getattr(args, 'limit', None) in (None, 0) else args.limit

        # Check for view-based export first
        if hasattr(args, 'view') and args.view:
            from ctk.core.views import ViewStore
            store = ViewStore(args.db)
            evaluated = store.evaluate(args.view, db)
            if not evaluated:
                print(f"Error: View '{args.view}' not found")
                return 1
            conversations = evaluated.conversations
            if evaluated.missing_ids:
                print(f"Warning: {len(evaluated.missing_ids)} conversations not found")
        elif args.ids:
            # Export specific conversations
            for conv_id in args.ids:
                conv = db.load_conversation(conv_id)
                if conv:
                    conversations.append(conv)
                else:
                    print(f"Warning: Conversation {conv_id} not found")
        else:
            # Export all or filtered conversations
            conv_list = db.list_conversations(limit=export_limit)
            for conv_info in conv_list:
                conv = db.load_conversation(conv_info.id)
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
                    # Organization filters
                    if hasattr(args, 'starred') and args.starred:
                        if not conv.metadata.starred_at:
                            continue
                    if hasattr(args, 'pinned') and args.pinned:
                        if not conv.metadata.pinned_at:
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
        if hasattr(args, 'embed'):
            export_kwargs['embed'] = args.embed
        if hasattr(args, 'media_dir') and args.media_dir:
            export_kwargs['media_dir'] = args.media_dir

        # Add Hugo-specific options if present
        if hasattr(args, 'draft'):
            export_kwargs['include_draft'] = args.draft
        if hasattr(args, 'date_prefix'):
            export_kwargs['date_prefix'] = args.date_prefix

        # Pass database directory for media files
        if hasattr(db, 'db_dir') and db.db_dir:
            export_kwargs['db_dir'] = str(db.db_dir)

        try:
            exporter.export_to_file(conversations, args.output, **export_kwargs)
            print(f"Exported to {args.output}")
        except (PermissionError, OSError) as e:
            print(f"Error: Cannot write to output file: {e}")
            return 1

        return 0


def cmd_list(args):
    """List conversations in database"""
    if not args.db:
        print("Error: Database path required")
        return 1

    from .core.helpers import list_conversations_helper

    db = ConversationDB(args.db)

    return list_conversations_helper(
        db=db,
        limit=args.limit,
        json_output=args.json,
        archived=getattr(args, 'archived', False),
        starred=getattr(args, 'starred', False),
        pinned=getattr(args, 'pinned', False),
        include_archived=getattr(args, 'include_archived', False),
        source=getattr(args, 'source', None),
        project=getattr(args, 'project', None),
        model=getattr(args, 'model', None),
        tags=getattr(args, 'tags', None)
    )


def cmd_search(args):
    """Advanced search for conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1

    from .core.helpers import search_conversations_helper
    from datetime import datetime

    db = ConversationDB(args.db)

    # Parse date arguments
    date_from = None
    date_to = None
    if args.date_from:
        date_from = datetime.fromisoformat(args.date_from)
    if args.date_to:
        date_to = datetime.fromisoformat(args.date_to)

    return search_conversations_helper(
        db=db,
        query=args.query,
        limit=args.limit,
        offset=args.offset,
        title_only=args.title_only,
        content_only=args.content_only,
        date_from=date_from,
        date_to=date_to,
        source=args.source,
        project=args.project,
        model=args.model,
        tags=args.tags,
        min_messages=args.min_messages,
        max_messages=args.max_messages,
        has_branches=args.has_branches,
        archived=getattr(args, 'archived', False),
        starred=getattr(args, 'starred', False),
        pinned=getattr(args, 'pinned', False),
        include_archived=getattr(args, 'include_archived', False),
        order_by=args.order_by,
        ascending=args.ascending,
        output_format=args.format
    )


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


def cmd_view(args):
    """View management commands"""
    from ctk.core.views import ViewStore, View, ViewItem, ViewQuery

    if not args.db:
        print("Error: Database path required")
        return 1

    store = ViewStore(args.db)
    action = args.view_action

    if action == "list":
        views = store.list_views_detailed()
        if not views:
            print("No views found. Create one with: ctk view create <name> --db <db>")
            return 0

        print(f"{'Name':<20} {'Type':<10} {'Items':<8} {'Description'}")
        print("-" * 70)
        for v in views:
            desc = (v['description'] or '')[:30]
            print(f"{v['name']:<20} {v['selection_type']:<10} {v['item_count']:<8} {desc}")
        return 0

    elif action == "create":
        if not args.name:
            print("Error: View name required")
            return 1

        if store.exists(args.name):
            print(f"Error: View '{args.name}' already exists")
            return 1

        # Parse query options if provided
        query = None
        if any([args.tags, args.source, args.model, args.starred, args.pinned]):
            query = {
                "tags": args.tags.split(",") if args.tags else None,
                "source": args.source,
                "model": args.model,
                "starred": args.starred,
                "pinned": args.pinned,
            }

        view = store.create_view(
            name=args.name,
            description=args.description,
            items=args.ids if args.ids else None,
            query=query,
            author=args.author
        )

        if args.track_changes:
            view.track_changes = True

        store.save(view)
        print(f"Created view: {args.name}")
        return 0

    elif action == "show":
        if not args.name:
            print("Error: View name required")
            return 1

        view = store.load(args.name)
        if not view:
            print(f"Error: View '{args.name}' not found")
            return 1

        print(f"Name: {view.name}")
        print(f"Description: {view.description or '(none)'}")
        print(f"Type: {view.selection_type.value}")
        print(f"Created: {view.created}")
        print(f"Updated: {view.updated}")

        if view.items:
            print(f"\nItems ({len(view.get_items())} conversations):")
            for item in view.items:
                if hasattr(item, 'id'):
                    note = f" - {item.note}" if item.note else ""
                    title = f" ({item.title})" if item.title else ""
                    print(f"  {item.id[:8]}{title}{note}")
                elif hasattr(item, 'title'):
                    print(f"  [Section: {item.title}]")

        if view.query:
            print(f"\nQuery:")
            if view.query.tags:
                print(f"  Tags: {view.query.tags}")
            if view.query.source:
                print(f"  Source: {view.query.source}")
            if view.query.starred:
                print(f"  Starred: {view.query.starred}")

        return 0

    elif action == "add":
        if not args.name or not args.ids:
            print("Error: View name and conversation IDs required")
            return 1

        if not store.exists(args.name):
            print(f"Error: View '{args.name}' not found")
            return 1

        db = ConversationDB(args.db)
        with db:
            for conv_id in args.ids:
                if store.add_to_view(args.name, conv_id, title=args.title, note=args.note, db=db):
                    print(f"Added {conv_id[:8]} to {args.name}")
                else:
                    print(f"Failed to add {conv_id[:8]}")

        return 0

    elif action == "remove":
        if not args.name or not args.ids:
            print("Error: View name and conversation IDs required")
            return 1

        for conv_id in args.ids:
            if store.remove_from_view(args.name, conv_id):
                print(f"Removed {conv_id[:8]} from {args.name}")
            else:
                print(f"Not found: {conv_id[:8]}")

        return 0

    elif action == "delete":
        if not args.name:
            print("Error: View name required")
            return 1

        if store.delete(args.name):
            print(f"Deleted view: {args.name}")
        else:
            print(f"View not found: {args.name}")

        return 0

    elif action == "check":
        if not args.name:
            # Check all views
            views = store.list_views()
            if not views:
                print("No views to check")
                return 0

            db = ConversationDB(args.db)
            with db:
                for name in views:
                    result = store.check_view(name, db)
                    if result.get("error"):
                        print(f"{name}: {result['error']}")
                    elif result["issues"] > 0:
                        print(f"{name}: {result['issues']} issues (missing: {len(result['missing_ids'])}, drift: {result['drift_count']})")
                    else:
                        print(f"{name}: OK ({result['resolved_items']} items)")
        else:
            db = ConversationDB(args.db)
            with db:
                result = store.check_view(args.name, db)
                if result.get("error"):
                    print(f"Error: {result['error']}")
                    return 1

                print(f"View: {result['name']}")
                print(f"Items: {result['total_items']} defined, {result['resolved_items']} resolved")

                if result['missing_ids']:
                    print(f"\nMissing conversations ({len(result['missing_ids'])}):")
                    for mid in result['missing_ids']:
                        print(f"  {mid}")

                if result['drift_count'] > 0:
                    print(f"\nContent drift detected: {result['drift_count']} items")

                if result['issues'] == 0:
                    print("\nNo issues found.")

        return 0

    elif action == "eval":
        if not args.name:
            print("Error: View name required")
            return 1

        db = ConversationDB(args.db)
        with db:
            evaluated = store.evaluate(args.name, db)
            if not evaluated:
                print(f"Error: View '{args.name}' not found")
                return 1

            print(f"View: {args.name}")
            print(f"Conversations: {len(evaluated)}")
            print()

            for item in evaluated.items:
                section_str = f" [{item.section}]" if item.section else ""
                note_str = f" - {item.item.note}" if item.item.note else ""
                drift_str = " [DRIFT]" if item.drift_detected else ""
                print(f"{item.index + 1}. {item.effective_title}{section_str}{note_str}{drift_str}")

        return 0

    else:
        print(f"Unknown action: {action}")
        return 1


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


def cmd_auto_tag(args):
    """Auto-tag conversations using LLM"""
    from ctk.integrations.llm.ollama import OllamaProvider
    from ctk.integrations.llm.base import Message, MessageRole
    from ctk.core.config import get_config

    if not args.db:
        print("Error: Database path required")
        return 1

    # Load config
    cfg = get_config()
    provider_config = cfg.get_provider_config(args.provider)

    # Configure provider
    config = {
        'model': args.model,
        'base_url': provider_config.get('base_url', 'http://localhost:11434'),
        'timeout': provider_config.get('timeout', 120),
    }

    if args.base_url:
        config['base_url'] = args.base_url

    # Create provider
    provider = OllamaProvider(config)

    with ConversationDB(args.db) as db:
        # Use search if query provided, otherwise list
        if args.query:
            # Full-text search
            search_args = {
                'query_text': args.query,
                'limit': None,  # Get all matching, filter later
                'include_archived': False,
            }

            if args.project:
                search_args['project'] = args.project
            if args.starred:
                search_args['starred'] = True
            if args.source:
                search_args['source'] = args.source

            conversations = db.search_conversations(**search_args)
        else:
            # List with filters
            filter_args = {
                'limit': None,  # Get all matching, filter later
                'include_archived': False,
            }

            if args.project:
                filter_args['project'] = args.project
            if args.starred:
                filter_args['starred'] = True
            if args.source:
                filter_args['source'] = args.source

            conversations = db.list_conversations(**filter_args)

        # Additional filtering
        if args.title:
            conversations = [c for c in conversations if args.title.lower() in c.title.lower()]
        if args.no_tags:
            conversations = [c for c in conversations if not c.to_dict().get('tags')]

        # Apply limit after all filtering
        if args.limit is not None:
            conversations = conversations[:args.limit]

        if not conversations:
            print("No conversations found matching criteria")
            return 0

        print(f"Found {len(conversations)} conversation(s) to tag\n")

        tagged_count = 0
        for i, conv_summary in enumerate(conversations, 1):
            # Load full conversation
            tree = db.load_conversation(conv_summary.id)
            if not tree:
                continue

            print(f"[{i}/{len(conversations)}] {tree.title[:60]}")

            # Build context from first messages
            context = f"Title: {tree.title}\n\n"
            messages = list(tree.message_map.values())[:10]
            for msg in messages:
                role = msg.role.value.upper()
                content = msg.content.text[:200] if msg.content.text and len(msg.content.text) > 200 else (msg.content.text or "")
                context += f"{role}: {content}\n\n"

            # Ask LLM for tags
            tag_prompt = f"""Based on this conversation, suggest 3-5 relevant tags (single words or short phrases).
Return ONLY the tags as a comma-separated list, nothing else.

{context}

Tags:"""

            try:
                response = provider.chat(
                    [Message(role=MessageRole.USER, content=tag_prompt)],
                    temperature=0.3
                )

                # Parse tags
                response_text = response.content if hasattr(response, 'content') else str(response)
                tags = [t.strip() for t in response_text.strip().split(',')]
                tags = [t for t in tags if t]

                if not tags:
                    print("  No tags suggested\n")
                    continue

                print(f"  Suggested: {', '.join(tags)}")

                # Apply or prompt
                if args.dry_run:
                    print("  (dry run - not applied)\n")
                    continue
                elif args.yes:
                    apply = True
                else:
                    confirm = input("  Apply? (y/n): ").strip().lower()
                    apply = confirm == 'y'

                if apply:
                    db.add_tags(conv_summary.id, tags)
                    print("  ✓ Applied\n")
                    tagged_count += 1
                else:
                    print("  Skipped\n")

            except Exception as e:
                print(f"  Error: {e}\n")

        print(f"Tagged {tagged_count} conversation(s)")
        return 0


def cmd_say(args):
    """One-shot message to LLM with full tool support (same as TUI 'say' command)"""
    from ctk.integrations.llm.ollama import OllamaProvider
    from ctk.integrations.chat.tui import ChatTUI
    from ctk.core.config import get_config

    # Join query words
    message = ' '.join(args.message)

    # Load config
    cfg = get_config()
    provider_config = cfg.get_provider_config(args.provider)

    # Configure provider
    config = {
        'model': args.model,
        'base_url': provider_config.get('base_url', 'http://localhost:11434'),
        'timeout': provider_config.get('timeout', 120),
    }
    if args.base_url:
        config['base_url'] = args.base_url

    # Create provider
    try:
        provider = OllamaProvider(config)
    except Exception as e:
        print(f"Error: Failed to initialize provider: {e}")
        return 1

    # Test connection
    if not provider.is_available():
        base_url = config.get('base_url', 'http://localhost:11434')
        print(f"Error: Cannot connect to {args.provider} at {base_url}")
        return 1

    # Create database connection if specified
    db = None
    if args.db:
        try:
            db = ConversationDB(args.db)
        except Exception as e:
            print(f"Warning: Could not connect to database: {e}")

    # Create TUI instance (but don't run interactive loop)
    disable_tools = getattr(args, 'no_tools', False)
    tui = ChatTUI(provider, db=db, render_markdown=True, disable_tools=disable_tools)

    # One-shot: send message and get response
    try:
        tui.chat(message)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _resolve_conversation_id(db: ConversationDB, conv_id: str) -> str:
    """
    Resolve a conversation ID prefix to full ID.

    Args:
        db: Database instance
        conv_id: Full or partial conversation ID

    Returns:
        Full conversation ID or "Error: ..." message
    """
    if len(conv_id) >= 36:
        # Already full ID
        return conv_id

    # Try prefix matching
    all_convs = db.list_conversations(limit=None, include_archived=True)
    matches = [c for c in all_convs if c.id.startswith(conv_id)]

    if len(matches) == 0:
        return f"Error: No conversation found matching '{conv_id}'"
    elif len(matches) > 1:
        match_list = ", ".join(f"{m.id[:8]}..." for m in matches[:3])
        return f"Error: Multiple conversations match '{conv_id}': {match_list}"
    else:
        return matches[0].id


def execute_ask_tool(db: ConversationDB, tool_name: str, tool_args: dict, debug: bool = False, use_rich: bool = True, shell_executor=None) -> str:
    """
    Execute a tool and return result as string.

    Args:
        db: Database instance
        tool_name: Name of tool to execute
        tool_args: Tool arguments
        debug: Enable debug logging
        use_rich: Use Rich formatting for output
        shell_executor: Optional callback to execute shell commands (for TUI integration)

    Returns:
        String representation of result
    """
    import sys

    if debug:
        print(f"[DEBUG] Tool: {tool_name}", file=sys.stderr)
        print(f"[DEBUG] Args: {tool_args}", file=sys.stderr)

    try:
        if tool_name == 'search_conversations':
            # Parse tags if provided
            tags_list = tool_args.get('tags', '').split(',') if tool_args.get('tags') else None

            # Convert string booleans to actual booleans
            # IMPORTANT: Only return True if explicitly true, otherwise None (not False!)
            # When LLM passes "false" or False, it usually means "not filtering" not "filter to false"
            def to_bool_or_none(val):
                if val is None:
                    return None
                if isinstance(val, bool):
                    return True if val else None  # Only True matters, False = not filtering
                if isinstance(val, str):
                    lower_val = val.lower()
                    if lower_val in ('true', '1', 'yes'):
                        return True
                    # "false", "none", "null", "0", "no" all mean "not filtering"
                    return None
                return None

            # Convert boolean flags - only True matters for filtering
            starred = to_bool_or_none(tool_args.get('starred'))
            pinned = to_bool_or_none(tool_args.get('pinned'))
            archived = to_bool_or_none(tool_args.get('archived'))

            # Clean up "None" strings in other params
            def clean_none(val):
                if val is None or (isinstance(val, str) and val.lower() in ('none', 'null', '')):
                    return None
                return val

            # Clean all string params that might be "None" or "null"
            query_text = clean_none(tool_args.get('query'))
            source = clean_none(tool_args.get('source'))
            project = clean_none(tool_args.get('project'))
            model = clean_none(tool_args.get('model'))
            limit_val = clean_none(tool_args.get('limit'))

            if debug:
                print(f"[DEBUG] Parsed filters: starred={starred}, pinned={pinned}, archived={archived}", file=sys.stderr)
                print(f"[DEBUG] query={query_text}, source={source}, model={model}", file=sys.stderr)

            # If no query, use list_conversations for better performance
            if query_text:
                results = db.search_conversations(
                    query_text=query_text,
                    limit=limit_val,
                    source=source,
                    project=project,
                    model=model,
                    starred=starred,
                    archived=archived,
                    tags=tags_list,
                    include_archived=False
                )
            else:
                # No query - use list for better performance
                results = db.list_conversations(
                    limit=limit_val,
                    source=source,
                    project=project,
                    model=model,
                    starred=starred,
                    pinned=pinned,
                    archived=archived,
                    tags=tags_list,
                    include_archived=False
                )

            if debug:
                print(f"[DEBUG] Query returned {len(results)} results", file=sys.stderr)

            if not results:
                return "No conversations found."

            # Format results with Rich if enabled
            if use_rich:
                from ctk.core.helpers import format_conversations_table

                # Limit to 10 for display
                display_results = results[:10]
                format_conversations_table(display_results, show_message_count=False)

                if len(results) > 10:
                    from rich.console import Console
                    console = Console()
                    console.print(f"[dim]... and {len(results) - 10} more results (showing first 10)[/dim]")

                return ""  # Already printed
            else:
                # Plain text format for JSON mode
                result_str = f"RESULTS: {len(results)} conversation(s) found\n\n"
                for i, conv in enumerate(results[:10], 1):
                    conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
                    result_str += f"{i}. ID: {conv_dict['id'][:8]}...\n"
                    result_str += f"   Title: {conv_dict.get('title', 'Untitled')}\n"
                    result_str += f"   Updated: {conv_dict.get('updated_at', 'N/A')}\n"
                    if conv_dict.get('tags'):
                        result_str += f"   Tags: {', '.join(conv_dict['tags'])}\n"
                    result_str += "\n"

                if len(results) > 10:
                    result_str += f"... and {len(results) - 10} more results (showing first 10)\n"

                result_str += f"END OF RESULTS (Total: {len(results)})"
                return result_str

        elif tool_name == 'get_conversation':
            conv_id = tool_args['conversation_id']

            # Handle prefix matching
            if len(conv_id) < 36:
                all_convs = db.list_conversations(limit=None, include_archived=True)
                matches = [c for c in all_convs if c.id.startswith(conv_id)]

                if len(matches) == 0:
                    return f"No conversation found matching '{conv_id}'"
                elif len(matches) > 1:
                    return f"Multiple conversations match '{conv_id}' - please be more specific"
                else:
                    conv_id = matches[0].id

            # Load conversation
            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            result_str = f"Conversation: {tree.title or 'Untitled'}\n"
            result_str += f"ID: {tree.id}\n"
            if tree.metadata:
                if tree.metadata.source:
                    result_str += f"Source: {tree.metadata.source}\n"
                if tree.metadata.model:
                    result_str += f"Model: {tree.metadata.model}\n"
                if tree.metadata.project:
                    result_str += f"Project: {tree.metadata.project}\n"
                if tree.metadata.tags:
                    result_str += f"Tags: {', '.join(tree.metadata.tags)}\n"

            # Count messages
            all_messages = list(tree.traverse())
            result_str += f"Messages: {len(all_messages)}\n"

            # Show messages if requested
            if tool_args.get('show_messages', False):
                result_str += "\nMessages:\n"
                for i, msg in enumerate(all_messages[:5], 1):
                    result_str += f"\n{i}. {msg.role}: {msg.content[:100]}...\n"
                if len(all_messages) > 5:
                    result_str += f"\n... and {len(all_messages) - 5} more messages\n"

            return result_str

        elif tool_name == 'get_statistics':
            stats = db.get_statistics()

            result_str = "Database Statistics:\n\n"
            result_str += f"Total conversations: {stats.get('total_conversations', 0)}\n"
            result_str += f"Total messages: {stats.get('total_messages', 0)}\n"

            if stats.get('by_source'):
                result_str += "\nBy source:\n"
                for source, count in stats['by_source'].items():
                    result_str += f"  - {source}: {count}\n"

            if stats.get('by_model'):
                result_str += "\nTop models:\n"
                for model, count in list(stats['by_model'].items())[:5]:
                    result_str += f"  - {model}: {count}\n"

            return result_str

        elif tool_name == 'execute_shell_command':
            command = tool_args.get('command', '')
            if not command:
                return "Error: No command provided"

            if shell_executor is None:
                return "Error: Shell command execution not available in this context. Use the TUI shell mode."

            # Execute the command via the provided executor
            try:
                result = shell_executor(command)
                if hasattr(result, 'output'):
                    # CommandResult object
                    if result.success:
                        return result.output if result.output else "(command executed successfully)"
                    else:
                        return f"Error: {result.error}" if result.error else "Command failed"
                else:
                    return str(result)
            except Exception as e:
                return f"Error executing command: {e}"

        elif tool_name == 'star_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            # Resolve prefix
            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.star_conversation(conv_id)
            return f"Starred conversation {conv_id[:8]}..."

        elif tool_name == 'unstar_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unstar_conversation(conv_id)
            return f"Unstarred conversation {conv_id[:8]}..."

        elif tool_name == 'pin_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.pin_conversation(conv_id)
            return f"Pinned conversation {conv_id[:8]}..."

        elif tool_name == 'unpin_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unpin_conversation(conv_id)
            return f"Unpinned conversation {conv_id[:8]}..."

        elif tool_name == 'archive_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.archive_conversation(conv_id)
            return f"Archived conversation {conv_id[:8]}..."

        elif tool_name == 'unarchive_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unarchive_conversation(conv_id)
            return f"Unarchived conversation {conv_id[:8]}..."

        elif tool_name == 'rename_conversation':
            conv_id = tool_args.get('conversation_id', '')
            title = tool_args.get('title', '')
            if not conv_id:
                return "Error: conversation_id required"
            if not title:
                return "Error: title required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.update_conversation_title(conv_id, title)
            return f"Renamed conversation {conv_id[:8]}... to '{title}'"

        elif tool_name == 'show_conversation_content':
            from ctk.core.helpers import show_conversation_helper

            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            path_selection = tool_args.get('path_selection', 'longest')

            result = show_conversation_helper(
                db=db,
                conv_id=conv_id,
                path_selection=path_selection,
                plain_output=True,
                show_metadata=True
            )

            if result['success']:
                return result['output']
            else:
                return f"Error: {result['error']}"

        elif tool_name == 'show_conversation_tree':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            # Use shell command if executor available
            if shell_executor:
                result = shell_executor(f"tree {conv_id}")
                if hasattr(result, 'output'):
                    return result.output if result.success else f"Error: {result.error}"
                return str(result)

            # Fallback to direct implementation
            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            return f"Tree for {tree.title or 'Untitled'}:\n(Use TUI shell mode for full tree visualization)"

        elif tool_name == 'delete_conversation':
            conv_id = tool_args.get('conversation_id', '')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            # Get title before deletion for confirmation message
            tree = db.load_conversation(conv_id)
            title = tree.title if tree else 'Unknown'

            db.delete_conversation(conv_id)
            return f"Deleted conversation '{title}' ({conv_id[:8]}...)"

        elif tool_name == 'tag_conversation':
            conv_id = tool_args.get('conversation_id', '')
            tags = tool_args.get('tags', [])
            if not conv_id:
                return "Error: conversation_id required"
            if not tags:
                return "Error: tags required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            # Add tags
            existing_tags = tree.metadata.tags if tree.metadata and tree.metadata.tags else []
            new_tags = [t for t in tags if t not in existing_tags]
            tree.metadata.tags = existing_tags + new_tags
            db.save_conversation(tree)

            return f"Added tags to {conv_id[:8]}...: {', '.join(new_tags)}"

        elif tool_name == 'list_tags':
            # Get all tags with counts
            stats = db.get_statistics()
            tags_data = stats.get('by_tag', {})

            if not tags_data:
                return "No tags found in database."

            result_str = "Tags in database:\n\n"
            # Sort by count descending
            sorted_tags = sorted(tags_data.items(), key=lambda x: x[1], reverse=True)
            for tag, count in sorted_tags:
                result_str += f"  {tag}: {count} conversation(s)\n"

            result_str += f"\nTotal: {len(tags_data)} unique tags"
            return result_str

        elif tool_name == 'remove_tag':
            conv_id = tool_args.get('conversation_id', '')
            tag = tool_args.get('tag', '')
            if not conv_id:
                return "Error: conversation_id required"
            if not tag:
                return "Error: tag required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            if not tree.metadata or not tree.metadata.tags:
                return f"Conversation has no tags"

            if tag not in tree.metadata.tags:
                return f"Tag '{tag}' not found on conversation"

            tree.metadata.tags = [t for t in tree.metadata.tags if t != tag]
            db.save_conversation(tree)
            return f"Removed tag '{tag}' from {conv_id[:8]}..."

        elif tool_name == 'list_sources':
            stats = db.get_statistics()
            sources_data = stats.get('by_source', {})

            if not sources_data:
                return "No sources found in database."

            result_str = "Sources in database:\n\n"
            sorted_sources = sorted(sources_data.items(), key=lambda x: x[1], reverse=True)
            for source, count in sorted_sources:
                result_str += f"  {source}: {count} conversation(s)\n"

            result_str += f"\nTotal: {len(sources_data)} sources"
            return result_str

        elif tool_name == 'list_models':
            stats = db.get_statistics()
            models_data = stats.get('by_model', {})

            if not models_data:
                return "No models found in database."

            result_str = "Models in database:\n\n"
            sorted_models = sorted(models_data.items(), key=lambda x: x[1], reverse=True)
            for model, count in sorted_models[:20]:  # Limit to top 20
                result_str += f"  {model}: {count} conversation(s)\n"

            if len(models_data) > 20:
                result_str += f"\n  ... and {len(models_data) - 20} more models"

            result_str += f"\nTotal: {len(models_data)} unique models"
            return result_str

        elif tool_name == 'export_conversation':
            conv_id = tool_args.get('conversation_id', '')
            export_format = tool_args.get('format', 'markdown')
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            if export_format == 'markdown':
                from ctk.integrations.exporters.markdown import MarkdownExporter
                exporter = MarkdownExporter()
                output = exporter.export_to_string(tree)
                return f"Markdown export of '{tree.title}':\n\n{output}"

            elif export_format == 'json':
                import json
                # Convert to dict
                conv_dict = {
                    'id': tree.id,
                    'title': tree.title,
                    'messages': [
                        {
                            'role': msg.role.value if msg.role else 'user',
                            'content': msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                        }
                        for msg in tree.get_longest_path()
                    ]
                }
                return f"JSON export:\n{json.dumps(conv_dict, indent=2)}"

            elif export_format == 'jsonl':
                messages = tree.get_longest_path()
                lines = []
                for msg in messages:
                    import json
                    line = json.dumps({
                        'role': msg.role.value if msg.role else 'user',
                        'content': msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                    })
                    lines.append(line)
                return f"JSONL export ({len(lines)} messages):\n" + "\n".join(lines)

            else:
                return f"Unknown format: {export_format}. Use markdown, json, or jsonl."

        elif tool_name == 'duplicate_conversation':
            conv_id = tool_args.get('conversation_id', '')
            new_title = tool_args.get('new_title', None)
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            # Create a deep copy with new ID
            import uuid
            import copy

            new_tree = copy.deepcopy(tree)
            new_tree.id = str(uuid.uuid4())
            new_tree.title = new_title or f"Copy of {tree.title}"

            # Update message IDs
            old_to_new = {}
            for old_id, msg in list(new_tree.message_map.items()):
                new_id = str(uuid.uuid4())
                old_to_new[old_id] = new_id
                msg.id = new_id

            # Update message_map keys and parent references
            new_message_map = {}
            for old_id, msg in new_tree.message_map.items():
                new_id = old_to_new.get(old_id, old_id)
                if msg.parent_id and msg.parent_id in old_to_new:
                    msg.parent_id = old_to_new[msg.parent_id]
                new_message_map[new_id] = msg
            new_tree.message_map = new_message_map

            # Update root_message_ids
            new_tree.root_message_ids = [old_to_new.get(rid, rid) for rid in new_tree.root_message_ids]

            db.save_conversation(new_tree)
            return f"Created copy: '{new_tree.title}' ({new_tree.id[:8]}...)"

        elif tool_name == 'get_recent_conversations':
            limit = tool_args.get('limit', 10)
            if not isinstance(limit, int):
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    limit = 10

            conversations = db.list_conversations(limit=limit)

            if not conversations:
                return "No conversations found."

            result_str = f"Recent conversations (last {len(conversations)}):\n\n"
            for i, conv in enumerate(conversations, 1):
                conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
                flags = ""
                if conv_dict.get('starred_at'):
                    flags += "⭐"
                if conv_dict.get('pinned_at'):
                    flags += "📌"

                title = conv_dict.get('title', 'Untitled')[:50]
                updated = conv_dict.get('updated_at', 'Unknown')[:19]

                result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
                result_str += f"   Updated: {updated}\n"

            result_str += f"\nType `show <id>` to view any conversation."
            return result_str

        elif tool_name == 'list_conversations':
            # Get filter parameters
            starred = tool_args.get('starred')
            pinned = tool_args.get('pinned')
            archived = tool_args.get('archived')
            limit = tool_args.get('limit', 20)
            source = tool_args.get('source')
            model = tool_args.get('model')

            if not isinstance(limit, int):
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    limit = 20

            # Build kwargs for list_conversations
            kwargs = {'limit': limit}
            if starred is not None:
                kwargs['starred'] = starred
            if pinned is not None:
                kwargs['pinned'] = pinned
            if archived is not None:
                kwargs['archived'] = archived
            if source:
                kwargs['source'] = source
            if model:
                kwargs['model'] = model

            conversations = db.list_conversations(**kwargs)

            if not conversations:
                filters_desc = []
                if starred:
                    filters_desc.append("starred")
                if pinned:
                    filters_desc.append("pinned")
                if archived:
                    filters_desc.append("archived")
                if source:
                    filters_desc.append(f"source={source}")
                if model:
                    filters_desc.append(f"model={model}")
                filter_str = f" ({', '.join(filters_desc)})" if filters_desc else ""
                return f"No conversations found{filter_str}."

            result_str = f"Conversations ({len(conversations)} results):\n\n"
            for i, conv in enumerate(conversations, 1):
                conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
                flags = ""
                if conv_dict.get('starred_at'):
                    flags += "⭐"
                if conv_dict.get('pinned_at'):
                    flags += "📌"
                if conv_dict.get('archived_at'):
                    flags += "📦"

                title = conv_dict.get('title', 'Untitled')[:50]
                source_str = conv_dict.get('metadata', {}).get('source', '') or ''
                model_str = conv_dict.get('metadata', {}).get('model', '') or ''

                result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
                if source_str or model_str:
                    result_str += f"   {source_str} | {model_str}\n"

            return result_str

        elif tool_name == 'list_conversation_paths':
            conv_id_arg = tool_args.get('conversation_id', '')
            conv_id = _resolve_conversation_id(db, conv_id_arg)
            if not conv_id:
                return f"Conversation not found: {conv_id_arg}"

            conversation = db.load_conversation(conv_id)
            if not conversation:
                return f"Conversation not found: {conv_id}"

            paths = conversation.get_all_paths()

            if not paths:
                return f"No paths found in conversation {conv_id[:8]}..."

            result_str = f"Paths in conversation {conv_id[:8]}... ({len(paths)} total):\n\n"
            for i, path in enumerate(paths, 1):
                result_str += f"Path {i} ({len(path)} messages):\n"
                for msg in path:
                    role_label = msg.role.value.title() if msg.role else "User"
                    content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                    preview = content_text[:50].replace('\n', ' ').strip() if content_text else ""
                    if len(content_text) > 50:
                        preview += "..."
                    result_str += f"  {role_label}: {preview}\n"
                result_str += "\n"

            return result_str

        elif tool_name == 'list_plugins':
            from ctk.core.plugin import PluginManager

            manager = PluginManager()
            importers = manager.list_importers()
            exporters = manager.list_exporters()

            result_str = "Available Plugins:\n\n"

            result_str += "Importers:\n"
            if importers:
                for name in sorted(importers):
                    result_str += f"  - {name}\n"
            else:
                result_str += "  (none)\n"

            result_str += "\nExporters:\n"
            if exporters:
                for name in sorted(exporters):
                    result_str += f"  - {name}\n"
            else:
                result_str += "  (none)\n"

            return result_str

        elif tool_name == 'auto_tag_conversation':
            conv_id_arg = tool_args.get('conversation_id', '')
            conv_id = _resolve_conversation_id(db, conv_id_arg)
            if not conv_id:
                return f"Conversation not found: {conv_id_arg}"

            conversation = db.load_conversation(conv_id)
            if not conversation:
                return f"Conversation not found: {conv_id}"

            # Auto-tagging requires LLM - check if we have one in context
            # This is a simplified version - the full implementation would use the TUI's provider
            # For now, return a message suggesting manual tagging
            return f"Auto-tagging requires an LLM provider. Use `ctk auto-tag {conv_id[:8]}` from the command line, or manually add tags with `tag_conversation`."

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error executing {tool_name}: {e}"


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


def cmd_chat(args):
    """Start interactive chat with LLM"""
    # Import here to avoid loading if not needed
    from ctk.integrations.llm.ollama import OllamaProvider
    from ctk.integrations.chat.tui import ChatTUI
    from ctk.core.config import get_config

    # Load config
    cfg = get_config()
    provider_config = cfg.get_provider_config(args.provider)

    # Configure provider (CLI args override config)
    config = {
        'model': args.model,
        'base_url': provider_config.get('base_url', 'http://localhost:11434'),
        'timeout': provider_config.get('timeout', 120),
    }

    # Override with CLI args if provided
    if args.base_url:
        config['base_url'] = args.base_url

    print(f"Initializing {args.provider} provider...")
    print(f"  Model: {args.model}")
    if args.base_url:
        print(f"  URL: {args.base_url}")
    if args.db:
        print(f"  Database: {args.db}")
    print()

    # Create provider
    if args.provider == 'ollama':
        provider = OllamaProvider(config)
    else:
        print(f"Error: Unsupported provider: {args.provider}")
        return 1

    # Test connection
    if not provider.is_available():
        base_url = config.get('base_url', 'http://localhost:11434')
        print(f"Error: Cannot connect to {args.provider} at {base_url}")
        print(f"Make sure {args.provider} is running")
        return 1

    # Create database connection if specified
    db = None
    if args.db:
        try:
            db = ConversationDB(args.db)
            print(f"✓ Connected to database")
        except Exception as e:
            print(f"Warning: Could not connect to database: {e}")
            print("Continuing without database support...")

    # Create and run chat
    render_markdown = not args.no_markdown
    disable_tools = getattr(args, 'no_tools', False)
    chat = ChatTUI(provider, db=db, render_markdown=render_markdown, disable_tools=disable_tools)
    chat.run()

    return 0


def cmd_show(args):
    """Show a specific conversation"""
    from ctk.core.helpers import show_conversation_helper

    db = ConversationDB(args.db)

    try:
        # Determine which path to show based on args
        path_selection = getattr(args, 'path', 'longest')  # Default to longest

        # Use shared helper to load conversation
        result = show_conversation_helper(
            db=db,
            conv_id=args.id,
            path_selection=path_selection,
            plain_output=getattr(args, 'no_color', False),
            show_metadata=True
        )

        if not result['success']:
            print(f"Error: {result['error']}")
            return 1

        tree = result['conversation']
        nav = result['navigator']
        path = result['path']
        path_count = result['path_count']

        # Display conversation metadata
        print(f"\nConversation: {tree.title}")
        print(f"ID: {tree.id}")
        if tree.metadata:
            print(f"Source: {tree.metadata.source or 'unknown'}")
            print(f"Model: {tree.metadata.model or 'unknown'}")
            if tree.metadata.created_at:
                print(f"Created: {tree.metadata.created_at}")
            if tree.metadata.tags:
                print(f"Tags: {', '.join(tree.metadata.tags)}")
        print(f"Total messages: {len(tree.message_map)}")
        print(f"Paths: {path_count}")
        print()

        if not path:
            print(f"No messages in conversation")
            return 0

        # Display path using navigator's pretty-print method
        from rich.console import Console

        if getattr(args, 'no_color', False):
            # Plain output
            print(f"\nMessages (path: {path_selection}, {len(path)} messages):")
            print(nav.format_path(path, show_metadata=True))
        else:
            # Pretty output
            console = Console()
            console.print(f"\n[bold]Messages (path: {path_selection}, {len(path)} messages):[/bold]")
            render_markdown = not getattr(args, 'no_markdown', False)
            nav.print_path(path, console=console, show_metadata=True, render_markdown=render_markdown)

        # Show branch info
        if path_count > 1:
            print(f"\nNote: This conversation has {path_count} paths")
            print(f"Use --path longest|latest|N to view different paths")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_delete(args):
    """Delete a conversation from database"""
    db = ConversationDB(args.db)

    try:
        # Load to verify it exists
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Confirm deletion unless --yes flag
        if not args.yes:
            print(f"\nAbout to delete conversation:")
            print(f"  ID: {tree.id[:8]}...")
            print(f"  Title: {tree.title}")
            print(f"  Messages: {len(tree.message_map)}")

            confirm = input("\nType 'yes' to confirm deletion: ").strip().lower()
            if confirm != 'yes':
                print("Deletion cancelled")
                return 0

        # Delete
        db.delete_conversation(tree.id)
        print(f"✓ Deleted conversation: {tree.title}")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_tree_view(args):
    """Show tree structure of a conversation"""
    from ctk.core.tree import ConversationTreeNavigator

    db = ConversationDB(args.db)

    try:
        # Load conversation
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=None, include_archived=True)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Use navigator to build tree
        nav = ConversationTreeNavigator(tree)

        if not nav.root:
            print("Error: No root message found")
            return 1

        from rich.console import Console
        console = Console()

        console.print(f"\n[bold cyan]Conversation Tree:[/bold cyan] {tree.title}")
        console.print(f"[dim]ID:[/dim] {tree.id[:8]}...")
        console.print(f"[dim]Total messages:[/dim] {len(tree.message_map)}")
        console.print(f"[dim]Paths:[/dim] {nav.get_path_count()}")
        console.print()

        # Use navigator's pretty-print method
        nav.print_tree(console=console)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_paths(args):
    """List all paths in a conversation"""
    from ctk.core.tree import ConversationTreeNavigator

    db = ConversationDB(args.db)

    try:
        # Load conversation
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=None, include_archived=True)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Use navigator
        nav = ConversationTreeNavigator(tree)

        from rich.console import Console
        console = Console()

        console.print(f"\n[bold cyan]Conversation:[/bold cyan] {tree.title}")
        console.print(f"[dim]ID:[/dim] {tree.id[:8]}...")

        # Use navigator's pretty-print method
        nav.print_path_summary(console=console)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_title(args):
    """Rename a conversation"""
    db = ConversationDB(args.db)

    try:
        # Load conversation
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Update title
        old_title = tree.title
        tree.title = args.new_title

        # Save back
        db.save_conversation(tree)

        print(f"✓ Renamed conversation")
        print(f"  Old title: {old_title}")
        print(f"  New title: {args.new_title}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_archive(args):
    """Archive or unarchive a conversation"""
    db = ConversationDB(args.db)

    try:
        # Load to verify it exists
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Archive or unarchive
        action = "unarchive" if args.unarchive else "archive"
        success = db.archive_conversation(tree.id, archive=not args.unarchive)

        if success:
            print(f"✓ {action.capitalize()}d conversation: {tree.title}")
            return 0
        else:
            print(f"Error: Failed to {action} conversation")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_star(args):
    """Star or unstar a conversation"""
    db = ConversationDB(args.db)

    try:
        # Load to verify it exists
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Star or unstar
        action = "unstar" if args.unstar else "star"
        success = db.star_conversation(tree.id, star=not args.unstar)

        if success:
            print(f"✓ {action.capitalize()}red conversation: {tree.title}")
            return 0
        else:
            print(f"Error: Failed to {action} conversation")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_pin(args):
    """Pin or unpin a conversation"""
    db = ConversationDB(args.db)

    try:
        # Load to verify it exists
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Pin or unpin
        action = "unpin" if args.unpin else "pin"
        success = db.pin_conversation(tree.id, pin=not args.unpin)

        if success:
            print(f"✓ {action.capitalize()}ned conversation: {tree.title}")
            return 0
        else:
            print(f"Error: Failed to {action} conversation")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_duplicate(args):
    """Duplicate a conversation"""
    db = ConversationDB(args.db)

    try:
        # Load to verify it exists
        tree = db.load_conversation(args.id)

        if not tree:
            # Try partial ID match
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(args.id)]

            if len(matches) == 0:
                print(f"Error: No conversation found matching '{args.id}'")
                return 1
            elif len(matches) > 1:
                print(f"Error: Multiple conversations match '{args.id}':")
                for match in matches[:5]:
                    print(f"  - {match.id[:8]}... {match.title}")
                return 1
            else:
                tree = db.load_conversation(matches[0].id)

        if not tree:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Duplicate
        new_id = db.duplicate_conversation(tree.id, new_title=args.title)

        if new_id:
            new_tree = db.load_conversation(new_id)
            print(f"✓ Duplicated conversation")
            print(f"  Original: {tree.title}")
            print(f"  New ID: {new_id[:8]}...")
            print(f"  New title: {new_tree.title}")
            return 0
        else:
            print(f"Error: Failed to duplicate conversation")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


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
                               help='For branching conversations: which path to export (default: longest)')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export conversations')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('--db', '-d', required=True, help='Database path')
    export_parser.add_argument('--format', '-f', default='jsonl',
                               help='Export format: json, markdown, jsonl, html, hugo (default: jsonl)')
    export_parser.add_argument('--ids', nargs='+', help='Specific conversation IDs to export')
    export_parser.add_argument('--view', help='Export conversations from a named view')
    export_parser.add_argument('--limit', type=int, default=0, help='Maximum conversations (0 = all, default: all)')
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
    export_parser.add_argument('--no-embed', action='store_false', dest='embed', default=True,
                               help='Create separate index.html + conversations.jsonl (requires web server). Default: embed data in single HTML file')
    export_parser.add_argument('--media-dir',
                               help='Output media files to directory instead of embedding. Path relative to output file (default: embed in HTML)')
    # Organization filters
    export_parser.add_argument('--starred', action='store_true',
                               help='Export only starred conversations')
    export_parser.add_argument('--pinned', action='store_true',
                               help='Export only pinned conversations')
    # Hugo-specific options
    export_parser.add_argument('--draft', action='store_true',
                               help='Hugo: mark exported conversations as draft')
    export_parser.add_argument('--no-date-prefix', action='store_false', dest='date_prefix', default=True,
                               help='Hugo: do not include date prefix in directory names')

    # List command
    list_parser = subparsers.add_parser('list', help='List conversations')
    list_parser.add_argument('--db', '-d', required=True, help='Database path')
    list_parser.add_argument('--limit', type=int, default=None, help='Maximum results (default: all)')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.add_argument('--archived', action='store_true', help='Show only archived conversations')
    list_parser.add_argument('--starred', action='store_true', help='Show only starred conversations')
    list_parser.add_argument('--pinned', action='store_true', help='Show only pinned conversations')
    list_parser.add_argument('--include-archived', action='store_true', help='Include archived in results (default: exclude)')
    list_parser.add_argument('--source', help='Filter by source platform')
    list_parser.add_argument('--project', help='Filter by project name')
    list_parser.add_argument('--model', help='Filter by model used')
    list_parser.add_argument('--tags', help='Filter by tags (comma-separated)')
    
    # Search command with advanced options
    search_parser = subparsers.add_parser('search', help='Advanced search for conversations')
    search_parser.add_argument('query', nargs='?', help='Search query text')
    search_parser.add_argument('--db', '-d', required=True, help='Database path')
    search_parser.add_argument('--limit', type=int, default=None, help='Maximum results (default: all)')
    search_parser.add_argument('--offset', type=int, default=0, help='Number of results to skip')
    search_parser.add_argument('--title-only', action='store_true', help='Search only in titles')
    search_parser.add_argument('--content-only', action='store_true', help='Search only in message content')
    search_parser.add_argument('--date-from', help='Filter by created after (YYYY-MM-DD)')
    search_parser.add_argument('--date-to', help='Filter by created before (YYYY-MM-DD)')
    search_parser.add_argument('--source', help='Filter by source platform')
    search_parser.add_argument('--project', help='Filter by project name')
    search_parser.add_argument('--model', help='Filter by model used')
    search_parser.add_argument('--tags', help='Filter by tags (comma-separated)')
    search_parser.add_argument('--min-messages', type=int, help='Minimum number of messages')
    search_parser.add_argument('--max-messages', type=int, help='Maximum number of messages')
    search_parser.add_argument('--has-branches', action='store_true', help='Only branching conversations')
    search_parser.add_argument('--archived', action='store_true', help='Show only archived conversations')
    search_parser.add_argument('--starred', action='store_true', help='Show only starred conversations')
    search_parser.add_argument('--pinned', action='store_true', help='Show only pinned conversations')
    search_parser.add_argument('--include-archived', action='store_true', help='Include archived in results (default: exclude)')
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

    # View command (subcommands)
    view_parser = subparsers.add_parser('view', help='Manage curated views of conversations')
    view_parser.add_argument('--db', '-d', required=True, help='Database path')
    view_subparsers = view_parser.add_subparsers(dest='view_action', help='View action')

    # view list
    view_list = view_subparsers.add_parser('list', help='List all views')

    # view create
    view_create = view_subparsers.add_parser('create', help='Create a new view')
    view_create.add_argument('name', help='View name')
    view_create.add_argument('--description', '-D', help='View description')
    view_create.add_argument('--author', help='Author name')
    view_create.add_argument('--ids', nargs='+', help='Initial conversation IDs')
    view_create.add_argument('--tags', help='Filter by tags (comma-separated)')
    view_create.add_argument('--source', help='Filter by source')
    view_create.add_argument('--model', help='Filter by model')
    view_create.add_argument('--starred', action='store_true', help='Filter starred only')
    view_create.add_argument('--pinned', action='store_true', help='Filter pinned only')
    view_create.add_argument('--track-changes', action='store_true', help='Track content changes')

    # view show
    view_show = view_subparsers.add_parser('show', help='Show view details')
    view_show.add_argument('name', help='View name')

    # view add
    view_add = view_subparsers.add_parser('add', help='Add conversations to a view')
    view_add.add_argument('name', help='View name')
    view_add.add_argument('ids', nargs='+', help='Conversation IDs to add')
    view_add.add_argument('--title', help='Title override for added items')
    view_add.add_argument('--note', help='Note for added items')

    # view remove
    view_remove = view_subparsers.add_parser('remove', help='Remove conversations from a view')
    view_remove.add_argument('name', help='View name')
    view_remove.add_argument('ids', nargs='+', help='Conversation IDs to remove')

    # view delete
    view_delete = view_subparsers.add_parser('delete', help='Delete a view')
    view_delete.add_argument('name', help='View name')

    # view check
    view_check = view_subparsers.add_parser('check', help='Check view for issues')
    view_check.add_argument('name', nargs='?', help='View name (or check all)')

    # view eval
    view_eval = view_subparsers.add_parser('eval', help='Evaluate and list view contents')
    view_eval.add_argument('name', help='View name')

    # Plugins command
    plugins_parser = subparsers.add_parser('plugins', help='List available plugins')

    # Tags command
    tags_parser = subparsers.add_parser('tags', help='Manage and view tags')
    tags_parser.add_argument('--db', '-d', required=True, help='Database path')
    tags_parser.add_argument('--conversation-id', '-c', help='Conversation ID for tag operations')
    tags_parser.add_argument('--add', help='Add tags (comma-separated)')
    tags_parser.add_argument('--remove', help='Remove tags (comma-separated)')

    # Auto-tag command
    auto_tag_parser = subparsers.add_parser('auto-tag', help='Auto-tag conversations using LLM')
    auto_tag_parser.add_argument('--db', '-d', required=True, help='Database path')
    auto_tag_parser.add_argument('--provider', default='ollama', choices=['ollama'], help='LLM provider to use')
    auto_tag_parser.add_argument('--model', default='llama3.2', help='Model to use for tagging')
    auto_tag_parser.add_argument('--base-url', help='Provider base URL (default: from config)')
    auto_tag_parser.add_argument('--limit', type=int, default=None, help='Maximum conversations to tag (default: all matching)')
    auto_tag_parser.add_argument('--dry-run', action='store_true', help='Show suggestions without applying')
    auto_tag_parser.add_argument('--yes', '-y', action='store_true', help='Auto-approve all tags')
    # Filters
    auto_tag_parser.add_argument('--query', '-q', help='Full-text search in conversation content')
    auto_tag_parser.add_argument('--project', help='Filter by project')
    auto_tag_parser.add_argument('--starred', action='store_true', help='Only starred conversations')
    auto_tag_parser.add_argument('--source', help='Filter by source')
    auto_tag_parser.add_argument('--title', help='Filter by title (partial match)')
    auto_tag_parser.add_argument('--no-tags', action='store_true', help='Only conversations without tags')

    # Models command
    models_parser = subparsers.add_parser('models', help='List all models used')
    models_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Sources command
    sources_parser = subparsers.add_parser('sources', help='List all conversation sources')
    sources_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Interactive chat with LLM and MCP tools')
    chat_parser.add_argument('--model', '-m', default='llama3.2', help='Model to use (default: llama3.2)')
    chat_parser.add_argument('--provider', '-p', default='ollama', choices=['ollama'],
                            help='LLM provider (default: ollama)')
    chat_parser.add_argument('--base-url', help='Base URL for provider (e.g., http://localhost:11434)')
    chat_parser.add_argument('--db', '-d', help='Database path to save conversations')
    chat_parser.add_argument('--no-markdown', action='store_true', help='Disable markdown rendering')
    chat_parser.add_argument('--no-tools', action='store_true', help='Disable tool calling (for models that don\'t support it)')

    # Say command - one-shot LLM message with full tool support
    say_parser = subparsers.add_parser('say', help='One-shot message to LLM (same as TUI say)')
    say_parser.add_argument('message', nargs='+', help='Message to send')
    say_parser.add_argument('--db', '-d', help='Database path (enables CTK tools)')
    say_parser.add_argument('--model', '-m', default='llama3.2', help='Model to use (default: llama3.2)')
    say_parser.add_argument('--provider', '-p', default='ollama', choices=['ollama'],
                            help='LLM provider (default: ollama)')
    say_parser.add_argument('--base-url', help='Base URL for provider')
    say_parser.add_argument('--no-tools', action='store_true', help='Disable tool calling')

    # Show command
    show_parser = subparsers.add_parser('show', help='Show a specific conversation')
    show_parser.add_argument('id', help='Conversation ID (full or partial)')
    show_parser.add_argument('--db', '-d', required=True, help='Database path')
    show_parser.add_argument('--path', default='longest',
                            help='Path to display: longest, latest, or path number (0-N)')
    show_parser.add_argument('--no-color', action='store_true', help='Disable colored output')
    show_parser.add_argument('--no-markdown', action='store_true', help='Disable markdown rendering')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a conversation')
    delete_parser.add_argument('id', help='Conversation ID (full or partial)')
    delete_parser.add_argument('--db', '-d', required=True, help='Database path')
    delete_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')

    # Tree command
    tree_parser = subparsers.add_parser('tree', help='Show conversation tree structure')
    tree_parser.add_argument('id', help='Conversation ID (full or partial)')
    tree_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Paths command
    paths_parser = subparsers.add_parser('paths', help='List all paths in a conversation')
    paths_parser.add_argument('id', help='Conversation ID (full or partial)')
    paths_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Title command
    title_parser = subparsers.add_parser('title', help='Rename a conversation')
    title_parser.add_argument('id', help='Conversation ID (full or partial)')
    title_parser.add_argument('new_title', help='New title for conversation')
    title_parser.add_argument('--db', '-d', required=True, help='Database path')

    # Archive command
    archive_parser = subparsers.add_parser('archive', help='Archive/unarchive conversations')
    archive_parser.add_argument('id', help='Conversation ID (full or partial)')
    archive_parser.add_argument('--db', '-d', required=True, help='Database path')
    archive_parser.add_argument('--unarchive', action='store_true', help='Unarchive instead of archive')

    # Star command
    star_parser = subparsers.add_parser('star', help='Star/unstar conversations')
    star_parser.add_argument('id', help='Conversation ID (full or partial)')
    star_parser.add_argument('--db', '-d', required=True, help='Database path')
    star_parser.add_argument('--unstar', action='store_true', help='Unstar instead of star')

    # Pin command
    pin_parser = subparsers.add_parser('pin', help='Pin/unpin conversations')
    pin_parser.add_argument('id', help='Conversation ID (full or partial)')
    pin_parser.add_argument('--db', '-d', required=True, help='Database path')
    pin_parser.add_argument('--unpin', action='store_true', help='Unpin instead of pin')

    # Duplicate command
    duplicate_parser = subparsers.add_parser('duplicate', help='Duplicate a conversation')
    duplicate_parser.add_argument('id', help='Conversation ID (full or partial)')
    duplicate_parser.add_argument('--db', '-d', required=True, help='Database path')
    duplicate_parser.add_argument('--title', help='Title for duplicated conversation')

    # Database operations command
    from ctk.cli_db import add_db_commands
    add_db_commands(subparsers)

    # Network/similarity operations command
    from ctk.cli_net import add_net_commands
    add_net_commands(subparsers)

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
        'view': cmd_view,
        'plugins': cmd_plugins,
        'tags': cmd_tags,
        'auto-tag': cmd_auto_tag,
        'say': cmd_say,
        'models': cmd_models,
        'sources': cmd_sources,
        'chat': cmd_chat,
        'show': cmd_show,
        'delete': cmd_delete,
        'tree': cmd_tree_view,
        'paths': cmd_paths,
        'title': cmd_title,
        'archive': cmd_archive,
        'star': cmd_star,
        'pin': cmd_pin,
        'duplicate': cmd_duplicate,
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

    # Special handling for net subcommands
    if args.command == 'net':
        from ctk.cli_net import (
            cmd_embeddings, cmd_similar, cmd_links, cmd_network,
            cmd_clusters, cmd_neighbors, cmd_path, cmd_central, cmd_outliers
        )

        net_commands = {
            'embeddings': cmd_embeddings,
            'similar': cmd_similar,
            'links': cmd_links,
            'network': cmd_network,
            'clusters': cmd_clusters,
            'neighbors': cmd_neighbors,
            'path': cmd_path,
            'central': cmd_central,
            'outliers': cmd_outliers,
        }

        if hasattr(args, 'net_command') and args.net_command:
            return net_commands[args.net_command](args)
        else:
            print("Error: No network operation specified")
            print("Available: embeddings, similar, links, network, clusters, neighbors, path, central, outliers")
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
        'view': cmd_view,
        'plugins': cmd_plugins,
    }


if __name__ == '__main__':
    sys.exit(main())
