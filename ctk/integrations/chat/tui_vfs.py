"""VFS (Virtual Filesystem) command handlers extracted from ChatTUI."""


def ensure_vfs_navigator(db, vfs_navigator):
    """Lazy initialize VFS navigator, returning it.

    Args:
        db: ConversationDB instance
        vfs_navigator: Existing navigator or None

    Returns:
        VFSNavigator instance
    """
    if vfs_navigator is None:
        if not db:
            raise ValueError("Database required for VFS commands")
        from ctk.core.vfs_navigator import VFSNavigator

        vfs_navigator = VFSNavigator(db)
    return vfs_navigator


def handle_cd(db, vfs_navigator, vfs_cwd, args):
    """Handle /cd command.

    Args:
        db: ConversationDB instance
        vfs_navigator: VFSNavigator instance
        vfs_cwd: Current working directory string
        args: Raw argument string

    Returns:
        New vfs_cwd string, or original if unchanged
    """
    if not db:
        print("Error: Database required for VFS commands")
        return vfs_cwd

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)

    from ctk.core.vfs import VFSPathParser

    # Default to "/" if no args
    path = args.strip() if args else "/"

    # Try normal path parsing FIRST
    try:
        # Parse path
        vfs_path = VFSPathParser.parse(path, vfs_cwd)

        # Check if it's a directory
        if not vfs_path.is_directory:
            print(f"Error: Not a directory: {vfs_path.normalized_path}")
            return vfs_cwd

        # Special case: Try prefix resolution for ID-like paths
        path_segments = path.rstrip("/").split("/")
        last_segment = path_segments[-1] if path_segments else ""

        # Check if we're navigating to a conversation directory
        target_in_conv_dir = (
            vfs_path.normalized_path.startswith("/chats/")
            or vfs_path.normalized_path.startswith("/starred/")
            or vfs_path.normalized_path.startswith("/pinned/")
            or vfs_path.normalized_path.startswith("/archived/")
            or vfs_path.normalized_path.startswith("/tags/")
            or vfs_path.normalized_path.startswith("/recent/")
            or vfs_path.normalized_path.startswith("/source/")
            or vfs_path.normalized_path.startswith("/model/")
        )

        # Check if last segment looks like an ID (3+ chars, alphanumeric with dashes)
        looks_like_id = (
            len(last_segment) >= 3
            and last_segment.replace("-", "").replace("_", "").isalnum()
        )

        if target_in_conv_dir and looks_like_id:
            # Get the parent directory for prefix resolution
            parent_path = (
                "/".join(vfs_path.normalized_path.rstrip("/").split("/")[:-1]) or "/"
            )

            try:
                parent_vfs = VFSPathParser.parse(parent_path)
                resolved_id = vfs_navigator.resolve_prefix(last_segment, parent_vfs)

                if resolved_id:
                    new_cwd = VFSPathParser.parse(
                        f"{parent_path}/{resolved_id}"
                    ).normalized_path
                    print(f"Resolved '{last_segment}' to: {resolved_id}")
                    return new_cwd
            except ValueError as prefix_error:
                in_id_only_dir = parent_path in [
                    "/chats",
                    "/starred",
                    "/pinned",
                    "/archived",
                ]

                if in_id_only_dir:
                    print(f"Error: {prefix_error}")
                    return vfs_cwd

        # Change directory using normal parsing result
        return vfs_path.normalized_path

    except ValueError as parse_error:
        # Normal parsing failed - try prefix resolution for conversation IDs
        if (
            "/" not in path
            and len(path) >= 3
            and path.replace("-", "").replace("_", "").isalnum()
        ):
            try:
                current_path = VFSPathParser.parse(vfs_cwd)
                resolved_id = vfs_navigator.resolve_prefix(path, current_path)

                if resolved_id:
                    new_cwd = VFSPathParser.parse(resolved_id, vfs_cwd).normalized_path
                    print(f"Resolved '{path}' to: {resolved_id}")
                    return new_cwd
            except ValueError as prefix_error:
                in_id_only_dir = (
                    vfs_cwd in ["/chats", "/starred", "/pinned", "/archived"]
                    or vfs_cwd.startswith("/source/")
                    or vfs_cwd.startswith("/model/")
                    or vfs_cwd.startswith("/tags/")
                    or vfs_cwd.startswith("/recent/")
                )

                if in_id_only_dir:
                    print(f"Error: {prefix_error}")
                    return vfs_cwd

        # Show original parsing error
        print(f"Error: {parse_error}")
        return vfs_cwd
    except Exception as e:
        print(f"Error changing directory: {e}")
        return vfs_cwd


