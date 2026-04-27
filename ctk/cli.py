#!/usr/bin/env python3
"""
Conversation Toolkit CLI with automatic plugin discovery
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ctk.core.database import ConversationDB
from ctk.core.input_validation import (ValidationError,
                                       validate_conversation_id,
                                       validate_file_path,
                                       validate_path_selection)
from ctk.core.plugin import registry
from ctk.core.sanitizer import Sanitizer


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def cmd_import(args):
    """Import conversations from file or auto-search"""
    registry.discover_plugins()

    # Handle auto-search for specific formats
    auto_search_formats = ["copilot", "claude_code", "cursor"]

    # Check if we should auto-search
    if args.input == "auto" and args.format in auto_search_formats:
        # Auto-search for the specified format
        print(f"Auto-searching for {args.format} data...")

        if args.format == "copilot":
            from ctk.importers.copilot import CopilotImporter

            found_paths = CopilotImporter.find_copilot_data()

            if not found_paths:
                print(f"No Copilot data found in VS Code storage")
                print(f"Searched in:")
                import platform

                system = platform.system().lower()
                if system == "windows":
                    system = "win32"
                for path in CopilotImporter.STORAGE_PATHS.get(
                    system, CopilotImporter.STORAGE_PATHS["linux"]
                ):
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
        # Normal file import - validate input path (allow both files and directories)
        try:
            input_path = validate_file_path(
                args.input,
                must_exist=True,
                allow_relative=True,
                allow_dir=True,
                allow_file=True,
            )
        except ValidationError as e:
            print(f"Error: Invalid input path: {e}")
            return 1

        # Handle directory imports (e.g., OpenAI export directories)
        if input_path.is_dir():
            # Look for standard data files in the directory
            possible_files = ["conversations.json", "data.json", "export.json"]
            data_file = None
            for filename in possible_files:
                candidate = input_path / filename
                if candidate.exists():
                    data_file = candidate
                    break

            if not data_file:
                print(
                    f"Error: Directory '{input_path}' does not contain a recognizable data file"
                )
                print(f"  Looked for: {', '.join(possible_files)}")
                return 1

            # Read from the found file
            with open(data_file, "r") as f:
                data = f.read()
        else:
            # Read input file
            with open(input_path, "r") as f:
                data = f.read()

        # Import conversations - get importer first (explicit or auto-detect)
        if args.format:
            importer = registry.get_importer(args.format)
            if not importer:
                print(f"Error: Unknown format: {args.format}")
                print(f"Available formats: {', '.join(registry.list_importers())}")
                return 1

            # Only try to parse as JSON if it's NOT a JSONL format
            if args.format not in ["jsonl", "local", "llama", "mistral", "alpaca"]:
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, ValueError, TypeError):
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
            args.format and args.format in ["openai", "chatgpt", "gpt"]
        ) or (importer.name in ["openai", "chatgpt", "gpt"])

        # If importing OpenAI format, pass source_dir for image resolution
        if is_openai_format:
            if input_path.is_dir():
                import_kwargs["source_dir"] = str(input_path)
            else:
                # Input is a file, use parent directory as source_dir
                import_kwargs["source_dir"] = str(input_path.parent)

        # If saving to database, pass media_dir for image storage
        if args.db:
            try:
                db_temp = ConversationDB(args.db)
                if hasattr(db_temp, "media_dir"):
                    import_kwargs["media_dir"] = str(db_temp.media_dir)
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
                        conv.metadata.tags.extend(args.tags.split(","))

                    conv_id = db.save_conversation(conv)
                    print(f"  Saved: {conv.title or 'Untitled'} ({conv_id})")

        # Export to file if requested
        if args.output:
            output_format = args.output_format or "jsonl"
            exporter = registry.get_exporter(output_format)
            if not exporter:
                print(f"Error: Unknown export format: {output_format}")
                return 1

            export_kwargs = {
                "sanitize": args.sanitize,
                "path_selection": args.path_selection,
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
        export_limit = None if getattr(args, "limit", None) in (None, 0) else args.limit

        # The legacy ``--view`` flag (curated YAML collections) was
        # dropped in 2.12.0 alongside the rest of the views machinery.
        # Tags + the sidebar filter tabs cover the same use case.
        if args.ids:
            # Export specific conversations - validate IDs
            for conv_id in args.ids:
                try:
                    validated_id = validate_conversation_id(conv_id, allow_partial=True)
                except ValidationError as e:
                    print(f"Error: Invalid conversation ID '{conv_id}': {e}")
                    return 1

                conv = db.load_conversation(validated_id)
                if conv:
                    conversations.append(conv)
                else:
                    print(f"Warning: Conversation {validated_id} not found")
        else:
            # Export all or filtered conversations
            conv_list = db.list_conversations(limit=export_limit)
            for conv_info in conv_list:
                conv = db.load_conversation(conv_info.id)
                if conv:
                    # Apply filters
                    if (
                        args.filter_source
                        and conv.metadata.source != args.filter_source
                    ):
                        continue
                    if args.filter_model and args.filter_model not in (
                        conv.metadata.model or ""
                    ):
                        continue
                    if args.filter_tags:
                        required_tags = set(args.filter_tags.split(","))
                        if not required_tags.issubset(set(conv.metadata.tags)):
                            continue
                    # Organization filters
                    if hasattr(args, "starred") and args.starred:
                        if not conv.metadata.starred_at:
                            continue
                    if hasattr(args, "pinned") and args.pinned:
                        if not conv.metadata.pinned_at:
                            continue

                    conversations.append(conv)

        if not conversations:
            print("No conversations found matching criteria")
            return 1

        print(f"Exporting {len(conversations)} conversation(s)")

        # Export
        format_name = args.format or "jsonl"
        exporter = registry.get_exporter(format_name)
        if not exporter:
            print(f"Error: Unknown export format: {format_name}")
            print(f"Available formats: {', '.join(registry.list_exporters())}")
            return 1

        # Validate path_selection and export format
        try:
            path_selection = validate_path_selection(args.path_selection)
        except ValidationError as e:
            print(f"Error: Invalid path selection: {e}")
            return 1

        export_kwargs = {
            "sanitize": args.sanitize,
            "path_selection": path_selection,
            "include_metadata": args.include_metadata,
        }

        # Add HTML-specific options if present
        if hasattr(args, "theme"):
            export_kwargs["theme"] = args.theme
        if hasattr(args, "group_by"):
            export_kwargs["group_by"] = args.group_by
        if hasattr(args, "show_tree"):
            export_kwargs["show_tree"] = args.show_tree
        if hasattr(args, "embed"):
            export_kwargs["embed"] = args.embed
        if hasattr(args, "media_dir") and args.media_dir:
            export_kwargs["media_dir"] = args.media_dir

        # Add Hugo-specific options if present
        if hasattr(args, "draft"):
            export_kwargs["include_draft"] = args.draft
        if hasattr(args, "date_prefix"):
            export_kwargs["date_prefix"] = args.date_prefix
        if hasattr(args, "hugo_organize"):
            export_kwargs["hugo_organize"] = args.hugo_organize

        # Add ECHO-specific options if present
        if hasattr(args, "include_db"):
            export_kwargs["include_db"] = args.include_db
        if hasattr(args, "owner_name"):
            export_kwargs["owner_name"] = args.owner_name
        if hasattr(args, "include_site"):
            export_kwargs["include_site"] = args.include_site
        # Pass db_path for database copy
        if hasattr(args, "db") and args.db:
            export_kwargs["db_path"] = args.db

        # Pass database directory for media files
        if hasattr(db, "db_dir") and db.db_dir:
            export_kwargs["db_dir"] = str(db.db_dir)

        # Validate output path (for Hugo exports, this is a directory; for file formats, it's a file)
        try:
            output_path = validate_file_path(
                args.output,
                must_exist=False,
                allow_relative=True,
                allow_dir=True,
                allow_file=True,
            )
        except ValidationError as e:
            print(f"Error: Invalid output path: {e}")
            return 1

        try:
            exporter.export_to_file(conversations, str(output_path), **export_kwargs)
            print(f"Exported to {output_path}")
        except (PermissionError, OSError) as e:
            print(f"Error: Cannot write to output file: {e}")
            return 1

        return 0


def cmd_list(args):
    """List conversations in database"""
    if not args.db:
        print("Error: Database path required")
        return 1

    from .core.db_helpers import list_conversations_helper

    db = ConversationDB(args.db)

    return list_conversations_helper(
        db=db,
        limit=args.limit,
        json_output=args.json,
        archived=getattr(args, "archived", False),
        starred=getattr(args, "starred", False),
        pinned=getattr(args, "pinned", False),
        include_archived=getattr(args, "include_archived", False),
        source=getattr(args, "source", None),
        project=getattr(args, "project", None),
        model=getattr(args, "model", None),
        tags=getattr(args, "tags", None),
    )


def cmd_query(args):
    """Human-friendly query command with composable flags.

    Replaces ctk db query for searching. Use ctk sql for raw SQL.
    """
    import re
    from datetime import datetime, timedelta

    from rich.console import Console
    from rich.table import Table

    console = Console()

    if not args.db:
        print("Error: Database path required (-d)")
        return 1

    db = ConversationDB(args.db)

    # Note: the legacy ``--view`` flag (curated YAML collections) was
    # removed in 2.12.0 alongside the rest of the views machinery.
    # Tags + filter flags below cover the same use case more flexibly.

    # Parse date filters
    def parse_date(date_str):
        if not date_str:
            return None
        # Handle relative dates like "7d", "1w", "1m"
        match = re.match(r"^(\d+)([dwmy])$", date_str.lower())
        if match:
            num, unit = int(match.group(1)), match.group(2)
            if unit == "d":
                return datetime.now() - timedelta(days=num)
            elif unit == "w":
                return datetime.now() - timedelta(weeks=num)
            elif unit == "m":
                return datetime.now() - timedelta(days=num * 30)
            elif unit == "y":
                return datetime.now() - timedelta(days=num * 365)
        # Try ISO format
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            print(f"Warning: Could not parse date '{date_str}'")
            return None

    date_from = parse_date(args.since)
    date_to = parse_date(args.until)

    # Collect tags from multiple --tag flags
    tags = ",".join(args.tag) if args.tag else None

    # Use the search helper
    from .core.db_helpers import search_conversations_helper

    # Cursor pagination: --cursor flag (empty string = first page)
    cursor = getattr(args, "cursor", None)
    page_size = getattr(args, "page_size", 50)

    return search_conversations_helper(
        db=db,
        query=args.text,
        limit=args.limit or 50,
        offset=0,
        title_only=False,
        content_only=False,
        date_from=date_from,
        date_to=date_to,
        source=args.source,
        project=args.project,
        model=args.model,
        tags=tags,
        min_messages=None,
        max_messages=None,
        has_branches=False,
        archived=args.archived,
        starred=args.starred,
        pinned=args.pinned,
        include_archived=(
            args.include_archived if hasattr(args, "include_archived") else False
        ),
        order_by=args.order_by or "updated_at",
        ascending=args.asc if hasattr(args, "asc") else False,
        output_format=args.format,
        cursor=cursor,
        page_size=page_size,
    )


def cmd_search(args):
    """Advanced search for conversations"""
    if not args.db:
        print("Error: Database path required")
        return 1

    from datetime import datetime

    from .core.db_helpers import search_conversations_helper

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
        archived=getattr(args, "archived", False),
        starred=getattr(args, "starred", False),
        pinned=getattr(args, "pinned", False),
        include_archived=getattr(args, "include_archived", False),
        order_by=args.order_by,
        ascending=args.ascending,
        output_format=args.format,
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

        if stats["messages_by_role"]:
            print("\n📝 Messages by Role:")
            for role, count in sorted(
                stats["messages_by_role"].items(), key=lambda x: x[1], reverse=True
            ):
                bar = "█" * min(
                    40, count // (max(stats["messages_by_role"].values()) // 40 + 1)
                )
                print(f"  {role:12} {count:7,} {bar}")

        if stats["conversations_by_source"]:
            print("\n🌐 Conversations by Source:")
            for source, count in sorted(
                stats["conversations_by_source"].items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                print(f"  {source:20} {count:7,}")

        if stats.get("top_tags"):
            print("\n🏆 Top Tags:")
            for tag in stats["top_tags"][:10]:
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
                print(
                    f"  {model_info['model']:30} {model_info['count']:5,} conversations"
                )

        return 0


def cmd_auto_tag(args):
    """Auto-tag conversations using LLM"""
    from ctk.llm.base import Message, MessageRole
    from ctk.llm.factory import build_provider

    if not args.db:
        print("Error: Database path required")
        return 1

    provider = build_provider(
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
    )

    with ConversationDB(args.db) as db:
        # Use search if query provided, otherwise list
        if args.query:
            # Full-text search
            search_args = {
                "query_text": args.query,
                "limit": None,  # Get all matching, filter later
                "include_archived": False,
            }

            if args.project:
                search_args["project"] = args.project
            if args.starred:
                search_args["starred"] = True
            if args.source:
                search_args["source"] = args.source

            conversations = db.search_conversations(**search_args)
        else:
            # List with filters
            filter_args = {
                "limit": None,  # Get all matching, filter later
                "include_archived": False,
            }

            if args.project:
                filter_args["project"] = args.project
            if args.starred:
                filter_args["starred"] = True
            if args.source:
                filter_args["source"] = args.source

            conversations = db.list_conversations(**filter_args)

        # Additional filtering
        if args.title:
            conversations = [
                c for c in conversations if args.title.lower() in c.title.lower()
            ]
        if args.no_tags:
            conversations = [c for c in conversations if not c.to_dict().get("tags")]

        # Apply limit after all filtering
        if args.limit is not None:
            conversations = conversations[: args.limit]

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
                content = (
                    msg.content.text[:200]
                    if msg.content.text and len(msg.content.text) > 200
                    else (msg.content.text or "")
                )
                context += f"{role}: {content}\n\n"

            # Ask LLM for tags
            tag_prompt = f"""Based on this conversation, suggest 3-5 relevant tags (single words or short phrases).
