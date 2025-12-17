"""
Hugo exporter for CTK conversations

Exports conversations as Hugo page bundles for static site generation.
Each conversation becomes a directory with index.md and associated media.
"""

import os
import re
import shutil
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from ctk.core.plugin import ExporterPlugin
from ctk.core.models import ConversationTree, Message, MessageRole


class HugoExporter(ExporterPlugin):
    """Export conversations as Hugo page bundles"""

    name = "hugo"
    description = "Export conversations as Hugo page bundles for static site generation"
    version = "1.0.0"

    def validate(self, data: Any) -> bool:
        """Hugo is an export-only format"""
        return False

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations - returns count of exported conversations"""
        # This method is less useful for Hugo since we create directories
        # But we implement it for interface compliance
        return len(conversations)

    def export_to_file(self, conversations: List[ConversationTree],
                       file_path: str, **kwargs) -> None:
        """
        Export conversations as Hugo page bundles.

        Args:
            file_path: Output directory (e.g., content/conversations/)
            conversations: List of conversations to export
            **kwargs: Additional options:
                - db_dir: Source database directory for media files
                - section: Hugo section name (default: "conversations")
                - path_selection: How to handle branching (longest, first, last)
                - include_draft: Mark as draft (default: False)
                - date_prefix: Include date in directory name (default: True)
        """
        db_dir = kwargs.get('db_dir')
        section = kwargs.get('section', 'conversations')
        path_selection = kwargs.get('path_selection', 'longest')
        include_draft = kwargs.get('include_draft', False)
        date_prefix = kwargs.get('date_prefix', True)

        # Create output directory
        output_dir = Path(file_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        exported_count = 0
        for conv in conversations:
            try:
                self._export_conversation(
                    conv, output_dir,
                    db_dir=db_dir,
                    path_selection=path_selection,
                    include_draft=include_draft,
                    date_prefix=date_prefix
                )
                exported_count += 1
            except Exception as e:
                import sys
                print(f"Warning: Failed to export conversation {conv.id}: {e}", file=sys.stderr)

        print(f"Exported {exported_count} conversation(s) to {output_dir}")

    def _export_conversation(
        self,
        conv: ConversationTree,
        output_dir: Path,
        db_dir: Optional[str] = None,
        path_selection: str = "longest",
        include_draft: bool = False,
        date_prefix: bool = True
    ) -> None:
        """Export a single conversation as a Hugo page bundle."""

        # Generate slug from title
        slug = self._generate_slug(conv.title or "untitled", conv.id)

        # Add date prefix if requested
        if date_prefix and conv.metadata.created_at:
            date_str = conv.metadata.created_at.strftime("%Y-%m-%d")
            bundle_name = f"{date_str}-{slug}"
        else:
            bundle_name = slug

        # Create page bundle directory
        bundle_dir = output_dir / bundle_name
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Collect images from conversation
        images = self._collect_images(conv)

        # Copy images to bundle
        image_map = {}  # Maps original URL to new filename
        if images and db_dir:
            images_dir = bundle_dir / "images"
            images_dir.mkdir(exist_ok=True)
            image_map = self._copy_images(images, db_dir, images_dir)

        # Generate frontmatter
        frontmatter = self._generate_frontmatter(conv, include_draft)

        # Generate markdown content
        content = self._generate_content(conv, path_selection, image_map)

        # Write index.md
        index_path = bundle_dir / "index.md"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write("---\n")
            f.write(frontmatter)
            f.write("---\n\n")
            f.write(content)

    def _generate_slug(self, title: str, conv_id: str) -> str:
        """Generate URL-safe slug from title."""
        # Convert to lowercase and replace spaces
        slug = title.lower().strip()
        # Remove special characters, keep alphanumeric and spaces
        slug = re.sub(r'[^\w\s-]', '', slug)
        # Replace spaces with hyphens
        slug = re.sub(r'[\s_]+', '-', slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r'-+', '-', slug)
        # Trim to reasonable length
        slug = slug[:50].rstrip('-')

        # Add short ID suffix for uniqueness
        short_id = conv_id[:8] if conv_id else ""
        if slug:
            return f"{slug}-{short_id}"
        return short_id

    def _generate_frontmatter(self, conv: ConversationTree, include_draft: bool) -> str:
        """Generate YAML frontmatter for Hugo."""
        lines = []

        # Title
        title = conv.title or "Untitled Conversation"
        # Escape quotes in title
        title = title.replace('"', '\\"')
        lines.append(f'title: "{title}"')

        # Dates
        if conv.metadata.created_at:
            lines.append(f'date: {conv.metadata.created_at.isoformat()}')
        if conv.metadata.updated_at:
            lines.append(f'lastmod: {conv.metadata.updated_at.isoformat()}')

        # Draft status
        if include_draft:
            lines.append('draft: true')
        else:
            lines.append('draft: false')

        # Tags from metadata
        if conv.metadata.tags:
            tags_str = ', '.join(f'"{t}"' for t in conv.metadata.tags)
            lines.append(f'tags: [{tags_str}]')

        # Categories - use source as category
        if conv.metadata.source:
            lines.append(f'categories: ["{conv.metadata.source}"]')

        # Custom params for CTK metadata
        lines.append('params:')
        lines.append(f'  conversation_id: "{conv.id}"')

        if conv.metadata.source:
            lines.append(f'  source: "{conv.metadata.source}"')
        if conv.metadata.model:
            lines.append(f'  model: "{conv.metadata.model}"')

        # Message count
        lines.append(f'  message_count: {len(conv.message_map)}')

        # Organization flags
        if conv.metadata.starred_at:
            lines.append('  starred: true')
        if conv.metadata.pinned_at:
            lines.append('  pinned: true')
        if conv.metadata.archived_at:
            lines.append('  archived: true')

        return '\n'.join(lines) + '\n'

    def _generate_content(
        self,
        conv: ConversationTree,
        path_selection: str,
        image_map: Dict[str, str]
    ) -> str:
        """Generate markdown content from conversation."""
        lines = []

        # Get messages in order
        if path_selection == "longest":
            path = conv.get_longest_path()
        elif path_selection == "first":
            paths = conv.get_all_paths()
            path = paths[0] if paths else []
        elif path_selection == "last":
            paths = conv.get_all_paths()
            path = paths[-1] if paths else []
        else:
            path = conv.get_longest_path()

        # Check if conversation has branches
        has_branches = len(conv.get_all_paths()) > 1
        if has_branches:
            lines.append(f"*This conversation has multiple branches. Showing the {path_selection} path.*\n")

        for msg in path:
            # Role header
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            role_display = self._format_role(role)
            lines.append(f"## {role_display}\n")

            # Message content
            content = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)

            # Replace image URLs with Hugo-relative paths
            content = self._replace_image_urls(content, image_map)

            lines.append(content)
            lines.append("")  # Blank line after message

            # Handle images in message
            if hasattr(msg.content, 'images') and msg.content.images:
                for img in msg.content.images:
                    img_ref = img.url or img.path
                    if img_ref and img_ref in image_map:
                        new_path = image_map[img_ref]
                        caption = img.caption or ""
                        if caption:
                            lines.append(f"![{caption}]({new_path})")
                        else:
                            lines.append(f"![]({new_path})")
                        lines.append("")

        return '\n'.join(lines)

    def _format_role(self, role: str) -> str:
        """Format role for display."""
        role_map = {
            'user': 'User',
            'assistant': 'Assistant',
            'system': 'System',
            'tool': 'Tool',
            'human': 'User',
            'ai': 'Assistant',
        }
        return role_map.get(role.lower(), role.capitalize())

    def _collect_images(self, conv: ConversationTree) -> List[Dict[str, Any]]:
        """Collect all images from a conversation."""
        images = []
        for msg in conv.message_map.values():
            if hasattr(msg.content, 'images') and msg.content.images:
                for img in msg.content.images:
                    img_ref = img.url or img.path
                    if img_ref:
                        images.append({
                            'url': img_ref,
                            'mime_type': img.mime_type,
                            'caption': img.caption
                        })
        return images

    def _copy_images(
        self,
        images: List[Dict[str, Any]],
        db_dir: str,
        images_dir: Path
    ) -> Dict[str, str]:
        """Copy images to bundle and return mapping of old to new paths."""
        image_map = {}
        db_path = Path(db_dir)

        for img in images:
            img_ref = img['url']

            # Determine source path
            if img_ref.startswith('media/'):
                src_path = db_path / img_ref
            elif '/' not in img_ref and '\\' not in img_ref:
                src_path = db_path / 'media' / img_ref
            else:
                src_path = db_path / img_ref

            if src_path.exists():
                # Get filename
                filename = src_path.name
                dest_path = images_dir / filename

                # Copy file
                shutil.copy2(src_path, dest_path)

                # Map original URL to Hugo-relative path
                image_map[img_ref] = f"images/{filename}"

        return image_map

    def _replace_image_urls(self, content: str, image_map: Dict[str, str]) -> str:
        """Replace image URLs in content with Hugo-relative paths."""
        for old_url, new_path in image_map.items():
            # Replace various forms the URL might appear
            content = content.replace(old_url, new_path)
            # Also try with media/ prefix removed
            if old_url.startswith('media/'):
                content = content.replace(old_url[6:], new_path)
        return content


# Register the exporter
exporter = HugoExporter()