def handle_pwd(vfs_cwd):
    """Handle /pwd command."""
    print(vfs_cwd)


def handle_ls(db, vfs_navigator, vfs_cwd, args, console=None):
    """Handle /ls command.

    Args:
        db: ConversationDB instance
        vfs_navigator: VFSNavigator instance
        vfs_cwd: Current working directory string
        args: Raw argument string
        console: Rich Console instance for table output
    """
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)

    from rich.table import Table

    from ctk.core.vfs import VFSPathParser

    if console is None:
        from rich.console import Console

        console = Console()

    # Parse options
    show_long = False
    path = None

    if args:
        parts = args.strip().split()
        for part in parts:
            if part == "-l":
                show_long = True
            elif not path:
                path = part

    # Default to current directory
    if not path:
        path = vfs_cwd

    try:
        # Parse path
        vfs_path = VFSPathParser.parse(path, vfs_cwd)

        # Get directory listing
        entries = vfs_navigator.list_directory(vfs_path)

        if not entries:
            print("(empty)")
            return

        # Display entries
        if show_long:
            # Determine if we're listing message nodes
            is_message_listing = any(e.message_id is not None for e in entries)

            # Long format with table
            table = Table(show_header=True, header_style="bold")
            table.add_column("Name")
            table.add_column("Type")

            if is_message_listing:
                table.add_column("Role")
                table.add_column("Content Preview")
                table.add_column("Created")
            else:
                table.add_column("Title")
                table.add_column("Tags")
                table.add_column("Modified")

            for entry in sorted(entries, key=lambda e: (not e.is_directory, e.name)):
                entry_type = "dir" if entry.is_directory else "file"

                name = entry.name
                if entry.is_directory and not name.endswith("/"):
                    name += "/"

                if is_message_listing:
                    role = entry.role or "unknown"
                    preview = entry.content_preview or ""
                    created = (
                        entry.created_at.strftime("%Y-%m-%d %H:%M")
                        if entry.created_at
                        else ""
                    )

                    if entry.has_children:
                        name += " *"

                    table.add_row(name, entry_type, role, preview, created)
                else:
                    title = entry.title or ""
                    if title and len(title) > 40:
                        title = title[:37] + "..."
                    tags = ", ".join(entry.tags[:3]) if entry.tags else ""
                    if entry.tags and len(entry.tags) > 3:
                        tags += f" (+{len(entry.tags)-3})"

                    modified = ""
                    if entry.updated_at:
                        modified = entry.updated_at.strftime("%Y-%m-%d")

                    # Add flags
                    flags = []
                    if entry.starred:
                        flags.append("\u2b50")
                    if entry.pinned:
                        flags.append("\U0001f4cc")
                    if entry.archived:
                        flags.append("\U0001f4e6")

                    if flags:
                        name = f"{name} {' '.join(flags)}"

                    table.add_row(name, entry_type, title, tags, modified)

            console.print(table)
        else:
            # Simple format (like ls)
            dirs = [e for e in entries if e.is_directory]
            files = [e for e in entries if not e.is_directory]

            if dirs:
                dir_names = [f"{d.name}/" for d in sorted(dirs, key=lambda e: e.name)]
                print("  ".join(dir_names))

            if files:
                file_entries = []
                for f in sorted(files, key=lambda e: e.name):
                    name = f.name
                    if f.starred:
                        name += " \u2b50"
                    if f.pinned:
                        name += " \U0001f4cc"
                    if f.archived:
                        name += " \U0001f4e6"
                    file_entries.append(name)
                print("  ".join(file_entries))

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error listing directory: {e}")
        import traceback

        traceback.print_exc()


