"""Slash command dispatcher for the TUI's chat input.

When the user types a line starting with ``/``, the chat input routes
it here instead of sending it to the LLM. Modeled after the slash
commands in claude-code: discoverable via ``/help``, no setup
required, doesn't add visual clutter to the bindings strip.

Each command is a small function that takes the App and the rest of
the line; it returns either ``None`` (handled silently) or a string
to display as a system note in the message view.

Adding a command: write a ``def cmd_foo(app, args) -> Optional[str]``
and register it in ``COMMANDS``. Keep the implementation small —
anything substantial belongs in app.py as an action method that the
slash command then calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from ctk.tui.app import CTKApp

logger = logging.getLogger(__name__)


@dataclass
class SlashCommand:
    """A single slash command definition."""

    name: str
    summary: str
    usage: str
    handler: Callable[["CTKApp", str], Optional[str]]


# Registry built at module import time. Order here drives the order in
# /help so put the most-used commands first.
_REGISTRY: List[SlashCommand] = []


def register(name: str, *, summary: str, usage: Optional[str] = None):
    """Decorator for adding a function to the command registry."""

    def decorate(fn: Callable[["CTKApp", str], Optional[str]]):
        _REGISTRY.append(
            SlashCommand(
                name=name,
                summary=summary,
                usage=usage or f"/{name}",
                handler=fn,
            )
        )
        return fn

    return decorate


def parse(line: str) -> Optional[Tuple[str, str]]:
    """Split a chat-input line into ``(name, args)``.

    Returns ``None`` if the line isn't a slash command, so the caller
    can route it to the LLM. Whitespace between the slash and the name
    is tolerated (so ``/ help`` still works).
    """
    stripped = line.lstrip()
    if not stripped.startswith("/"):
        return None
    body = stripped[1:].lstrip()
    if not body:
        return ("", "")  # bare slash → show help
    parts = body.split(maxsplit=1)
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return (name, args)


def commands() -> Dict[str, SlashCommand]:
    """Return the current registry as a name → command mapping."""
    return {c.name: c for c in _REGISTRY}


def dispatch(app: "CTKApp", line: str) -> Tuple[bool, Optional[str]]:
    """Route a chat-input line through the slash dispatcher.

    Returns:
        ``(handled, note)`` — ``handled`` is True when the line was a
        slash command (regardless of success), so the caller knows
        not to send it to the LLM. ``note`` is an optional human-
        readable result to display in the message view.
    """
    parsed = parse(line)
    if parsed is None:
        return (False, None)
    name, args = parsed
    if not name:
        return (True, _help_text())
    cmd = commands().get(name)
    if cmd is None:
        return (
            True,
            f"Unknown command: /{name}. Type /help for a list.",
        )
    try:
        return (True, cmd.handler(app, args))
    except Exception as exc:  # pragma: no cover — surface programmer errors
        logger.exception("Slash command /%s failed", name)
        return (True, f"/{name} failed: {exc}")


def _help_text() -> str:
    rows = ["Available commands:", ""]
    for cmd in _REGISTRY:
        rows.append(f"  {cmd.usage:<28} {cmd.summary}")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Command implementations
#
# Each command is intentionally small — anything that needs widget access
# or app state mutation calls into ``app`` rather than re-implementing.
# ---------------------------------------------------------------------------


@register("help", summary="Show this list", usage="/help")
def cmd_help(app: "CTKApp", args: str) -> str:
    return _help_text()


@register("mcp", summary="List MCP tool providers and their tools", usage="/mcp")
def cmd_mcp(app: "CTKApp", args: str) -> str:
    """Show every tool provider the model can call.

    Built-in tool providers (``ctk.builtin``, ``ctk.network``) are
    treated as always-available virtual MCP servers, alongside any
    real MCPs the user wires up later. The display mirrors what
    claude-code's ``/mcp`` shows: provider name, status, tool count,
    and each tool's name + one-line summary.
    """
    from ctk.core.tools_registry import iter_providers

    lines = []
    for provider in iter_providers():
        status = "ready" if provider.available else "unavailable"
        lines.append(
            f"[{status}] {provider.name}  ({len(provider.tools)} tool"
            f"{'s' if len(provider.tools) != 1 else ''})"
        )
        if provider.description:
            lines.append(f"  {provider.description}")
        for tool in provider.tools:
            summary = (tool.get("description") or "").strip().splitlines()[0]
            if len(summary) > 90:
                summary = summary[:87] + "…"
            lines.append(f"    • {tool['name']}  — {summary}")
        lines.append("")
    return "\n".join(lines).rstrip() or "No MCP providers registered."


@register("model", summary="Show or switch the chat model", usage="/model [name]")
def cmd_model(app: "CTKApp", args: str) -> str:
    if not args.strip():
        if app.provider is None:
            return "No provider configured."
        return f"Current model: {app.provider.model}"
    if app.provider is None:
        return "No provider configured; cannot switch models."
    new_model = args.strip()
    app.provider.model = new_model
    app._refresh_status()
    return f"Switched model to {new_model}."


@register("system", summary="Show or set the system prompt", usage="/system [text]")
def cmd_system(app: "CTKApp", args: str) -> Optional[str]:
    if not args.strip():
        if app._current_tree is None:
            return "No conversation loaded."
        existing = app._existing_system_prompt(app._current_tree)
        if existing is None:
            return "(no system prompt set)"
        return f"Current system prompt:\n{existing}"
    # Inline set — same effect as Ctrl+G + Save.
    if app._current_tree is None:
        # Lazily create the tree, mirroring action_edit_system_prompt.
        app.action_edit_system_prompt()
        return "Opened the system-prompt modal — paste your prompt there."
    app._set_system_prompt(app._current_tree, args)
    app._safe_save(app._current_tree)
    if app.main is not None:
        app.main.messages.show_conversation(app._current_tree)
    return "System prompt updated."


@register("title", summary="Rename the current conversation", usage="/title <text>")
def cmd_title(app: "CTKApp", args: str) -> Optional[str]:
    if app._current_tree is None:
        return "No conversation loaded."
    new_title = args.strip()
    if not new_title:
        return "Usage: /title <new title>"
    app._current_tree.title = new_title
    app._safe_save(app._current_tree)
    if app.main is not None:
        app.main.set_header(app._header_for(app._current_tree))
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"Renamed to: {new_title}"


def _toggle_flag(app: "CTKApp", flag: str) -> Optional[str]:
    """Shared helper for /star, /pin, /archive."""
    if app._current_tree is None:
        return f"No conversation loaded — nothing to {flag}."
    conv_id = app._current_tree.id
    method = getattr(app.db, f"{flag}_conversation", None)
    if method is None:
        return f"db has no {flag}_conversation method."
    # Read the current value from DB so we toggle correctly.
    meta_attr = f"{flag}red_at" if flag == "star" else f"{flag}ned_at" if flag == "pin" else "archived_at"
    is_set = bool(getattr(app._current_tree.metadata, meta_attr, None))
    method(conv_id, not is_set)
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"{flag.capitalize()}{'red' if flag == 'star' else 'ned' if flag == 'pin' else 'd'} conversation."


@register("star", summary="Toggle starred flag on current conversation", usage="/star")
def cmd_star(app: "CTKApp", args: str) -> Optional[str]:
    return _toggle_flag(app, "star")


@register("pin", summary="Toggle pinned flag on current conversation", usage="/pin")
def cmd_pin(app: "CTKApp", args: str) -> Optional[str]:
    return _toggle_flag(app, "pin")


@register("archive", summary="Toggle archived flag on current conversation", usage="/archive")
def cmd_archive(app: "CTKApp", args: str) -> Optional[str]:
    return _toggle_flag(app, "archive")


@register("tag", summary="Add tag(s) to the current conversation", usage="/tag <tag> [tag ...]")
def cmd_tag(app: "CTKApp", args: str) -> Optional[str]:
    if app._current_tree is None:
        return "No conversation loaded."
    tags = args.split()
    if not tags:
        return "Usage: /tag <tag> [tag ...]"
    app.db.add_tags(app._current_tree.id, tags)
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"Tagged: {', '.join(tags)}"


@register("untag", summary="Remove a tag from the current conversation", usage="/untag <tag>")
def cmd_untag(app: "CTKApp", args: str) -> Optional[str]:
    if app._current_tree is None:
        return "No conversation loaded."
    tag = args.strip()
    if not tag:
        return "Usage: /untag <tag>"
    app.db.remove_tag(app._current_tree.id, tag)
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"Untagged: {tag}"


@register("export", summary="Export current conversation to a file", usage="/export <path> [json|jsonl|md]")
def cmd_export(app: "CTKApp", args: str) -> Optional[str]:
    """Export the current conversation to a single file.

    The format is auto-detected from the path's extension if not
    given explicitly. Anything more elaborate (multi-conversation
    export, hugo trees, etc.) is what ``ctk export`` is for at the
    shell prompt.
    """
    import os

    if app._current_tree is None:
        return "No conversation loaded."
    parts = args.strip().split(maxsplit=1)
    if not parts:
        return "Usage: /export <path> [json|jsonl|md|html]"
    path = os.path.expanduser(parts[0])
    fmt = parts[1].strip().lower() if len(parts) > 1 else None
    if fmt is None:
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        fmt = {"md": "markdown"}.get(ext, ext) or "json"
    from ctk.core.plugin import registry

    exporter = registry.get_exporter(fmt)
    if exporter is None:
        return f"Unknown export format: {fmt}"
    try:
        exporter.export_to_file([app._current_tree], path)
    except Exception as exc:
        return f"Export failed: {exc}"
    return f"Exported to {path} ({fmt})."


@register("attach", summary="Attach a file as a system message (skip modal)", usage="/attach <path>")
def cmd_attach(app: "CTKApp", args: str) -> Optional[str]:
    path = args.strip()
    if not path:
        return "Usage: /attach <path>"
    # _on_file_attached handles validation, reading, and notification.
    target_id = app._current_tree.id if app._current_tree is not None else None
    app._on_file_attached(target_id, path)
    return None  # the helper already posts a Textual notification


@register("fork", summary="Fork at current path tail (no need to focus a message)", usage="/fork")
def cmd_fork(app: "CTKApp", args: str) -> Optional[str]:
    return _fork_or_branch_at_tail(app, preserve_tree=False)


@register("branch", summary="Branch at current path tail (preserve full tree)", usage="/branch")
def cmd_branch(app: "CTKApp", args: str) -> Optional[str]:
    return _fork_or_branch_at_tail(app, preserve_tree=True)


def _fork_or_branch_at_tail(app: "CTKApp", preserve_tree: bool) -> Optional[str]:
    """Like Ctrl+F / Ctrl+B but always at the path tail.

    The keyboard versions act on the focused message; for slash users
    we operate on the last message in the current path so they don't
    have to Tab around first.
    """
    if app._current_tree is None:
        return "No conversation loaded."
    path = app._current_tree.get_longest_path()
    if not path:
        return "Conversation is empty."
    target = path[-1]
    app._safe_save(app._current_tree)
    if not preserve_tree:
        app._truncate_tree_to_message(app._current_tree, target.id)
    import uuid as _uuid

    old_id = app._current_tree.id
    new_id = str(_uuid.uuid4())
    app._current_tree.id = new_id
    verb = "Branch" if preserve_tree else "Fork"
    app._current_tree.title = f"{verb} of {app._current_tree.title or '(untitled)'}"
    if app.main is not None:
        app.main.messages.show_conversation(app._current_tree)
        app.main.set_header(app._header_for(app._current_tree))
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"{verb}ed at tail — new id {new_id[:8]} (old: {old_id[:8]})"


@register("clone", summary="Duplicate the current conversation as a sibling", usage="/clone")
def cmd_clone(app: "CTKApp", args: str) -> Optional[str]:
    """Save a copy of the current conversation under a new id."""
    if app._current_tree is None:
        return "No conversation loaded."
    new_tree = app._current_tree.copy()
    new_tree.title = f"Copy of {app._current_tree.title or '(untitled)'}"
    app._safe_save(new_tree)
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"Cloned to new conversation {new_tree.id[:8]}."


@register("snapshot", summary="Save a dated snapshot of the current conversation", usage="/snapshot")
def cmd_snapshot(app: "CTKApp", args: str) -> Optional[str]:
    """Like /clone but prefixes the title with today's date."""
    from datetime import date

    if app._current_tree is None:
        return "No conversation loaded."
    new_tree = app._current_tree.copy()
    new_tree.title = (
        f"[{date.today().isoformat()}] {app._current_tree.title or '(untitled)'}"
    )
    app._safe_save(new_tree)
    if app.sidebar is not None:
        app.sidebar.refresh_list()
    return f"Snapshot saved as {new_tree.id[:8]}."


