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


def resolve_conversation_id(db: ConversationDB, id_or_slug: str) -> Optional[str]:
    """Resolve a partial conversation ID or slug to a full ID."""
    # Try the database's resolve method first (handles slugs, prefixes, etc.)
    resolved = db.resolve_conversation(id_or_slug)
    if resolved:
        return resolved

    # If that failed, try to provide better error messages
    all_convs = db.list_conversations(limit=1000, include_archived=True)

    # Check for ID prefix matches
    id_matches = [c for c in all_convs if c.id.startswith(id_or_slug)]
    if len(id_matches) > 1:
        print(f"Error: Multiple conversations match ID '{id_or_slug}':")
        for match in id_matches[:5]:
            slug_info = f" ({match.slug})" if match.slug else ""
            print(f"  - {match.id[:8]}...{slug_info} {match.title}")
        return None

    # Check for slug matches
    slug_matches = [c for c in all_convs if c.slug and c.slug.startswith(id_or_slug)]
    if len(slug_matches) > 1:
        print(f"Error: Multiple conversations match slug '{id_or_slug}':")
        for match in slug_matches[:5]:
            print(f"  - {match.slug} ({match.id[:8]}...) {match.title}")
        return None

    print(f"Error: No conversation found matching '{id_or_slug}'")
    print("  Hint: Use ID prefix, slug, or partial slug (e.g., 'python-hints')")
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
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            role_style = {
                "USER": "green",
                "ASSISTANT": "blue",
                "SYSTEM": "yellow",
                "TOOL": "magenta",
            }.get(role, "white")

            content = msg.content.text if msg.content else ""
            if args.truncate and len(content) > args.truncate:
                content = content[: args.truncate] + "..."

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
            role = (
                message.role.value
                if hasattr(message.role, "value")
                else str(message.role)
            )
            role_style = {
                "USER": "green",
                "ASSISTANT": "blue",
                "SYSTEM": "yellow",
                "TOOL": "magenta",
            }.get(role, "white")

            content = message.content.text if message.content else ""
            preview = (
                content[:50].replace("\n", " ") + "..."
                if len(content) > 50
                else content.replace("\n", " ")
            )

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
                preview = last_msg.content.text[:60].replace("\n", " ")
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
            if confirm.lower() != "yes":
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

        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
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


def cmd_say(args):
    """Send a message to an existing conversation"""
    from ctk.core.models import Message, MessageContent, MessageRole

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Join message words
        message_text = " ".join(args.message)
        if not message_text.strip():
            print("Error: Message cannot be empty")
            return 1

        # Find the last message in the longest path to attach as parent
        longest_path = conv.get_longest_path()
        parent_id = longest_path[-1].id if longest_path else None

        # Determine role
        role = MessageRole.from_string(args.role) if args.role else MessageRole.USER

        # Create the message
        new_message = Message(
            role=role, content=MessageContent(text=message_text), parent_id=parent_id
        )

        # Add to conversation
        conv.add_message(new_message)

        # Save
        db.save_conversation(conv)

        role_str = role.value
        print(f"✓ Added {role_str} message to {conv_id[:8]}...")
        if args.show:
            print(f"\n[{role_str.upper()}]: {message_text}")

        return 0