def handle_ln(db, vfs_navigator, vfs_cwd, args):
    """Handle /ln command - link (add tag)."""
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)
    from ctk.core.vfs import VFSPathParser

    parts = args.strip().split(None, 1)
    if len(parts) != 2:
        print("Usage: /ln <src> <dest>")
        print("Example: /ln /chats/abc123 /tags/physics/")
        return

    src_path_str, dest_path_str = parts

    try:
        src_path = VFSPathParser.parse(src_path_str, vfs_cwd)
        if src_path.is_directory:
            print(
                f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}"
            )
            return
        if not src_path.conversation_id:
            print(f"Error: Source is not a conversation: {src_path.normalized_path}")
            return

        dest_path = VFSPathParser.parse(dest_path_str, vfs_cwd)
        if not dest_path.is_directory:
            print(
                f"Error: Destination must be a directory: {dest_path.normalized_path}"
            )
            return

        if dest_path.path_type.value not in ["tags", "tag_dir"]:
            print(
                f"Error: Can only link to /tags/* directories (destination is read-only)"
            )
            return

        if dest_path.path_type.value == "tags":
            print("Error: Must specify a tag name, not just /tags/")
            return

        tag_name = dest_path.tag_path

        success = db.add_tags(src_path.conversation_id, [tag_name])
        if success:
            print(f"Linked {src_path.conversation_id} -> {tag_name}")
        else:
            print(f"Error: Failed to link conversation")

    except ValueError as e:
        print(f"Error: {e}")


def handle_cp(db, vfs_navigator, vfs_cwd, args):
    """Handle /cp command - copy (deep copy with new UUID)."""
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)
    from ctk.core.vfs import VFSPathParser

    parts = args.strip().split(None, 1)
    if len(parts) != 2:
        print("Usage: /cp <src> <dest>")
        print("Example: /cp /chats/abc123 /tags/physics/")
        return

    src_path_str, dest_path_str = parts

    try:
        src_path = VFSPathParser.parse(src_path_str, vfs_cwd)
        if src_path.is_directory:
            print(
                f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}"
            )
            return
        if not src_path.conversation_id:
            print(f"Error: Source is not a conversation: {src_path.normalized_path}")
            return

        dest_path = VFSPathParser.parse(dest_path_str, vfs_cwd)
        if not dest_path.is_directory:
            print(
                f"Error: Destination must be a directory: {dest_path.normalized_path}"
            )
            return

        if dest_path.path_type.value not in ["tags", "tag_dir"]:
            print(
                f"Error: Can only copy to /tags/* directories (destination is read-only)"
            )
            return

        new_id = db.duplicate_conversation(src_path.conversation_id)
        if not new_id:
            print(f"Error: Failed to duplicate conversation")
            return

        print(f"Copied conversation -> {new_id}")

        if dest_path.path_type.value == "tag_dir":
            tag_name = dest_path.tag_path
            db.add_tags(new_id, [tag_name])
            print(f"Tagged with: {tag_name}")

    except ValueError as e:
        print(f"Error: {e}")