@register("delete", summary="Delete the current conversation entirely (confirm)", usage="/delete")
def cmd_delete(app: "CTKApp", args: str) -> Optional[str]:
    """Delete the loaded conversation. Requires --force to skip confirm."""
    from ctk.tui.modals import ConfirmModal

    if app._current_tree is None:
        return "No conversation loaded."
    target = app._current_tree
    title = target.title or "(untitled)"
    msg_count = len(target.message_map)

    def _on_confirm(confirmed: Optional[bool]) -> None:
        if not confirmed:
            return
        app.db.delete_conversation(target.id)
        app._current_tree = None
        if app.main is not None:
            app.main.messages.clear()
            app.main.set_header("(no conversation)")
        if app.sidebar is not None:
            app.sidebar.refresh_list()
        app.notify(f"Deleted conversation '{title}'.")

    app.push_screen(
        ConfirmModal(
            title=f"Delete conversation '{title}'?",
            detail=(
                f"Removes {msg_count} message{'s' if msg_count != 1 else ''} "
                "and all branches. Cannot be undone."
            ),
        ),
        _on_confirm,
    )
    return None  # Modal posts its own notification on completion.


@register("delete-subtree", summary="Delete focused message + descendants (confirm)", usage="/delete-subtree")
def cmd_delete_subtree(app: "CTKApp", args: str) -> Optional[str]:
    app.action_delete_subtree_at_focus()
    return None