def cmd_fork(args):
    """Create a branch from a specific message in a conversation"""
    from ctk.core.models import Message, MessageContent, MessageRole

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Find the message to fork from
        if args.message_id:
            # Use specified message ID
            parent_id = args.message_id
            if parent_id not in conv.message_map:
                # Try prefix match
                matches = [
                    mid for mid in conv.message_map.keys() if mid.startswith(parent_id)
                ]
                if len(matches) == 1:
                    parent_id = matches[0]
                elif len(matches) > 1:
                    print(f"Error: Multiple messages match '{args.message_id}'")
                    return 1
                else:
                    print(f"Error: Message '{args.message_id}' not found")
                    return 1
        else:
            # Use last message in longest path
            longest_path = conv.get_longest_path()
            if not longest_path:
                print("Error: Conversation has no messages")
                return 1
            parent_id = longest_path[-1].id

        # Create fork message
        message_text = " ".join(args.message)
        if not message_text.strip():
            print("Error: Fork message cannot be empty")
            return 1

        new_message = Message(
            role=MessageRole.USER,
            content=MessageContent(text=message_text),
            parent_id=parent_id,
        )

        conv.add_message(new_message)
        db.save_conversation(conv)

        print(f"✓ Created fork from message {parent_id[:8]}...")
        print(f"  New message: {new_message.id[:8]}...")
        print(f"  Branches: {conv.count_branches()}")

        return 0


def cmd_reply(args):
    """Get an LLM response and append it to a conversation"""
    from ctk.core.config import get_config
    from ctk.core.models import Message, MessageContent, MessageRole
    from ctk.integrations.llm.ollama import OllamaProvider

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Get conversation history for context
        messages = conv.get_longest_path()
        if not messages:
            print("Error: Conversation has no messages")
            return 1

        # Build message history for LLM
        history = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            content = msg.content.text if msg.content else ""
            history.append({"role": role, "content": content})

        # Initialize provider
        cfg = get_config()
        provider_name = args.provider or "ollama"
        provider_config = cfg.get_provider_config(provider_name)

        config = {
            "model": args.model or provider_config.get("default_model", "llama2"),
            "base_url": provider_config.get("base_url", "http://localhost:11434"),
            "timeout": provider_config.get("timeout", 120),
        }

        try:
            provider = OllamaProvider(config)
        except Exception as e:
            print(f"Error: Failed to initialize provider: {e}")
            return 1

        if not provider.is_available():
            print(f"Error: Cannot connect to {provider_name}")
            return 1

        # Get response
        print(f"Getting response from {config['model']}...")
        try:
            response_text = ""
            for chunk in provider.chat(history, stream=True):
                if chunk:
                    print(chunk, end="", flush=True)
                    response_text += chunk
            print()  # Newline after response
        except Exception as e:
            print(f"\nError getting response: {e}")
            return 1

        if not response_text.strip():
            print("Error: Empty response from LLM")
            return 1

        # Create response message
        parent_id = messages[-1].id
        response_message = Message(
            role=MessageRole.ASSISTANT,
            content=MessageContent(text=response_text),
            parent_id=parent_id,
            metadata={"model": config["model"]},
        )

        conv.add_message(response_message)
        db.save_conversation(conv)

        print(f"\n✓ Added response to {conv_id[:8]}...")
        return 0