def handle_mv(db, vfs_navigator, vfs_cwd, args):
    """Handle /mv command - move between tags."""
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)
    from ctk.core.vfs import VFSPathParser

    parts = args.strip().split(None, 1)
    if len(parts) != 2:
        print("Usage: /mv <src> <dest>")
        print("Example: /mv /tags/old/abc123 /tags/new/")
        return

    src_path_str, dest_path_str = parts

    try:
        src_path = VFSPathParser.parse(src_path_str, vfs_cwd)
        if src_path.is_directory:
            print(
                f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}"
            )
            return
        if not src_path.conversation_id:
            print(f"Error: Source is not a conversation: {src_path.normalized_path}")
            return

        if src_path.path_type.value != "tag_dir":
            print(
                f"Error: Can only move from /tags/* (source must be a tagged conversation)"
            )
            return

        dest_path = VFSPathParser.parse(dest_path_str, vfs_cwd)
        if not dest_path.is_directory:
            print(
                f"Error: Destination must be a directory: {dest_path.normalized_path}"
            )
            return

        if dest_path.path_type.value not in ["tags", "tag_dir"]:
            print(f"Error: Can only move to /tags/* directories")
            return

        old_tag = src_path.tag_path
        if dest_path.path_type.value == "tags":
            print("Error: Must specify a tag name, not just /tags/")
            return
        new_tag = dest_path.tag_path

        removed = db.remove_tag(src_path.conversation_id, old_tag)
        if removed:
            added = db.add_tags(src_path.conversation_id, [new_tag])
            if added:
                print(f"Moved {src_path.conversation_id}: {old_tag} -> {new_tag}")
            else:
                db.add_tags(src_path.conversation_id, [old_tag])
                print(f"Error: Failed to add new tag")
        else:
            print(f"Error: Failed to remove old tag")

    except ValueError as e:
        print(f"Error: {e}")


def handle_rm(db, vfs_navigator, vfs_cwd, args):
    """Handle /rm command - remove tag or delete conversation."""
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)
    from ctk.core.vfs import VFSPathParser

    path_str = args.strip()
    if not path_str:
        print("Usage: /rm <path>")
        print("Examples:")
        print("  /rm /tags/physics/abc123  - Remove tag from conversation")
        print("  /rm /chats/abc123         - Delete conversation (with confirmation)")
        return

    try:
        vfs_path = VFSPathParser.parse(path_str, vfs_cwd)

        if vfs_path.is_directory:
            print(f"Error: Cannot remove directory: {vfs_path.normalized_path}")
            print("(Directories are automatically cleaned up when empty)")
            return

        if not vfs_path.conversation_id:
            print(f"Error: Path is not a conversation: {vfs_path.normalized_path}")
            return

        if vfs_path.path_type.value == "chats":
            conv = db.get_conversation(vfs_path.conversation_id)
            if not conv:
                print(f"Error: Conversation not found: {vfs_path.conversation_id}")
                return

            title = conv.title or vfs_path.conversation_id
            print(f"WARNING: This will permanently delete conversation: {title}")
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm != "yes":
                print("Deletion cancelled")
                return

            success = db.delete_conversation(vfs_path.conversation_id)
            if success:
                print(f"Deleted conversation: {vfs_path.conversation_id}")
            else:
                print(f"Error: Failed to delete conversation")

        elif vfs_path.path_type.value == "tag_dir":
            tag_name = vfs_path.tag_path
            success = db.remove_tag(vfs_path.conversation_id, tag_name)
            if success:
                print(f"Removed tag '{tag_name}' from {vfs_path.conversation_id}")
            else:
                print(f"Error: Failed to remove tag")

        else:
            print(
                f"Error: Cannot remove from read-only directory: {vfs_path.normalized_path}"
            )

    except ValueError as e:
        print(f"Error: {e}")


def handle_mkdir(db, vfs_navigator, vfs_cwd, args):
    """Handle /mkdir command - create tag hierarchy (conceptual)."""
    if not db:
        print("Error: Database required for VFS commands")
        return

    vfs_navigator = ensure_vfs_navigator(db, vfs_navigator)
    from ctk.core.vfs import VFSPathParser

    path_str = args.strip()
    if not path_str:
        print("Usage: /mkdir <path>")
        print("Example: /mkdir /tags/research/ml/transformers/")
        return

    try:
        vfs_path = VFSPathParser.parse(path_str, vfs_cwd)

        if vfs_path.path_type.value not in ["tags", "tag_dir"]:
            print(f"Error: Can only create directories in /tags/*")
            return

        if vfs_path.path_type.value == "tags":
            print("Note: /tags/ already exists")
            return

        tag_path = vfs_path.tag_path
        print(f"Created tag hierarchy: {tag_path}")
        print(
            "Note: This is conceptual - the directory will appear when conversations are tagged"
        )

    except ValueError as e:
        print(f"Error: {e}")