@register("extract", summary="Copy focused subtree as a new conversation", usage="/extract")
def cmd_extract(app: "CTKApp", args: str) -> Optional[str]:
    app.action_extract_subtree_at_focus()
    return None


@register("detach", summary="Move focused subtree out as a new conversation (confirm)", usage="/detach")
def cmd_detach(app: "CTKApp", args: str) -> Optional[str]:
    """detach = extract + delete_subtree on the source.

    The composition is here rather than as a primitive so the modal +
    save dance only happens once.
    """
    from ctk.tui.modals import ConfirmModal

    if app._current_tree is None:
        return "No conversation loaded."
    target_id = app._focused_message_id()
    if target_id is None:
        return "Focus a message first (Tab/Shift+Tab to move between messages)."
    if target_id not in app._current_tree.message_map:
        return "Focused message no longer exists."
    tree = app._current_tree
    count = 1 + len(tree.descendants_of(target_id))

    def _on_confirm(confirmed: Optional[bool]) -> None:
        if not confirmed:
            return
        new_tree = tree.copy_subtree(target_id)
        new_tree.title = f"Detached from {tree.title or '(untitled)'}"
        tree.delete_subtree(target_id)
        app._safe_save(new_tree)
        app._safe_save(tree)
        if app.main is not None:
            app.main.messages.show_conversation(tree)
        if app.sidebar is not None:
            app.sidebar.refresh_list()
        app.notify(
            f"Detached {count} message{'s' if count != 1 else ''} "
            f"→ new conversation {new_tree.id[:8]}"
        )

    app.push_screen(
        ConfirmModal(
            title="Detach subtree?",
            detail=(
                f"Moves {count} message{'s' if count != 1 else ''} from "
                f"{target_id[:8]} into a new conversation, removing them "
                "from the source. Cannot be undone."
            ),
        ),
        _on_confirm,
    )
    return None