def cmd_info(args):
    """Show detailed information about a conversation"""
    import json
    from datetime import datetime

    from rich.console import Console
    from rich.panel import Panel
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

        # Compute statistics
        paths = conv.get_all_paths()
        longest_path = conv.get_longest_path()
        all_messages = list(conv.message_map.values())

        # Role counts
        role_counts = {}
        total_chars = 0
        for msg in all_messages:
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            role_counts[role] = role_counts.get(role, 0) + 1
            if msg.content and msg.content.text:
                total_chars += len(msg.content.text)

        # Timestamps
        timestamps = [msg.timestamp for msg in all_messages if msg.timestamp]
        first_ts = min(timestamps) if timestamps else None
        last_ts = max(timestamps) if timestamps else None

        if args.json:
            info = {
                "id": conv.id,
                "title": conv.title,
                "slug": conv.metadata.slug,
                "source": conv.metadata.source,
                "model": conv.metadata.model,
                "created_at": (
                    str(conv.metadata.created_at) if conv.metadata.created_at else None
                ),
                "updated_at": (
                    str(conv.metadata.updated_at) if conv.metadata.updated_at else None
                ),
                "first_message": str(first_ts) if first_ts else None,
                "last_message": str(last_ts) if last_ts else None,
                "message_count": len(all_messages),
                "path_count": len(paths),
                "longest_path_length": len(longest_path),
                "total_characters": total_chars,
                "role_counts": role_counts,
                "tags": conv.metadata.tags,
                "starred": bool(conv.metadata.starred_at),
                "pinned": bool(conv.metadata.pinned_at),
                "archived": bool(conv.metadata.archived_at),
                "summary": conv.metadata.summary,
            }
            print(json.dumps(info, indent=2, default=str))
            return 0

        # Rich output
        title = conv.title or "Untitled"
        flags = []
        if conv.metadata.starred_at:
            flags.append("⭐")
        if conv.metadata.pinned_at:
            flags.append("📌")
        if conv.metadata.archived_at:
            flags.append("📦")

        header = f"{title} {' '.join(flags)}"
        console.print(Panel(header, style="bold cyan", title="Conversation Info"))

        # Basic info
        console.print(f"\n[bold]Identifiers:[/bold]")
        console.print(f"  ID: {conv.id}")
        if conv.metadata.slug:
            console.print(f"  Slug: {conv.metadata.slug}")
        if conv.metadata.source:
            console.print(f"  Source: {conv.metadata.source}")
        if conv.metadata.model:
            console.print(f"  Model: {conv.metadata.model}")

        # Timestamps
        console.print(f"\n[bold]Timeline:[/bold]")
        if conv.metadata.created_at:
            console.print(f"  Created: {conv.metadata.created_at}")
        if first_ts:
            console.print(f"  First message: {first_ts}")
        if last_ts:
            console.print(f"  Last message: {last_ts}")

        # Statistics
        console.print(f"\n[bold]Statistics:[/bold]")
        console.print(f"  Total messages: {len(all_messages)}")
        console.print(f"  Paths: {len(paths)}")
        console.print(f"  Longest path: {len(longest_path)} messages")
        console.print(f"  Total characters: {total_chars:,}")
        console.print(f"  Branches: {conv.count_branches()}")

        # Role breakdown
        console.print(f"\n[bold]Messages by Role:[/bold]")
        for role, count in sorted(role_counts.items()):
            console.print(f"  {role}: {count}")

        # Tags
        if conv.metadata.tags:
            console.print(f"\n[bold]Tags:[/bold] {', '.join(conv.metadata.tags)}")

        # Summary
        if conv.metadata.summary:
            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  {conv.metadata.summary}")

        return 0


def cmd_summarize(args):
    """Generate an LLM summary for a conversation"""
    from rich.console import Console

    from ctk.core.config import get_config
    from ctk.integrations.llm.ollama import OllamaProvider

    console = Console()

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Get messages to summarize
        if args.path is not None:
            paths = conv.get_all_paths()
            if args.path < 0 or args.path >= len(paths):
                print(f"Error: Path {args.path} not found (valid: 0-{len(paths)-1})")
                return 1
            messages = paths[args.path]
            path_desc = f"path {args.path}"
        elif args.all_paths:
            # Concatenate all paths (with separators)
            paths = conv.get_all_paths()
            messages = []
            for i, path in enumerate(paths):
                messages.extend(path)
                if i < len(paths) - 1:
                    # Add separator conceptually (will be handled in text building)
                    pass
            path_desc = "all paths"
        else:
            messages = conv.get_longest_path()
            path_desc = "longest path"

        if not messages:
            print("Error: No messages to summarize")
            return 1

        # Build conversation text for summarization
        conv_text = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            content = msg.content.text if msg.content else ""
            conv_text.append(f"{role}: {content}")

        full_text = "\n\n".join(conv_text)

        # Truncate if too long
        max_chars = args.max_chars or 10000
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n\n[TRUNCATED]"

        # Initialize LLM provider
        cfg = get_config()
        provider_name = args.provider or "ollama"
        provider_config = cfg.get_provider_config(provider_name)

        config = {
            "model": args.model or provider_config.get("default_model", "llama2"),
            "base_url": provider_config.get("base_url", "http://localhost:11434"),
            "timeout": provider_config.get("timeout", 120),
        }

        try:
            provider = OllamaProvider(config)
        except Exception as e:
            print(f"Error: Failed to initialize provider: {e}")
            return 1

        if not provider.is_available():
            print(f"Error: Cannot connect to {provider_name}")
            return 1

        # Build summary prompt
        prompt = f"""Summarize this conversation in 2-3 concise sentences. Focus on the main topic and key points discussed.

Conversation ({path_desc}, {len(messages)} messages):

{full_text}

Summary:"""

        console.print(f"Generating summary using {config['model']}...")

        try:
            summary_text = ""
            for chunk in provider.chat(
                [{"role": "user", "content": prompt}], stream=True
            ):
                if chunk:
                    print(chunk, end="", flush=True)
                    summary_text += chunk
            print()  # Newline after response
        except Exception as e:
            print(f"\nError generating summary: {e}")
            return 1

        summary_text = summary_text.strip()

        if not summary_text:
            print("Error: Empty summary from LLM")
            return 1

        # Save summary to metadata if requested
        if args.save:
            conv.metadata.summary = summary_text
            db.save_conversation(conv)
            console.print(f"\n[green]✓ Summary saved to conversation metadata[/green]")
        else:
            console.print(
                f"\n[dim](Use --save to store this summary in the conversation)[/dim]"
            )

        return 0


