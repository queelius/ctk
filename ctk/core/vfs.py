"""
Virtual Filesystem for conversation navigation.

Provides a POSIX-like filesystem interface for navigating conversations
using hierarchical tags, filters, and metadata views.
"""

from typing import Optional, List, Tuple, Dict, Any
from pathlib import PurePosixPath
from dataclasses import dataclass
from enum import Enum
import re


class PathType(Enum):
    """Type of filesystem path"""
    ROOT = "root"
    CHATS = "chats"              # /chats/ - flat list
    TAGS = "tags"                # /tags/* - hierarchical tags (mutable)
    STARRED = "starred"          # /starred/ - starred conversations (read-only)
    PINNED = "pinned"            # /pinned/ - pinned conversations (read-only)
    ARCHIVED = "archived"        # /archived/ - archived conversations (read-only)
    RECENT = "recent"            # /recent/* - time-based views (read-only)
    SOURCE = "source"            # /source/* - grouped by source (read-only)
    MODEL = "model"              # /model/* - grouped by model (read-only)
    VIEWS = "views"              # /views/ - named views
    VIEW_DIR = "view_dir"        # /views/<name>/ - contents of a view
    CONVERSATION = "conversation"  # Conversation reference (symlink-like)
    CONVERSATION_ROOT = "conversation_root"  # Conversation as directory (e.g., /chats/abc123/)
    MESSAGE_NODE = "message_node"  # Message node in tree (e.g., /chats/abc123/m5/)
    MESSAGE_FILE = "message_file"  # Message metadata file (e.g., /chats/abc123/m5/text)
    TAG_DIR = "tag_dir"          # Tag directory (e.g., /tags/physics/)


@dataclass
class VFSPath:
    """
    Parsed virtual filesystem path.

    Examples:
        /chats/abc123 -> type=CONVERSATION, segments=['chats', 'abc123']
        /chats/abc123/ -> type=CONVERSATION_ROOT, segments=['chats', 'abc123']
        /chats/abc123/m5/ -> type=MESSAGE_NODE, message_path=['m5']
        /chats/abc123/m5/m10/ -> type=MESSAGE_NODE, message_path=['m5', 'm10']
        /chats/abc123/m5/text -> type=MESSAGE_FILE, message_path=['m5'], file_name='text'
        /tags/physics/simulator -> type=TAG_DIR, segments=['tags', 'physics', 'simulator']
        /starred/ -> type=STARRED, segments=['starred']
        /views/ -> type=VIEWS, segments=['views']
        /views/my-view/ -> type=VIEW_DIR, segments=['views', 'my-view'], view_name='my-view'
    """
    raw_path: str
    normalized_path: str
    segments: List[str]
    path_type: PathType
    conversation_id: Optional[str] = None
    tag_path: Optional[str] = None  # For tags: "physics/simulator"
    view_name: Optional[str] = None  # For views: "my-view"
    message_path: Optional[List[str]] = None  # For message nodes: ['m5', 'm10']
    file_name: Optional[str] = None  # For message files: 'text', 'role', 'timestamp', 'id'
    is_directory: bool = True

    def __str__(self):
        return self.normalized_path