@register("promote", summary="Make focused message's path the only path (confirm)", usage="/promote")
def cmd_promote(app: "CTKApp", args: str) -> Optional[str]:
    app.action_promote_path_at_focus()
    return None


@register("graft", summary="Attach another conversation under focused message", usage="/graft <conv-id-prefix>")
def cmd_graft(app: "CTKApp", args: str) -> Optional[str]:
    """Attach a copy of another conversation under the focused message.

    The donor is identified by its conversation id (or a unique prefix).
    All messages get fresh ids in the target tree, so there's no risk
    of collision.
    """
    if app._current_tree is None:
        return "No conversation loaded."
    target_id = app._focused_message_id()
    if target_id is None:
        return "Focus a message first (Tab/Shift+Tab to move between messages)."
    if target_id not in app._current_tree.message_map:
        return "Focused message no longer exists."
    arg = args.strip()
    if not arg:
        return "Usage: /graft <conv-id-or-prefix>"
    resolved = app.db.resolve_identifier(arg)
    if resolved is None:
        return f"Could not resolve '{arg}' to a conversation."
    donor_id, _ = resolved
    if donor_id == app._current_tree.id:
        return "Cannot graft a conversation into itself."
    donor = app.db.load_conversation(donor_id)
    if donor is None:
        return f"Could not load donor conversation {donor_id[:8]}."
    added = app._current_tree.graft(target_id, donor)
    app._safe_save(app._current_tree)
    if app.main is not None:
        app.main.messages.show_conversation(app._current_tree)
    return (
        f"Grafted {added} message{'s' if added != 1 else ''} "
        f"from {donor_id[:8]} under {target_id[:8]}."
    )