def cmd_export_conv(args):
    """Export a single conversation to a file"""
    import json
    from pathlib import Path

    with ConversationDB(args.db) as db:
        conv_id = resolve_conversation_id(db, args.id)
        if not conv_id:
            return 1

        conv = db.load_conversation(conv_id)
        if not conv:
            print(f"Error: Conversation {args.id} not found")
            return 1

        # Determine output format
        output_path = Path(args.output) if args.output else None
        fmt = args.format

        if output_path and not fmt:
            # Infer format from extension
            ext = output_path.suffix.lower()
            fmt = {
                ".json": "json",
                ".jsonl": "jsonl",
                ".md": "markdown",
                ".html": "html",
            }.get(ext, "json")

        fmt = fmt or "json"

        # Export based on format
        if fmt == "json":
            data = conv.to_dict()
            output = json.dumps(data, indent=2, default=str)

        elif fmt == "jsonl":
            # Export as JSONL (one message per line)
            lines = []
            for msg in conv.get_longest_path():
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = msg.content.text if msg.content else ""
                lines.append(json.dumps({"role": role, "content": content}))
            output = "\n".join(lines)

        elif fmt == "markdown":
            # Export as markdown
            lines = [f"# {conv.title or 'Untitled'}\n"]
            lines.append(f"**ID:** {conv.id}\n")
            if conv.metadata.model:
                lines.append(f"**Model:** {conv.metadata.model}\n")
            if conv.metadata.tags:
                lines.append(f"**Tags:** {', '.join(conv.metadata.tags)}\n")
            lines.append("\n---\n")

            for msg in conv.get_longest_path():
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = msg.content.text if msg.content else ""
                lines.append(f"\n## {role.upper()}\n\n{content}\n")

            output = "\n".join(lines)

        else:
            print(f"Error: Unsupported format '{fmt}'")
            return 1

        # Write output
        if output_path:
            output_path.write_text(output)
            print(f"✓ Exported to {output_path}")
        else:
            print(output)

        return 0