class VFSPathParser:
    """Parser for virtual filesystem paths"""

    # Metadata file names
    METADATA_FILES = {'text', 'role', 'timestamp', 'id'}

    # Valid conversation ID pattern (hash-like strings)
    CONV_ID_PATTERN = re.compile(r'^[a-f0-9\-_]+$', re.IGNORECASE)

    # Message node pattern (m followed by digits)
    MESSAGE_NODE_PATTERN = re.compile(r'^m\d+$', re.IGNORECASE)

    @staticmethod
    def is_valid_conversation_id(segment: str) -> bool:
        """Check if segment looks like a conversation ID"""
        # Must be alphanumeric with dashes/underscores, reasonable length
        if len(segment) < 5 or len(segment) > 100:
            return False
        return bool(VFSPathParser.CONV_ID_PATTERN.match(segment))

    @staticmethod
    def is_message_node(segment: str) -> bool:
        """Check if segment is a message node (m1, m2, m100, etc.)"""
        return bool(VFSPathParser.MESSAGE_NODE_PATTERN.match(segment))

    @staticmethod
    def parse_message_segments(segments: List[str], normalized: str) -> tuple:
        """
        Parse message segments, detecting metadata files

        Args:
            segments: List of path segments after conversation ID
            normalized: Normalized full path for error messages

        Returns:
            Tuple of (path_type, message_path, file_name)
            where path_type is MESSAGE_NODE or MESSAGE_FILE
        """
        if not segments:
            return (PathType.MESSAGE_NODE, [], None)

        # Check if last segment is a metadata file
        if segments[-1] in VFSPathParser.METADATA_FILES:
            # This is a metadata file
            message_segments = segments[:-1]
            file_name = segments[-1]

            # Verify all message segments are valid message nodes
            for seg in message_segments:
                if not VFSPathParser.is_message_node(seg):
                    raise ValueError(f"Invalid message node: {seg} in path {normalized}")

            return (PathType.MESSAGE_FILE, message_segments, file_name)
        else:
            # All segments are message nodes
            for seg in segments:
                if not VFSPathParser.is_message_node(seg):
                    raise ValueError(f"Invalid message node: {seg} in path {normalized}")

            return (PathType.MESSAGE_NODE, segments, None)

    @staticmethod
    def normalize_path(path: str, current_dir: str = "/") -> str:
        """
        Normalize a path (resolve . and .., make absolute).

        Args:
            path: Path to normalize (absolute or relative)
            current_dir: Current working directory (for relative paths)

        Returns:
            Normalized absolute path
        """
        # Handle absolute vs relative
        if path.startswith('/'):
            base_path = PurePosixPath('/')
            rel_path = path[1:]  # Remove leading /
        else:
            # Relative path - join with current dir
            base_path = PurePosixPath(current_dir)
            rel_path = path

        # Join and resolve
        if rel_path:
            full_path = base_path / rel_path
        else:
            full_path = base_path

        # Resolve . and .. completely
        parts = []
        for part in full_path.parts:
            if part == '..':
                if parts and parts[-1] != '/':
                    parts.pop()
            elif part == '.':
                continue
            else:
                parts.append(part)

        # Reconstruct path
        if not parts or parts == ['/']:
            return '/'

        # Filter out the root '/' from parts if present
        filtered_parts = [p for p in parts if p != '/']

        # Join parts, ensuring leading /
        if filtered_parts:
            normalized = '/' + '/'.join(filtered_parts)
        else:
            normalized = '/'

        return normalized

    @staticmethod
    def parse(path: str, current_dir: str = "/") -> VFSPath:
        """
        Parse a filesystem path.

        Args:
            path: Path to parse (absolute or relative)
            current_dir: Current working directory

        Returns:
            VFSPath object
        """
        # Normalize path
        normalized = VFSPathParser.normalize_path(path, current_dir)

        # Split into segments (filter empty)
        segments = [s for s in normalized.split('/') if s]

        # Root directory
        if not segments:
            return VFSPath(
                raw_path=path,
                normalized_path="/",
                segments=[],
                path_type=PathType.ROOT,
                is_directory=True
            )

        # Determine path type based on first segment
        first = segments[0]

        # /chats/
        if first == "chats":
            if len(segments) == 1:
                # /chats/ directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CHATS,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /chats/<id> - always treat as navigable directory
                conv_id = segments[1]
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=conv_id,
                    is_directory=True
                )
            else:
                # /chats/abc123/m5/m10/... - check if these are message nodes or metadata files
                conv_id = segments[1]
                remaining_segments = segments[2:]

                # Parse message segments with metadata file detection
                path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                    remaining_segments, normalized
                )

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=path_type,
                    conversation_id=conv_id,
                    message_path=message_path,
                    file_name=file_name,
                    is_directory=(path_type == PathType.MESSAGE_NODE)
                )

        # /tags/*
        elif first == "tags":
            if len(segments) == 1:
                # /tags/ directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.TAGS,
                    is_directory=True
                )
            else:
                # Could be:
                # - /tags/physics/simulator (tag directory)
                # - /tags/physics/abc123 (conversation in tag)
                # - /tags/physics/abc123/m5 (message node in tagged conversation)

                # Find where conversation ID is (if any)
                conv_idx = None
                for i in range(1, len(segments)):
                    if VFSPathParser.is_valid_conversation_id(segments[i]):
                        conv_idx = i
                        break

                if conv_idx is None:
                    # No conversation ID found - this is a tag directory
                    tag_path = '/'.join(segments[1:])
                    return VFSPath(
                        raw_path=path,
                        normalized_path=normalized,
                        segments=segments,
                        path_type=PathType.TAG_DIR,
                        tag_path=tag_path,
                        is_directory=True
                    )
                else:
                    # Found conversation ID
                    conv_id = segments[conv_idx]
                    tag_path = '/'.join(segments[1:conv_idx]) if conv_idx > 1 else ""

                    # Check if there are message nodes after conv_id
                    if conv_idx == len(segments) - 1:
                        # /tags/physics/abc123 - conversation as directory
                        return VFSPath(
                            raw_path=path,
                            normalized_path=normalized,
                            segments=segments,
                            path_type=PathType.CONVERSATION_ROOT,
                            conversation_id=conv_id,
                            tag_path=tag_path,
                            is_directory=True
                        )
                    else:
                        # /tags/physics/abc123/m5/... - message nodes or metadata files
                        remaining_segments = segments[conv_idx + 1:]

                        # Parse message segments with metadata file detection
                        path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                            remaining_segments, normalized
                        )

                        return VFSPath(
                            raw_path=path,
                            normalized_path=normalized,
                            segments=segments,
                            path_type=path_type,
                            conversation_id=conv_id,
                            tag_path=tag_path,
                            message_path=message_path,
                            file_name=file_name,
                            is_directory=(path_type == PathType.MESSAGE_NODE)
                        )

        # /starred/
        elif first == "starred":
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.STARRED,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /starred/<id> - conversation as directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=segments[1],
                    is_directory=True
                )
            else:
                # /starred/<id>/m1/m2/... - message nodes or metadata files
                conv_id = segments[1]
                remaining_segments = segments[2:]

                # Parse message segments with metadata file detection
                path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                    remaining_segments, normalized
                )

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=path_type,
                    conversation_id=conv_id,
                    message_path=message_path,
                    file_name=file_name,
                    is_directory=(path_type == PathType.MESSAGE_NODE)
                )

        # /pinned/
        elif first == "pinned":
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.PINNED,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /pinned/<id> - conversation as directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=segments[1],
                    is_directory=True
                )
            else:
                # /pinned/<id>/m1/m2/... - message nodes or metadata files
                conv_id = segments[1]
                remaining_segments = segments[2:]

                # Parse message segments with metadata file detection
                path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                    remaining_segments, normalized
                )

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=path_type,
                    conversation_id=conv_id,
                    message_path=message_path,
                    file_name=file_name,
                    is_directory=(path_type == PathType.MESSAGE_NODE)
                )

        # /archived/
        elif first == "archived":
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.ARCHIVED,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /archived/<id> - conversation as directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=segments[1],
                    is_directory=True
                )
            else:
                # /archived/<id>/m1/m2/... - message nodes or metadata files
                conv_id = segments[1]
                remaining_segments = segments[2:]

                # Parse message segments with metadata file detection
                path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                    remaining_segments, normalized
                )

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=path_type,
                    conversation_id=conv_id,
                    message_path=message_path,
                    file_name=file_name,
                    is_directory=(path_type == PathType.MESSAGE_NODE)
                )

        # /recent/*
        elif first == "recent":
            # /recent/, /recent/today/, /recent/this-week/, etc.
            # Also handles /recent/today/abc123/m1/m2/... (message nodes)
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.RECENT,
                    is_directory=True
                )
            else:
                # Find conversation ID in path (if any)
                conv_idx = None
                for i in range(1, len(segments)):
                    if VFSPathParser.is_valid_conversation_id(segments[i]):
                        conv_idx = i
                        break

                if conv_idx is None:
                    # No conversation ID - must be time period directory
                    return VFSPath(
                        raw_path=path,
                        normalized_path=normalized,
                        segments=segments,
                        path_type=PathType.RECENT,
                        is_directory=True
                    )
                elif conv_idx == len(segments) - 1:
                    # Conversation ID is last segment - conversation root
                    return VFSPath(
                        raw_path=path,
                        normalized_path=normalized,
                        segments=segments,
                        path_type=PathType.CONVERSATION_ROOT,
                        conversation_id=segments[conv_idx],
                        is_directory=True
                    )
                else:
                    # Message nodes after conversation ID
                    conv_id = segments[conv_idx]
                    message_segments = segments[conv_idx + 1:]

                    # Verify all are message nodes
                    for seg in message_segments:
                        if not VFSPathParser.is_message_node(seg):
                            raise ValueError(f"Invalid message node: {seg} in path {normalized}")

                    return VFSPath(
                        raw_path=path,
                        normalized_path=normalized,
                        segments=segments,
                        path_type=PathType.MESSAGE_NODE,
                        conversation_id=conv_id,
                        message_path=message_segments,
                        is_directory=True
                    )

        # /source/*
        elif first == "source":
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.SOURCE,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /source/openai/
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.SOURCE,
                    is_directory=True
                )
            elif len(segments) == 3:
                # /source/openai/abc123 - conversation as directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=segments[2],
                    is_directory=True
                )
            else:
                # /source/openai/abc123/m1/m2/... - message nodes
                conv_id = segments[2]
                message_segments = segments[3:]

                # Verify all are message nodes
                for seg in message_segments:
                    if not VFSPathParser.is_message_node(seg):
                        raise ValueError(f"Invalid message node: {seg} in path {normalized}")

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.MESSAGE_NODE,
                    conversation_id=conv_id,
                    message_path=message_segments,
                    is_directory=True
                )

        # /model/*
        elif first == "model":
            if len(segments) == 1:
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.MODEL,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /model/gpt-4/
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.MODEL,
                    is_directory=True
                )
            elif len(segments) == 3:
                # /model/gpt-4/abc123 - conversation as directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    conversation_id=segments[2],
                    is_directory=True
                )
            else:
                # /model/gpt-4/abc123/m1/m2/... - message nodes
                conv_id = segments[2]
                message_segments = segments[3:]

                # Verify all are message nodes
                for seg in message_segments:
                    if not VFSPathParser.is_message_node(seg):
                        raise ValueError(f"Invalid message node: {seg} in path {normalized}")

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.MESSAGE_NODE,
                    conversation_id=conv_id,
                    message_path=message_segments,
                    is_directory=True
                )

        # /views/*
        elif first == "views":
            if len(segments) == 1:
                # /views/ directory
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.VIEWS,
                    is_directory=True
                )
            elif len(segments) == 2:
                # /views/<name>/ - view directory listing conversations
                view_name = segments[1]
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.VIEW_DIR,
                    view_name=view_name,
                    is_directory=True
                )
            elif len(segments) == 3:
                # /views/<name>/<id> - conversation as directory
                view_name = segments[1]
                conv_id = segments[2]
                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=PathType.CONVERSATION_ROOT,
                    view_name=view_name,
                    conversation_id=conv_id,
                    is_directory=True
                )
            else:
                # /views/<name>/<id>/m1/m2/... - message nodes or metadata files
                view_name = segments[1]
                conv_id = segments[2]
                remaining_segments = segments[3:]

                # Parse message segments with metadata file detection
                path_type, message_path, file_name = VFSPathParser.parse_message_segments(
                    remaining_segments, normalized
                )

                return VFSPath(
                    raw_path=path,
                    normalized_path=normalized,
                    segments=segments,
                    path_type=path_type,
                    view_name=view_name,
                    conversation_id=conv_id,
                    message_path=message_path,
                    file_name=file_name,
                    is_directory=(path_type == PathType.MESSAGE_NODE)
                )

        else:
            raise ValueError(f"Unknown filesystem root: /{first}")

    @staticmethod
    def is_read_only(vfs_path: VFSPath) -> bool:
        """Check if path is in a read-only directory"""
        read_only_types = {
            PathType.CHATS,  # Can't cp/mv into /chats (flat)
            PathType.STARRED,
            PathType.PINNED,
            PathType.ARCHIVED,
            PathType.RECENT,
            PathType.SOURCE,
            PathType.MODEL
        }

        # Check first segment
        if not vfs_path.segments:
            return True  # Root is read-only

        first = vfs_path.segments[0]

        # /tags/* is mutable
        if first == "tags":
            return False

        # Everything else is read-only for modifications
        return True

    @staticmethod
    def can_delete(vfs_path: VFSPath) -> bool:
        """Check if path can be deleted"""
        # Can delete from /chats/ (deletes conversation)
        if vfs_path.path_type == PathType.CONVERSATION and vfs_path.segments[0] == "chats":
            return True

        # Can delete from /tags/* (removes tag)
        if vfs_path.segments and vfs_path.segments[0] == "tags":
            return True

        return False