@register("clear", summary="Reset to a new empty conversation", usage="/clear")
def cmd_clear(app: "CTKApp", args: str) -> Optional[str]:
    app.action_new_conversation()
    return None


@register("sql", summary="Run a read-only SQL query on the database", usage="/sql <query>")
def cmd_sql(app: "CTKApp", args: str) -> str:
    """Execute a read-only SQL query and return the rows as text.

    Opens the underlying SQLite file in read-only URI mode (same
    pattern as ``ctk sql`` at the shell prompt) so the query can't
    mutate the database even if it tries.
    """
    import sqlite3

    query = args.strip()
    if not query:
        return "Usage: /sql <query>"
    db_file = getattr(app.db, "db_path", None)
    if db_file is None or str(db_file) == ":memory:":
        return "Cannot run /sql on an in-memory database."
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        return f"Could not open database read-only: {exc}"
    try:
        cur = conn.execute(query)
        rows = cur.fetchmany(50)
        headers = [d[0] for d in cur.description] if cur.description else []
    except sqlite3.Error as exc:
        return f"SQL error: {exc}"
    finally:
        conn.close()
    if not rows:
        return "(no rows)"
    out = ["\t".join(headers)] if headers else []
    for row in rows:
        out.append("\t".join(str(v)[:60] for v in row))
    return "\n".join(out)


@register("quit", summary="Exit the TUI", usage="/quit")
def cmd_quit(app: "CTKApp", args: str) -> Optional[str]:
    app.exit()
    return None