def add_conv_commands(subparsers):
    """Add conversation command group to parser"""
    conv_parser = subparsers.add_parser("conv", help="Conversation operations")
    conv_subparsers = conv_parser.add_subparsers(
        dest="conv_command", help="Conversation commands"
    )

    # show
    show_parser = conv_subparsers.add_parser("show", help="Show conversation content")
    show_parser.add_argument("id", help="Conversation ID (full or partial)")
    show_parser.add_argument("--db", "-d", required=True, help="Database path")
    show_parser.add_argument(
        "--path", "-p", type=int, help="Path index for branching conversations"
    )
    show_parser.add_argument(
        "--truncate", "-t", type=int, help="Truncate messages to N characters"
    )

    # tree
    tree_parser = conv_subparsers.add_parser(
        "tree", help="Show conversation tree structure"
    )
    tree_parser.add_argument("id", help="Conversation ID (full or partial)")
    tree_parser.add_argument("--db", "-d", required=True, help="Database path")

    # paths
    paths_parser = conv_subparsers.add_parser(
        "paths", help="List all paths in conversation"
    )
    paths_parser.add_argument("id", help="Conversation ID (full or partial)")
    paths_parser.add_argument("--db", "-d", required=True, help="Database path")

    # star
    star_parser = conv_subparsers.add_parser("star", help="Star/unstar conversation")
    star_parser.add_argument("id", help="Conversation ID (full or partial)")
    star_parser.add_argument("--db", "-d", required=True, help="Database path")
    star_parser.add_argument(
        "--unstar", action="store_true", help="Unstar instead of star"
    )

    # pin
    pin_parser = conv_subparsers.add_parser("pin", help="Pin/unpin conversation")
    pin_parser.add_argument("id", help="Conversation ID (full or partial)")
    pin_parser.add_argument("--db", "-d", required=True, help="Database path")
    pin_parser.add_argument("--unpin", action="store_true", help="Unpin instead of pin")

    # archive
    archive_parser = conv_subparsers.add_parser(
        "archive", help="Archive/unarchive conversation"
    )
    archive_parser.add_argument("id", help="Conversation ID (full or partial)")
    archive_parser.add_argument("--db", "-d", required=True, help="Database path")
    archive_parser.add_argument(
        "--unarchive", action="store_true", help="Unarchive instead of archive"
    )

    # title
    title_parser = conv_subparsers.add_parser("title", help="Rename conversation")
    title_parser.add_argument("id", help="Conversation ID (full or partial)")
    title_parser.add_argument("title", help="New title")
    title_parser.add_argument("--db", "-d", required=True, help="Database path")

    # delete
    delete_parser = conv_subparsers.add_parser("delete", help="Delete conversation")
    delete_parser.add_argument("id", help="Conversation ID (full or partial)")
    delete_parser.add_argument("--db", "-d", required=True, help="Database path")
    delete_parser.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation"
    )

    # duplicate
    duplicate_parser = conv_subparsers.add_parser(
        "duplicate", help="Duplicate conversation"
    )
    duplicate_parser.add_argument("id", help="Conversation ID (full or partial)")
    duplicate_parser.add_argument("--db", "-d", required=True, help="Database path")
    duplicate_parser.add_argument("--title", help="Title for duplicated conversation")

    # tag
    tag_parser = conv_subparsers.add_parser("tag", help="Add tags to conversation")
    tag_parser.add_argument("id", help="Conversation ID (full or partial)")
    tag_parser.add_argument("tags", help="Comma-separated tags to add")
    tag_parser.add_argument("--db", "-d", required=True, help="Database path")

    # untag
    untag_parser = conv_subparsers.add_parser(
        "untag", help="Remove tag from conversation"
    )
    untag_parser.add_argument("id", help="Conversation ID (full or partial)")
    untag_parser.add_argument("tag", help="Tag to remove")
    untag_parser.add_argument("--db", "-d", required=True, help="Database path")

    # say
    say_parser = conv_subparsers.add_parser(
        "say", help="Send a message to a conversation"
    )
    say_parser.add_argument("id", help="Conversation ID (full or partial)")
    say_parser.add_argument("message", nargs="+", help="Message to send")
    say_parser.add_argument("--db", "-d", required=True, help="Database path")
    say_parser.add_argument(
        "--role",
        "-r",
        choices=["user", "assistant", "system"],
        default="user",
        help="Message role (default: user)",
    )
    say_parser.add_argument(
        "--show", "-s", action="store_true", help="Show the message after adding"
    )

    # fork
    fork_parser = conv_subparsers.add_parser(
        "fork", help="Create a branch from a message"
    )
    fork_parser.add_argument("id", help="Conversation ID (full or partial)")
    fork_parser.add_argument("message", nargs="+", help="Fork message to send")
    fork_parser.add_argument("--db", "-d", required=True, help="Database path")
    fork_parser.add_argument(
        "--message-id", "-m", help="Message ID to fork from (default: last message)"
    )

    # reply
    reply_parser = conv_subparsers.add_parser(
        "reply", help="Get LLM response and append to conversation"
    )
    reply_parser.add_argument("id", help="Conversation ID (full or partial)")
    reply_parser.add_argument("--db", "-d", required=True, help="Database path")
    reply_parser.add_argument(
        "--provider", "-p", default="ollama", help="LLM provider (default: ollama)"
    )
    reply_parser.add_argument("--model", "-m", help="Model to use")

    # export (single conversation)
    export_conv_parser = conv_subparsers.add_parser(
        "export", help="Export conversation to file"
    )
    export_conv_parser.add_argument("id", help="Conversation ID (full or partial)")
    export_conv_parser.add_argument("--db", "-d", required=True, help="Database path")
    export_conv_parser.add_argument(
        "--output", "-o", help="Output file path (default: stdout)"
    )
    export_conv_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "jsonl", "markdown"],
        help="Output format (default: inferred from extension or json)",
    )

    # info (detailed conversation info)
    info_parser = conv_subparsers.add_parser(
        "info", help="Show detailed conversation information"
    )
    info_parser.add_argument("id", help="Conversation ID (full or partial)")
    info_parser.add_argument("--db", "-d", required=True, help="Database path")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # summarize (LLM summary)
    summarize_parser = conv_subparsers.add_parser(
        "summarize", help="Generate LLM summary for conversation"
    )
    summarize_parser.add_argument("id", help="Conversation ID (full or partial)")
    summarize_parser.add_argument("--db", "-d", required=True, help="Database path")
    summarize_parser.add_argument(
        "--provider", "-p", default="ollama", help="LLM provider (default: ollama)"
    )
    summarize_parser.add_argument("--model", "-m", help="Model to use")
    summarize_parser.add_argument(
        "--path", type=int, help="Specific path index to summarize"
    )
    summarize_parser.add_argument(
        "--all-paths", action="store_true", help="Summarize all paths"
    )
    summarize_parser.add_argument(
        "--max-chars",
        type=int,
        default=10000,
        help="Max chars to send to LLM (default: 10000)",
    )
    summarize_parser.add_argument(
        "--save",
        "-s",
        action="store_true",
        help="Save summary to conversation metadata",
    )

    return conv_parser


def dispatch_conv_command(args):
    """Dispatch to appropriate conv subcommand"""
    commands = {
        "show": cmd_show,
        "tree": cmd_tree,
        "paths": cmd_paths,
        "star": cmd_star,
        "pin": cmd_pin,
        "archive": cmd_archive,
        "title": cmd_title,
        "delete": cmd_delete,
        "duplicate": cmd_duplicate,
        "tag": cmd_tag,
        "untag": cmd_untag,
        "say": cmd_say,
        "fork": cmd_fork,
        "reply": cmd_reply,
        "export": cmd_export_conv,
        "info": cmd_info,
        "summarize": cmd_summarize,
    }

    if hasattr(args, "conv_command") and args.conv_command:
        if args.conv_command in commands:
            return commands[args.conv_command](args)
        else:
            print(f"Unknown conv command: {args.conv_command}")
            return 1
    else:
        print(
            "Error: No conv command specified. Use 'ctk conv --help' for available commands."
        )
        return 1