Return ONLY the tags as a comma-separated list, nothing else.

{context}

Tags:"""

            try:
                response = provider.chat(
                    [Message(role=MessageRole.USER, content=tag_prompt)],
                    temperature=0.3,
                )

                # Parse tags
                response_text = (
                    response.content if hasattr(response, "content") else str(response)
                )
                tags = [t.strip() for t in response_text.strip().split(",")]
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
                    apply = confirm == "y"

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


def execute_ask_tool(
    db: ConversationDB,
    tool_name: str,
    tool_args: dict,
    debug: bool = False,
    use_rich: bool = True,
    shell_executor=None,
) -> str:
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
        if tool_name == "search_conversations":
            # Parse tags if provided
            tags_list = (
                tool_args.get("tags", "").split(",") if tool_args.get("tags") else None
            )

            # Convert string booleans to actual booleans
            # IMPORTANT: Only return True if explicitly true, otherwise None (not False!)
            # When LLM passes "false" or False, it usually means "not filtering" not "filter to false"
            def to_bool_or_none(val):
                if val is None:
                    return None
                if isinstance(val, bool):
                    return (
                        True if val else None
                    )  # Only True matters, False = not filtering
                if isinstance(val, str):
                    lower_val = val.lower()
                    if lower_val in ("true", "1", "yes"):
                        return True
                    # "false", "none", "null", "0", "no" all mean "not filtering"
                    return None
                return None

            # Convert boolean flags - only True matters for filtering
            starred = to_bool_or_none(tool_args.get("starred"))
            pinned = to_bool_or_none(tool_args.get("pinned"))
            archived = to_bool_or_none(tool_args.get("archived"))

            # Clean up "None" strings in other params
            def clean_none(val):
                if val is None or (
                    isinstance(val, str) and val.lower() in ("none", "null", "")
                ):
                    return None
                return val

            # Clean all string params that might be "None" or "null"
            query_text = clean_none(tool_args.get("query"))
            source = clean_none(tool_args.get("source"))
            project = clean_none(tool_args.get("project"))
            model = clean_none(tool_args.get("model"))
            limit_val = clean_none(tool_args.get("limit"))

            if debug:
                print(
                    f"[DEBUG] Parsed filters: starred={starred}, pinned={pinned}, archived={archived}",
                    file=sys.stderr,
                )
                print(
                    f"[DEBUG] query={query_text}, source={source}, model={model}",
                    file=sys.stderr,
                )

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
                    include_archived=False,
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
                    include_archived=False,
                )

            if debug:
                print(f"[DEBUG] Query returned {len(results)} results", file=sys.stderr)

            if not results:
                return "No conversations found."

            # Format results with Rich if enabled
            if use_rich:
                from ctk.core.formatting import format_conversations_table

                # Limit to 10 for display
                display_results = results[:10]
                format_conversations_table(display_results, show_message_count=False)

                if len(results) > 10:
                    from rich.console import Console

                    console = Console()
                    console.print(
                        f"[dim]... and {len(results) - 10} more results (showing first 10)[/dim]"
                    )

                return ""  # Already printed
            else:
                # Plain text format for JSON mode
                result_str = f"Found {len(results)} conversation(s):\n\n"
                for i, conv in enumerate(results[:10], 1):
                    conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
                    title = conv_dict.get("title", "Untitled")[:50]
                    result_str += f"[{i}] {conv_dict['id'][:8]} - {title}\n"

                if len(results) > 10:
                    result_str += (
                        f"\n... and {len(results) - 10} more (showing first 10)\n"
                    )

                result_str += (
                    f"\nUse: show [N] or cd [N] to view (e.g., 'show 1' or 'cd 2')"
                )
                return result_str

        elif tool_name == "get_conversation":
            conv_id = tool_args["conversation_id"]

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
            msg_count = len(tree.message_map)
            result_str += f"Messages: {msg_count}\n"

            # Show messages if requested
            if tool_args.get("show_messages", False):
                result_str += "\nMessages:\n"
                path = tree.get_longest_path()
                for i, msg in enumerate(path[:5], 1):
                    # Handle both MessageContent objects and plain strings
                    if hasattr(msg.content, "get_text"):
                        text = msg.content.get_text()
                    else:
                        text = str(msg.content) if msg.content else ""
                    content = text[:100] if text else "(no content)"
                    role = (
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    )
                    result_str += f"\n{i}. {role}: {content}...\n"
                if len(path) > 5:
                    result_str += f"\n... and {len(path) - 5} more messages\n"

            return result_str

        elif tool_name == "get_statistics":
            stats = db.get_statistics()

            result_str = "Database Statistics:\n\n"
            result_str += (
                f"Total conversations: {stats.get('total_conversations', 0)}\n"
            )
            result_str += f"Total messages: {stats.get('total_messages', 0)}\n"

            if stats.get("by_source"):
                result_str += "\nBy source:\n"
                for source, count in stats["by_source"].items():
                    result_str += f"  - {source}: {count}\n"

            if stats.get("by_model"):
                result_str += "\nTop models:\n"
                for model, count in list(stats["by_model"].items())[:5]:
                    result_str += f"  - {model}: {count}\n"

            return result_str

        elif tool_name == "execute_shell_command":
            command = tool_args.get("command", "")
            if not command:
                return "Error: No command provided"

            if shell_executor is None:
                return "Error: Shell command execution not available in this context. Use the TUI shell mode."

            # Execute the command via the provided executor
            try:
                result = shell_executor(command)
                if hasattr(result, "output"):
                    # CommandResult object
                    if result.success:
                        return (
                            result.output
                            if result.output
                            else "(command executed successfully)"
                        )
                    else:
                        return (
                            f"Error: {result.error}"
                            if result.error
                            else "Command failed"
                        )
                else:
                    return str(result)
            except Exception as e:
                return f"Error executing command: {e}"

        elif tool_name == "star_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            # Resolve prefix
            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.star_conversation(conv_id)
            return f"Starred conversation {conv_id[:8]}..."

        elif tool_name == "unstar_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unstar_conversation(conv_id)
            return f"Unstarred conversation {conv_id[:8]}..."

        elif tool_name == "pin_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.pin_conversation(conv_id)
            return f"Pinned conversation {conv_id[:8]}..."

        elif tool_name == "unpin_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unpin_conversation(conv_id)
            return f"Unpinned conversation {conv_id[:8]}..."

        elif tool_name == "archive_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.archive_conversation(conv_id)
            return f"Archived conversation {conv_id[:8]}..."

        elif tool_name == "unarchive_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.unarchive_conversation(conv_id)
            return f"Unarchived conversation {conv_id[:8]}..."

        elif tool_name == "rename_conversation":
            conv_id = tool_args.get("conversation_id", "")
            title = tool_args.get("title", "")
            if not conv_id:
                return "Error: conversation_id required"
            if not title:
                return "Error: title required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            db.update_conversation_title(conv_id, title)
            return f"Renamed conversation {conv_id[:8]}... to '{title}'"

        elif tool_name == "show_conversation_content":
            from ctk.core.conversation_display import show_conversation_helper

            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            path_selection = tool_args.get("path_selection", "longest")

            result = show_conversation_helper(
                db=db,
                conv_id=conv_id,
                path_selection=path_selection,
                plain_output=True,
                show_metadata=True,
            )

            if result["success"]:
                return result["output"]
            else:
                return f"Error: {result['error']}"

        elif tool_name == "show_conversation_tree":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            # Use shell command if executor available
            if shell_executor:
                result = shell_executor(f"tree {conv_id}")
                if hasattr(result, "output"):
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

        elif tool_name == "delete_conversation":
            conv_id = tool_args.get("conversation_id", "")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            # Get title before deletion for confirmation message
            tree = db.load_conversation(conv_id)
            title = tree.title if tree else "Unknown"

            db.delete_conversation(conv_id)
            return f"Deleted conversation '{title}' ({conv_id[:8]}...)"

        elif tool_name == "tag_conversation":
            conv_id = tool_args.get("conversation_id", "")
            tags = tool_args.get("tags", [])
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
            existing_tags = (
                tree.metadata.tags if tree.metadata and tree.metadata.tags else []
            )
            new_tags = [t for t in tags if t not in existing_tags]
            tree.metadata.tags = existing_tags + new_tags
            db.save_conversation(tree)

            return f"Added tags to {conv_id[:8]}...: {', '.join(new_tags)}"

        elif tool_name == "list_tags":
            # Get all tags with counts
            stats = db.get_statistics()
            tags_data = stats.get("by_tag", {})

            if not tags_data:
                return "No tags found in database."

            result_str = "Tags in database:\n\n"
            # Sort by count descending
            sorted_tags = sorted(tags_data.items(), key=lambda x: x[1], reverse=True)
            for tag, count in sorted_tags:
                result_str += f"  {tag}: {count} conversation(s)\n"

            result_str += f"\nTotal: {len(tags_data)} unique tags"
            return result_str

        elif tool_name == "remove_tag":
            conv_id = tool_args.get("conversation_id", "")
            tag = tool_args.get("tag", "")
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

        elif tool_name == "list_sources":
            stats = db.get_statistics()
            sources_data = stats.get("by_source", {})

            if not sources_data:
                return "No sources found in database."

            result_str = "Sources in database:\n\n"
            sorted_sources = sorted(
                sources_data.items(), key=lambda x: x[1], reverse=True
            )
            for source, count in sorted_sources:
                result_str += f"  {source}: {count} conversation(s)\n"

            result_str += f"\nTotal: {len(sources_data)} sources"
            return result_str

        elif tool_name == "list_models":
            stats = db.get_statistics()
            models_data = stats.get("by_model", {})

            if not models_data:
                return "No models found in database."

            result_str = "Models in database:\n\n"
            sorted_models = sorted(
                models_data.items(), key=lambda x: x[1], reverse=True
            )
            for model, count in sorted_models[:20]:  # Limit to top 20
                result_str += f"  {model}: {count} conversation(s)\n"

            if len(models_data) > 20:
                result_str += f"\n  ... and {len(models_data) - 20} more models"

            result_str += f"\nTotal: {len(models_data)} unique models"
            return result_str

        elif tool_name == "export_conversation":
            conv_id = tool_args.get("conversation_id", "")
            export_format = tool_args.get("format", "markdown")
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            if export_format == "markdown":
                from ctk.exporters.markdown import \
                    MarkdownExporter

                exporter = MarkdownExporter()
                output = exporter.export_to_string(tree)
                return f"Markdown export of '{tree.title}':\n\n{output}"

            elif export_format == "json":
                import json

                # Convert to dict
                conv_dict = {
                    "id": tree.id,
                    "title": tree.title,
                    "messages": [
                        {
                            "role": msg.role.value if msg.role else "user",
                            "content": (
                                msg.content.get_text()
                                if hasattr(msg.content, "get_text")
                                else str(msg.content)
                            ),
                        }
                        for msg in tree.get_longest_path()
                    ],
                }
                return f"JSON export:\n{json.dumps(conv_dict, indent=2)}"

            elif export_format == "jsonl":
                messages = tree.get_longest_path()
                lines = []
                for msg in messages:
                    import json

                    line = json.dumps(
                        {
                            "role": msg.role.value if msg.role else "user",
                            "content": (
                                msg.content.get_text()
                                if hasattr(msg.content, "get_text")
                                else str(msg.content)
                            ),
                        }
                    )
                    lines.append(line)
                return f"JSONL export ({len(lines)} messages):\n" + "\n".join(lines)

            else:
                return f"Unknown format: {export_format}. Use markdown, json, or jsonl."

        elif tool_name == "duplicate_conversation":
            conv_id = tool_args.get("conversation_id", "")
            new_title = tool_args.get("new_title", None)
            if not conv_id:
                return "Error: conversation_id required"

            conv_id = _resolve_conversation_id(db, conv_id)
            if conv_id.startswith("Error:"):
                return conv_id

            tree = db.load_conversation(conv_id)
            if not tree:
                return f"Conversation {conv_id} not found"

            # Create a deep copy with new ID
            import copy
            import uuid

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
            new_tree.root_message_ids = [
                old_to_new.get(rid, rid) for rid in new_tree.root_message_ids
            ]

            db.save_conversation(new_tree)
            return f"Created copy: '{new_tree.title}' ({new_tree.id[:8]}...)"

        elif tool_name == "get_recent_conversations":
            limit = tool_args.get("limit", 10)
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
                conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
                flags = ""
                if conv_dict.get("starred_at"):
                    flags += "⭐"
                if conv_dict.get("pinned_at"):
                    flags += "📌"

                title = conv_dict.get("title", "Untitled")[:50]
                updated = conv_dict.get("updated_at", "Unknown")[:19]

                result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
                result_str += f"   Updated: {updated}\n"

            result_str += f"\nType `show <id>` to view any conversation."
            return result_str

        elif tool_name == "list_conversations":
            # Get filter parameters
            starred = tool_args.get("starred")
            pinned = tool_args.get("pinned")
            archived = tool_args.get("archived")
            limit = tool_args.get("limit", 20)
            source = tool_args.get("source")
            model = tool_args.get("model")

            if not isinstance(limit, int):
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    limit = 20

            # Build kwargs for list_conversations
            kwargs = {"limit": limit}
            if starred is not None:
                kwargs["starred"] = starred
            if pinned is not None:
                kwargs["pinned"] = pinned
            if archived is not None:
                kwargs["archived"] = archived
            if source:
                kwargs["source"] = source
            if model:
                kwargs["model"] = model

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
                conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
                flags = ""
                if conv_dict.get("starred_at"):
                    flags += "⭐"
                if conv_dict.get("pinned_at"):
                    flags += "📌"
                if conv_dict.get("archived_at"):
                    flags += "📦"

                title = conv_dict.get("title", "Untitled")[:50]
                source_str = conv_dict.get("metadata", {}).get("source", "") or ""
                model_str = conv_dict.get("metadata", {}).get("model", "") or ""

                result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
                if source_str or model_str:
                    result_str += f"   {source_str} | {model_str}\n"

            return result_str

        elif tool_name == "list_conversation_paths":
            conv_id_arg = tool_args.get("conversation_id", "")
            conv_id = _resolve_conversation_id(db, conv_id_arg)
            if not conv_id:
                return f"Conversation not found: {conv_id_arg}"

            conversation = db.load_conversation(conv_id)
            if not conversation:
                return f"Conversation not found: {conv_id}"

            paths = conversation.get_all_paths()

            if not paths:
                return f"No paths found in conversation {conv_id[:8]}..."

            result_str = (
                f"Paths in conversation {conv_id[:8]}... ({len(paths)} total):\n\n"
            )
            for i, path in enumerate(paths, 1):
                result_str += f"Path {i} ({len(path)} messages):\n"
                for msg in path:
                    role_label = msg.role.value.title() if msg.role else "User"
                    content_text = (
                        msg.content.get_text()
                        if hasattr(msg.content, "get_text")
                        else str(msg.content)
                    )
                    preview = (
                        content_text[:50].replace("\n", " ").strip()
                        if content_text
                        else ""
                    )
                    if len(content_text) > 50:
                        preview += "..."
                    result_str += f"  {role_label}: {preview}\n"
                result_str += "\n"

            return result_str

        elif tool_name == "list_plugins":
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

        elif tool_name == "auto_tag_conversation":
            conv_id_arg = tool_args.get("conversation_id", "")
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

            new_tags = args.add.split(",")
            conv.metadata.tags.extend(new_tags)
            db.save_conversation(conv)
            print(f"Added tags to conversation: {', '.join(new_tags)}")

        elif args.remove and args.conversation_id:
            # Remove tags from a conversation
            conv = db.load_conversation(args.conversation_id)
            if not conv:
                print(f"Error: Conversation {args.conversation_id} not found")
                return 1

            tags_to_remove = set(args.remove.split(","))
            conv.metadata.tags = [
                t for t in conv.metadata.tags if t not in tags_to_remove
            ]
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
                if tag.get("category"):
                    if tag["category"] not in categorized:
                        categorized[tag["category"]] = []
                    categorized[tag["category"]].append(tag)
                else:
                    uncategorized.append(tag)

            print(f"📏 Total Tags: {len(tags)}\n")

            # Show categorized tags
            for category, cat_tags in sorted(categorized.items()):
                print(f"\n📁 {category.upper()}:")
                for tag in sorted(
                    cat_tags, key=lambda x: x.get("usage_count", 0), reverse=True
                ):
                    count = tag.get("usage_count", 0)
                    bar = "█" * min(30, count // 10 + 1)
                    print(f"  {tag['name']:30} {count:5} {bar}")

            # Show uncategorized tags
            if uncategorized:
                print(f"\n🏷️  UNCATEGORIZED:")
                for tag in sorted(
                    uncategorized, key=lambda x: x.get("usage_count", 0), reverse=True
                )[:20]:
                    count = tag.get("usage_count", 0)
                    bar = "█" * min(30, count // 10 + 1)
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

        total = sum(m["count"] for m in models)
        for model_info in models:
            percentage = (model_info["count"] / total) * 100
            bar = "█" * int(percentage / 2)
            print(
                f"{model_info['model']:<40} {model_info['count']:<10} {bar} {percentage:.1f}%"
            )

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

        total = sum(s["count"] for s in sources)
        for source_info in sources:
            percentage = (source_info["count"] / total) * 100
            bar = "█" * int(percentage / 2)
            print(
                f"{source_info['source']:<30} {source_info['count']:<10} {bar} {percentage:.1f}%"
            )

    return 0


def _launch_default_tui(args, parser) -> int:
    """Resolve a DB path and launch the TUI for the no-subcommand case.

    Resolution order: ``--db`` flag, then ``database.default_path`` in
    ``~/.ctk/config.json``. Bails with a helpful error (and the help
    text) if neither yields a path, rather than silently opening an
    empty DB.
    """
    import os
    from ctk.core.config import get_config

    db_path = args.db
    if not db_path:
        cfg = get_config()
        db_path = cfg.config.get("database", {}).get("default_path")
        if db_path:
            db_path = os.path.expanduser(db_path)
            # ConversationDB expects a directory and stores the SQLite
            # file at <dir>/conversations.db. Older configs sometimes
            # named the SQLite file directly; tolerate both shapes.
            if os.path.isfile(db_path) and db_path.endswith(".db"):
                db_path = os.path.dirname(db_path) or "."
            if not os.path.exists(db_path):
                print(
                    f"Configured database does not exist: {db_path}\n"
                    "Either create it with `ctk db init`, import a "
                    "conversation export with `ctk import …`, or pass "
                    "`--db <path>` to use a different one."
                )
                return 1
    if not db_path:
        print(
            "No database configured. Either:\n"
            "  • pass --db <path> to open one explicitly,\n"
            "  • set `database.default_path` in ~/.ctk/config.json, or\n"
            "  • use `ctk import …` to create one from an export.\n"
        )
        parser.print_help()
        return 1

    # Forward to cmd_tui which handles provider construction + launch.
    # Make a shim namespace so cmd_tui doesn't see top-level flags it
    # doesn't expect.
    import argparse as _ap

    forwarded = _ap.Namespace(
        db=db_path,
        model=args.model,
        base_url=args.base_url,
        no_chat=args.no_chat,
        no_tools=args.no_tools,
    )
    return cmd_tui(forwarded)


def cmd_tui(args):
    """Launch the full-screen Textual TUI.

    Chat is enabled by default using whatever provider is configured in
    ``~/.ctk/config.json`` (or the environment). Pass ``--no-chat`` for
    browse-only, which skips the connectivity probe entirely.
    """
    from ctk.llm.factory import build_provider
    from ctk.tui.app import run as run_tui

    provider = None
    if not getattr(args, "no_chat", False):
        try:
            provider = build_provider(
                model=getattr(args, "model", None),
                base_url=getattr(args, "base_url", None),
            )
        except Exception as exc:
            print(f"Chat disabled: could not build provider ({exc})")
            provider = None
        else:
            if not provider.is_available():
                print(
                    f"Chat disabled: cannot reach {provider.base_url}. "
                    "Use --no-chat to silence this, or fix your endpoint."
                )
                provider = None

    try:
        run_tui(
            args.db,
            provider=provider,
            enable_tools=not getattr(args, "no_tools", False),
        )
    except KeyboardInterrupt:
        pass
    return 0


def cmd_show(args):
    """Show a specific conversation"""
    from ctk.core.conversation_display import show_conversation_helper

    db = ConversationDB(args.db)

    try:
        # Validate conversation ID
        try:
            conv_id = validate_conversation_id(args.id, allow_partial=True)
        except ValidationError as e:
            print(f"Error: Invalid conversation ID: {e}")
            return 1

        # Determine which path to show based on args and validate
        path_selection = getattr(args, "path", "longest")  # Default to longest
        try:
            path_selection = validate_path_selection(path_selection)
        except ValidationError as e:
            print(f"Error: Invalid path selection: {e}")
            return 1

        # Use shared helper to load conversation
        result = show_conversation_helper(
            db=db,
            conv_id=conv_id,
            path_selection=path_selection,
            plain_output=getattr(args, "no_color", False),
            show_metadata=True,
        )

        if not result["success"]:
            print(f"Error: {result['error']}")
            return 1

        tree = result["conversation"]
        nav = result["navigator"]
        path = result["path"]
        path_count = result["path_count"]

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

        if getattr(args, "no_color", False):
            # Plain output
            print(f"\nMessages (path: {path_selection}, {len(path)} messages):")
            print(nav.format_path(path, show_metadata=True))
        else:
            # Pretty output
            console = Console()
            console.print(
                f"\n[bold]Messages (path: {path_selection}, {len(path)} messages):[/bold]"
            )
            render_markdown = not getattr(args, "no_markdown", False)
            nav.print_path(
                path,
                console=console,
                show_metadata=True,
                render_markdown=render_markdown,
            )

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
            if confirm != "yes":
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


def cmd_sql(args):
    """Execute SQL queries with Rich table output"""
    import sqlite3

    from rich.console import Console
    from rich.table import Table

    console = Console()

    if not args.db:
        print("Error: Database path required")
        return 1

    # Resolve database path - support both directory and file paths
    db_path = Path(args.db)
    if db_path.is_dir():
        db_file = db_path / "conversations.db"
    elif db_path.suffix == ".db":
        db_file = db_path
    else:
        db_file = db_path / "conversations.db"

    if not db_file.exists():
        print(f"Error: Database not found: {db_file}")
        return 1

    try:
        # Open database in read-only mode
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Show schema if requested
        if args.schema:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            console.print("\n[bold cyan]Database Schema[/bold cyan]\n")

            for table_name in tables:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()

                table = Table(title=f"[bold]{table_name}[/bold]", show_header=True)
                table.add_column("Column", style="cyan")
                table.add_column("Type", style="green")
                table.add_column("PK", style="yellow")
                table.add_column("Nullable", style="dim")

                for col in columns:
                    # col: (cid, name, type, notnull, default_value, pk)
                    is_pk = "✓" if col[5] else ""
                    nullable = "" if col[3] else "✓"
                    table.add_row(col[1], col[2], is_pk, nullable)

                console.print(table)
                console.print()

            conn.close()
            return 0

        # Interactive mode
        if args.interactive:
            console.print("[bold cyan]CTK SQL Interactive Mode[/bold cyan]")
            console.print(
                "Type SQL queries, 'schema' to see tables, or 'exit' to quit.\n"
            )

            while True:
                try:
                    query = input("sql> ").strip()
                    if not query:
                        continue
                    if query.lower() in ("exit", "quit", "q"):
                        break
                    if query.lower() == "schema":
                        cursor.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                        )
                        tables = [row[0] for row in cursor.fetchall()]
                        console.print(f"Tables: {', '.join(tables)}")
                        continue

                    cursor.execute(query)
                    rows = cursor.fetchall()
                    keys = (
                        [desc[0] for desc in cursor.description]
                        if cursor.description
                        else []
                    )

                    if rows:
                        _display_sql_results(
                            console, rows, keys, args.format, args.limit
                        )
                    else:
                        console.print("[dim]No results[/dim]")

                except KeyboardInterrupt:
                    console.print("\n")
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")

            conn.close()
            return 0

        # Single query mode
        if not args.query:
            print("Error: Query required (or use --interactive)")
            return 1

        cursor.execute(args.query)
        rows = cursor.fetchall()
        keys = [desc[0] for desc in cursor.description] if cursor.description else []

        if rows:
            _display_sql_results(console, rows, keys, args.format, args.limit)
        else:
            console.print("[dim]No results[/dim]")

        conn.close()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def _display_sql_results(console, rows, keys, format_type, limit):
    """Display SQL query results in the specified format"""
    import json

    from rich.table import Table

    # Apply limit
    if limit and limit > 0:
        rows = rows[:limit]

    if format_type == "json":
        data = []
        for row in rows:
            if hasattr(row, "_asdict"):
                data.append(row._asdict())
            elif hasattr(row, "_mapping"):
                data.append(dict(row._mapping))
            else:
                data.append(dict(zip(keys, row)))
        print(json.dumps(data, indent=2, default=str))

    elif format_type == "csv":
        print(",".join(str(k) for k in keys))
        for row in rows:
            print(",".join(str(v) if v is not None else "" for v in row))

    else:  # table (default)
        table = Table(show_header=True, header_style="bold cyan")

        for key in keys:
            table.add_column(str(key))

        for row in rows:
            table.add_row(*[str(v) if v is not None else "" for v in row])

        console.print(table)
        console.print(f"\n[dim]{len(rows)} row(s)[/dim]")


def main():
    """Main CLI entry point.

    With no subcommand, ``ctk`` opens the Textual TUI on whatever
    database is configured in ``~/.ctk/config.json`` (or overridden
    by ``--db``). Bulk / scriptable operations remain as explicit
    subcommands (``import``, ``export``, ``query``, ``sql``, ``db``,
    ``auto-tag``, ``config``, ``llm``).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Conversation Toolkit. Run with no subcommand to open the TUI; "
            "use a subcommand for bulk / scripted operations."
        )
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Top-level flags that apply when ``ctk`` is invoked without a
    # subcommand (i.e., the TUI default path). Subcommands that need
    # the same flags declare them locally so subcommand-style usage
    # keeps working unchanged.
    parser.add_argument(
        "--db",
        "-d",
        default=None,
        help="Database path to open in the TUI (default: from config)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Model name for the TUI's chat (default: from config)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible endpoint for the TUI's chat (default: from config)",
    )
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="Open the TUI in browse-only mode (skip the LLM probe)",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable tool calling in the TUI",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import conversations")
    import_parser.add_argument(
        "input",
        help='Input file path (or "auto" for auto-search with copilot/claude_code/cursor)',
    )
    import_parser.add_argument(
        "--format",
        "-f",
        help="Input format: openai, anthropic, copilot, gemini, jsonl, filesystem_coding (auto-detect if not specified)",
    )
    import_parser.add_argument("--db", "-d", help="Database path to save to")
    import_parser.add_argument(
        "--output", "-o", help="Output file path (for conversion)"
    )
    import_parser.add_argument(
        "--output-format", help="Output format for conversion: json, markdown, jsonl"
    )
    import_parser.add_argument("--tags", "-t", help="Comma-separated tags to add")
    import_parser.add_argument(
        "--sanitize", action="store_true", help="Sanitize sensitive data"
    )
    import_parser.add_argument(
        "--path-selection",
        default="longest",
        choices=["longest", "first", "last"],
        help="For branching conversations: which path to export (default: longest)",
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export conversations")
    export_parser.add_argument("output", help="Output file path")
    export_parser.add_argument("--db", "-d", required=True, help="Database path")
    export_parser.add_argument(
        "--format",
        "-f",
        default="jsonl",
        help="Export format: json, markdown, jsonl, html, hugo, echo (default: jsonl)",
    )
    export_parser.add_argument(
        "--ids", nargs="+", help="Specific conversation IDs to export"
    )
    # ``--view`` was removed in 2.12.0 along with the views machinery.
    export_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum conversations (0 = all, default: all)",
    )
    export_parser.add_argument(
        "--filter-source",
        help="Filter by source (e.g., ChatGPT, Claude, GitHub Copilot)",
    )
    export_parser.add_argument(
        "--filter-model", help="Filter by model (e.g., gpt-4, claude-3)"
    )
    export_parser.add_argument("--filter-tags", help="Filter by tags (comma-separated)")
    export_parser.add_argument(
        "--sanitize", action="store_true", help="Sanitize sensitive data"
    )
    export_parser.add_argument(
        "--path-selection",
        default="longest",
        choices=["longest", "first", "last"],
        help="Path selection strategy for tree conversations (default: longest)",
    )
    export_parser.add_argument(
        "--include-metadata", action="store_true", help="Include metadata in export"
    )
    # HTML-specific options
    export_parser.add_argument(
        "--theme",
        default="auto",
        choices=["light", "dark", "auto"],
        help="Theme for HTML export (default: auto)",
    )
    export_parser.add_argument(
        "--group-by",
        default="date",
        choices=["date", "source", "model", "tag"],
        help="Grouping strategy for HTML export (default: date)",
    )
    export_parser.add_argument(
        "--show-tree",
        action="store_true",
        default=True,
        help="Show conversation tree structure in HTML export",
    )
    export_parser.add_argument(
        "--no-embed",
        action="store_false",
        dest="embed",
        default=True,
        help="Create separate index.html + conversations.jsonl (requires web server). Default: embed data in single HTML file",
    )
    export_parser.add_argument(
        "--media-dir",
        help="Output media files to directory instead of embedding. Path relative to output file (default: embed in HTML)",
    )
    # Organization filters
    export_parser.add_argument(
        "--starred", action="store_true", help="Export only starred conversations"
    )
    export_parser.add_argument(
        "--pinned", action="store_true", help="Export only pinned conversations"
    )
    # Hugo-specific options
    export_parser.add_argument(
        "--draft",
        action="store_true",
        help="Hugo: mark exported conversations as draft",
    )
    export_parser.add_argument(
        "--no-date-prefix",
        action="store_false",
        dest="date_prefix",
        default=True,
        help="Hugo: do not include date prefix in directory names",
    )
    export_parser.add_argument(
        "--hugo-organize",
        choices=["none", "tags", "source", "date"],
        default="date",
        help="Hugo: organize conversations into subdirectories (default: date). 'none' = flat, 'tags' = by tag, 'source' = by source, 'date' = by date",
    )
    # ECHO-specific options
    export_parser.add_argument(
        "--include-db",
        action="store_true",
        help="ECHO: Include SQLite database copy in export",
    )
    export_parser.add_argument(
        "--owner-name",
        default="Unknown",
        help="ECHO: Owner name for README (default: Unknown)",
    )
    export_parser.add_argument(
        "--include-site",
        action="store_true",
        help="ECHO: Generate browsable HTML site in site/ subdirectory",
    )

    # Auto-tag command
    auto_tag_parser = subparsers.add_parser(
        "auto-tag", help="Auto-tag conversations using LLM"
    )
    auto_tag_parser.add_argument("--db", "-d", required=True, help="Database path")
    auto_tag_parser.add_argument(
        "--model", default=None, help="Model to use for tagging (default: from config)"
    )
    auto_tag_parser.add_argument(
        "--base-url", help="OpenAI-compatible endpoint (default: from config)"
    )
    auto_tag_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum conversations to tag (default: all matching)",
    )
    auto_tag_parser.add_argument(
        "--dry-run", action="store_true", help="Show suggestions without applying"
    )
    auto_tag_parser.add_argument(
        "--yes", "-y", action="store_true", help="Auto-approve all tags"
    )
    # Filters
    auto_tag_parser.add_argument(
        "--query", "-q", help="Full-text search in conversation content"
    )
    auto_tag_parser.add_argument("--project", help="Filter by project")
    auto_tag_parser.add_argument(
        "--starred", action="store_true", help="Only starred conversations"
    )
    auto_tag_parser.add_argument("--source", help="Filter by source")
    auto_tag_parser.add_argument("--title", help="Filter by title (partial match)")
    auto_tag_parser.add_argument(
        "--no-tags", action="store_true", help="Only conversations without tags"
    )

    # `tui` subcommand kept as an alias for muscle memory; bare `ctk`
    # also opens the TUI via the no-subcommand path. The legacy
    # `chat` and `say` subcommands were removed in 2.12.0 — interactive
    # chat lives in the TUI now, with slash commands for power users.
    tui_parser = subparsers.add_parser(
        "tui", help="Open the full-screen TUI (alias for bare `ctk`)"
    )
    tui_parser.add_argument(
        "--db", "-d", required=False, help="Database path to browse"
    )
    tui_parser.add_argument(
        "--model", "-m", default=None, help="Model name (default: from config)"
    )
    tui_parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible endpoint URL (default: from config)",
    )
    tui_parser.add_argument(
        "--no-chat",
        action="store_true",
        help="Browse-only mode; skip the LLM probe on startup",
    )
    tui_parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable tool calling",
    )

    # Query command - human-friendly search with composable flags
    query_parser = subparsers.add_parser(
        "query", help="Search conversations with flags"
    )
    query_parser.add_argument("text", nargs="?", help="Optional search text")
    query_parser.add_argument("--db", "-d", required=True, help="Database path")
    # Filters (multiple --tag = AND)
    query_parser.add_argument(
        "--tag", action="append", help="Filter by tag (repeatable, AND logic)"
    )
    query_parser.add_argument("--starred", action="store_true", help="Only starred")
    query_parser.add_argument("--pinned", action="store_true", help="Only pinned")
    query_parser.add_argument("--archived", action="store_true", help="Only archived")
    query_parser.add_argument(
        "--include-archived", action="store_true", help="Include archived in results"
    )
    query_parser.add_argument("--source", help="Filter by source")
    query_parser.add_argument("--model", help="Filter by model")
    query_parser.add_argument("--project", help="Filter by project")
    # Date filters
    query_parser.add_argument("--since", help="After date (YYYY-MM-DD or 7d, 1w, 1m)")
    query_parser.add_argument("--until", help="Before date")
    # View integration
    # ``--view`` was removed in 2.12.0 along with the views machinery.
    # Output
    query_parser.add_argument(
        "--format", "-f", choices=["table", "json", "csv"], default="table"
    )
    query_parser.add_argument("--limit", "-n", type=int, help="Max results")
    query_parser.add_argument(
        "--order-by",
        choices=["created_at", "updated_at", "title"],
        default="updated_at",
    )
    query_parser.add_argument("--asc", action="store_true", help="Sort ascending")
    # Cursor pagination
    query_parser.add_argument(
        "--cursor",
        help="Pagination cursor (use value from previous page's next_cursor)",
    )
    query_parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Results per page when using --cursor (default: 50)",
    )

    # SQL command - direct SQL queries with Rich output
    sql_parser = subparsers.add_parser("sql", help="Execute SQL queries on database")
    sql_parser.add_argument("query", nargs="?", help="SQL query to execute")
    sql_parser.add_argument("--db", "-d", required=True, help="Database path")
    sql_parser.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    sql_parser.add_argument("--limit", "-n", type=int, help="Limit number of rows")
    sql_parser.add_argument(
        "--schema", "-s", action="store_true", help="Show database schema"
    )
    sql_parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive SQL mode"
    )

    # Database operations command
    from ctk.cli_db import add_db_commands

    add_db_commands(subparsers)

    # Network/similarity operations command
    from ctk.cli_net import add_net_commands

    add_net_commands(subparsers)

    # LLM provider command group
    from ctk.cli_llm import add_llm_commands

    add_llm_commands(subparsers)

    # Config command group
    from ctk.cli_config import add_config_commands

    add_config_commands(subparsers)

    args = parser.parse_args()

    if args.verbose:
        setup_logging(verbose=True)

    if not args.command:
        # No subcommand: open the TUI. Resolve the database path from
        # CLI flag → config → bail with a helpful message if neither
        # provides one. We don't want the TUI to silently open against
        # an empty in-memory DB.
        return _launch_default_tui(args, parser)

    # Dispatch to command handler. The CLI surface is intentionally
    # small in 2.12.0: bulk / scripted operations only. Everything
    # interactive (per-conversation ops, chat, view management,
    # graph analytics) lives in the TUI now via bindings, slash
    # commands, and tool calls.
    commands = {
        "import": cmd_import,
        "export": cmd_export,
        "auto-tag": cmd_auto_tag,
        "tui": cmd_tui,
        "sql": cmd_sql,
        "query": cmd_query,
    }

    # Special handling for db subcommands
    if args.command == "db":
        from ctk.cli_db import (cmd_backup, cmd_dedupe, cmd_diff, cmd_filter,
                                cmd_info, cmd_init, cmd_intersect, cmd_merge,
                                cmd_split)
        from ctk.cli_db import cmd_stats as cmd_db_stats
        from ctk.cli_db import cmd_vacuum, cmd_validate

        db_commands = {
            "init": cmd_init,
            "info": cmd_info,
            "vacuum": cmd_vacuum,
            "backup": cmd_backup,
            "merge": cmd_merge,
            "diff": cmd_diff,
            "intersect": cmd_intersect,
            "filter": cmd_filter,
            "split": cmd_split,
            "dedupe": cmd_dedupe,
            "stats": cmd_db_stats,
            "validate": cmd_validate,
            # NOTE: 'query' removed - use 'ctk sql' for raw SQL, 'ctk query' for search
        }

        if hasattr(args, "db_command") and args.db_command:
            return db_commands[args.db_command](args)
        else:
            print("Error: No database operation specified")
            return 1

    # Special handling for net subcommands
    if args.command == "net":
        from ctk.cli_net import cmd_embeddings, cmd_links

        net_commands = {
            "embeddings": cmd_embeddings,
            "links": cmd_links,
        }
        if hasattr(args, "net_command") and args.net_command:
            return net_commands[args.net_command](args)
        print(
            "Error: no net operation specified. Available: embeddings, links.\n"
            "Analytical queries (similar, neighbors, clusters, ...) live as "
            "ctk.network MCP tools — ask the model from inside `ctk` (TUI)."
        )
        return 1

    # Special handling for llm subcommands
    if args.command == "llm":
        from ctk.cli_llm import dispatch_llm_command

        return dispatch_llm_command(args)

    # Special handling for config subcommands
    if args.command == "config":
        from ctk.cli_config import dispatch_config_command

        return dispatch_config_command(args)

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
