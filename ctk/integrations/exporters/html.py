"""
HTML Exporter - Interactive browser-based conversation viewer with localStorage
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from ctk.core.models import ConversationTree
from ctk.core.plugin import ExporterPlugin


class HTMLExporter(ExporterPlugin):
    """Export conversations to interactive HTML app with localStorage features"""

    name = "html"
    description = "Export to interactive HTML app with annotations, bookmarks, and more"
    version = "2.0.0"

    def validate(self, data: Any) -> bool:
        """HTML is an export-only format"""
        return False

    def export_to_file(self, conversations: List[ConversationTree],
                      file_path: str, **kwargs) -> None:
        """
        Export to file(s)

        Options:
        - embed=True (default): Single HTML file with all data embedded (including base64 images)
        - embed=False: Separate index.html + conversations.jsonl + media/ (requires web server)
        - media_dir: Put media in specified directory, embed conversation data in HTML
        """
        embed = kwargs.pop('embed', True)  # Default to embedded for better UX
        db_dir = kwargs.pop('db_dir', None)  # Database directory for media files
        media_dir = kwargs.pop('media_dir', None)  # Optional: output media to separate directory

        if media_dir:
            # Hybrid mode: embed conversation data but put media in separate directory
            import shutil
            from pathlib import Path

            # Determine output directory and paths
            if file_path.endswith('.html'):
                output_dir = os.path.dirname(file_path) or '.'
                html_path = file_path
            else:
                output_dir = file_path
                html_path = os.path.join(output_dir, 'index.html')

            # Resolve media_dir relative to output directory
            if not os.path.isabs(media_dir):
                media_output_dir = os.path.join(output_dir, media_dir)
            else:
                media_output_dir = media_dir

            # Create directories
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(media_output_dir, exist_ok=True)

            # Copy media files if db_dir is provided
            if db_dir:
                source_media = Path(db_dir) / 'media'
                if source_media.exists():
                    for media_file in source_media.iterdir():
                        if media_file.is_file():
                            shutil.copy2(media_file, media_output_dir)

            # Generate HTML with embedded data but media URLs pointing to media_dir
            html_content = self.export_conversations(
                conversations, embed=True, db_dir=db_dir,
                media_dir=media_dir, **kwargs
            )
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

        elif embed:
            # Single file export with embedded data (images encoded as base64)
            html_content = self.export_conversations(conversations, embed=True, db_dir=db_dir, **kwargs)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        else:
            # Multi-file export: index.html + conversations.jsonl + media/
            import shutil
            from pathlib import Path

            if file_path.endswith('.html'):
                # Specific HTML filename provided - use its directory
                output_dir = os.path.dirname(file_path) or '.'
                html_path = file_path
            else:
                # Directory name provided - create it and put files inside
                output_dir = file_path
                html_path = os.path.join(output_dir, 'index.html')

            # Create output directory and media directory
            os.makedirs(output_dir, exist_ok=True)
            media_output_dir = os.path.join(output_dir, 'media')
            os.makedirs(media_output_dir, exist_ok=True)

            jsonl_path = os.path.join(output_dir, 'conversations.jsonl')

            # Copy media files if db_dir is provided
            if db_dir:
                source_media = Path(db_dir) / 'media'
                if source_media.exists():
                    # Copy all media files
                    for media_file in source_media.iterdir():
                        if media_file.is_file():
                            shutil.copy2(media_file, media_output_dir)

            # Generate HTML without embedded data
            html_content = self.export_conversations(conversations, embed=False, **kwargs)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # Generate JSONL data
            conv_data, stats = self._prepare_data(conversations)
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for conv in conv_data:
                    f.write(json.dumps(conv, ensure_ascii=False) + '\n')
                # Write stats as last line with special marker
                f.write(json.dumps({'__stats__': stats}, ensure_ascii=False) + '\n')

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations to HTML5"""
        return self.export_conversations(conversations, **kwargs)

    def _prepare_data(self, conversations: List[ConversationTree], db_dir: str = None, embed: bool = True, media_dir: str = None):
        """Prepare conversation data and stats

        Args:
            conversations: List of conversations to export
            db_dir: Database directory for resolving media file paths
            embed: Whether to embed media as base64
            media_dir: If set, use file URLs to this directory instead of embedding
        """
        import base64
        from pathlib import Path

        conv_data = []
        stats = {
            'total_conversations': len(conversations),
            'total_messages': 0,
            'sources': {},
            'models': {},
            'tags': {},
            'date_range': {'earliest': None, 'latest': None}
        }

        for conv in conversations:
            messages = []
            all_messages = list(conv.message_map.values())
            stats['total_messages'] += len(all_messages)

            for msg in sorted(all_messages, key=lambda m: m.timestamp or datetime.min):
                if msg.timestamp:
                    if not stats['date_range']['earliest'] or msg.timestamp < stats['date_range']['earliest']:
                        stats['date_range']['earliest'] = msg.timestamp
                    if not stats['date_range']['latest'] or msg.timestamp > stats['date_range']['latest']:
                        stats['date_range']['latest'] = msg.timestamp

                # Extract images if present
                images = []
                if hasattr(msg.content, 'images') and msg.content.images:
                    for img in msg.content.images:
                        img_data = {
                            'url': img.url,
                            'caption': img.caption,
                            'mime_type': img.mime_type or 'image/png'
                        }

                        # Determine the filename for this image
                        img_ref = img.url or img.path
                        if img_ref:
                            # Get just the filename
                            if img_ref.startswith('media/'):
                                filename = img_ref[6:]  # Remove 'media/' prefix
                            elif '/' in img_ref:
                                filename = img_ref.split('/')[-1]
                            elif '\\' in img_ref:
                                filename = img_ref.split('\\')[-1]
                            else:
                                filename = img_ref
                        else:
                            filename = None

                        # If media_dir is set, use file URLs instead of embedding
                        if media_dir and filename:
                            # Set URL to point to media_dir
                            img_data['url'] = f"{media_dir}/{filename}"
                            # Don't embed data - we're using file references
                        elif img.data:
                            # Already have base64 data
                            img_data['data'] = img.data
                        elif embed and db_dir:
                            # Try to read image from disk and encode as base64
                            image_path = None
                            if img_ref:
                                # Try various path resolutions
                                candidates = []
                                if img_ref.startswith('media/'):
                                    # Relative URL like 'media/xxx.png'
                                    candidates.append(Path(db_dir) / img_ref)
                                elif '/' not in img_ref and '\\' not in img_ref:
                                    # Just a filename - look in media/ directory
                                    candidates.append(Path(db_dir) / 'media' / img_ref)
                                    # Also try directly in db_dir
                                    candidates.append(Path(db_dir) / img_ref)
                                else:
                                    # Some other path - try relative to db_dir
                                    candidates.append(Path(db_dir) / img_ref)
                                    # Also try as absolute path
                                    if Path(img_ref).is_absolute():
                                        candidates.append(Path(img_ref))

                                # Find first existing path
                                for candidate in candidates:
                                    if candidate.exists():
                                        image_path = candidate
                                        break

                            if image_path:
                                try:
                                    with open(image_path, 'rb') as f:
                                        img_data['data'] = base64.b64encode(f.read()).decode('utf-8')
                                    # Detect mime type from extension if not set
                                    if not img_data['mime_type'] or img_data['mime_type'] == 'image/png':
                                        ext = image_path.suffix.lower()
                                        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                                                   '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
                                                   '.jfif': 'image/jpeg', '.JPG': 'image/jpeg'}
                                        img_data['mime_type'] = mime_map.get(ext, 'image/png')
                                except Exception as e:
                                    import sys
                                    print(f"Warning: Could not read image {image_path}: {e}", file=sys.stderr)
                            elif img_ref:
                                import sys
                                print(f"Warning: Image not found: {img_ref} (looked in {db_dir}/media/)", file=sys.stderr)

                        images.append(img_data)

                msg_dict = {
                    'id': msg.id,
                    'role': msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                    'content': msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content),
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'parent_id': msg.parent_id,
                    'has_code': '```' in (msg.content.get_text() if hasattr(msg.content, 'get_text') else ''),
                    'has_images': bool(images),
                    'images': images,
                    'has_tools': bool(msg.content.tool_calls) if hasattr(msg.content, 'tool_calls') else False
                }
                messages.append(msg_dict)

            source = conv.metadata.source or 'Unknown'
            model = conv.metadata.model or 'Unknown'
            tags = conv.metadata.tags or []

            stats['sources'][source] = stats['sources'].get(source, 0) + 1
            stats['models'][model] = stats['models'].get(model, 0) + 1
            for tag in tags:
                stats['tags'][tag] = stats['tags'].get(tag, 0) + 1

            conv_dict = {
                'id': conv.id,
                'title': conv.title or 'Untitled Conversation',
                'messages': messages,
                'root_message_ids': conv.root_message_ids,
                'created_at': conv.metadata.created_at.isoformat() if conv.metadata.created_at else None,
                'updated_at': conv.metadata.updated_at.isoformat() if conv.metadata.updated_at else None,
                'source': source,
                'model': model,
                'tags': tags,
                'message_count': len(messages)
            }
            conv_data.append(conv_dict)

        # Convert dates for JSON
        if stats['date_range']['earliest']:
            stats['date_range']['earliest'] = stats['date_range']['earliest'].isoformat()
        if stats['date_range']['latest']:
            stats['date_range']['latest'] = stats['date_range']['latest'].isoformat()

        return conv_data, stats

    def export_conversations(
        self,
        conversations: List[ConversationTree],
        include_metadata: bool = True,
        theme: str = 'auto',
        embed: bool = True,
        db_dir: str = None,
        media_dir: str = None,
        **kwargs
    ) -> str:
        """
        Export conversations to advanced HTML5 application

        Args:
            conversations: List of conversations to export
            include_metadata: Include conversation metadata
            theme: Theme (light, dark, auto)
            embed: Whether to embed data in HTML (True) or load from external JSONL (False)
            db_dir: Database directory for resolving media file paths
            media_dir: If set, use file URLs to this directory instead of embedding base64
        """
        conv_data, stats = self._prepare_data(conversations, db_dir=db_dir, embed=embed, media_dir=media_dir)
        return self._generate_html(conv_data, stats, theme, embed)

    def _generate_html(self, conversations: List[Dict], stats: Dict, theme: str, embed: bool = True) -> str:
        """Generate complete HTML5 document"""

        if embed:
            # Embed data directly in HTML
            conv_json = json.dumps(conversations, ensure_ascii=False, indent=2)
            stats_json = json.dumps(stats, ensure_ascii=False, indent=2)
            # Escape for safe embedding
            conv_json = conv_json.replace('</script>', '<\\/script>').replace('<!--', '<\\!--')
            stats_json = stats_json.replace('</script>', '<\\/script>').replace('<!--', '<\\!--')
            data_script = f"""
        const CONVERSATIONS = {conv_json};
        const STATS = {stats_json};
        {self._get_javascript()}
"""
        else:
            # Load data from external JSONL file
            data_script = f"""
        let CONVERSATIONS = [];
        let STATS = {{}};

        // Load data from conversations.jsonl
        {self._get_jsonl_loader()}
        {self._get_javascript()}
"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CTK Conversation Browser</title>
    <meta name="description" content="Interactive conversation browser exported by CTK (Conversation Toolkit)">
    <meta name="generator" content="CTK HTML Exporter v2.0">

    <!-- KaTeX for LaTeX math rendering -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" integrity="sha384-n8MVd4RsNIU0tAv4ct0nTaAbDJwPJzDEaqSD1odI+WdtXRGWt2kTvGFasHpSy3SV" crossorigin="anonymous">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js" integrity="sha384-XjKyOOlGwcjNTAIQHIpgOno0Hl1YQqzUOEleOLALmuqehneUG+vnGctmUb0ZY0l8" crossorigin="anonymous"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" integrity="sha384-+VBxd3r6XgURycqtZ117nYw44OOcIax56Z4dCRWbxyPt0Koah1uHoK0o4+/RRE05" crossorigin="anonymous"></script>

    <!-- Marked.js for markdown rendering -->
    <script src="https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js"></script>

    <!-- Highlight.js for code syntax highlighting -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github.min.css" media="(prefers-color-scheme: light)">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/highlight.min.js"></script>

    <style>{self._get_css()}</style>
</head>
<body data-theme="{theme}">
    <div class="app">
        <!-- Header with Tabs -->
        <header class="header">
            <div class="app-icon" title="CTK Conversation Browser">💬</div>
            <div class="tabs">
                <button class="tab active" data-tab="search">🔍 Search</button>
                <button class="tab" data-tab="browse">📚 Browse</button>
                <button class="tab" data-tab="timeline">📅 Timeline</button>
                <button class="tab" data-tab="collections">⭐ Collections</button>
                <button class="tab" data-tab="snippets">💾 Code Snippets</button>
                <button class="tab" data-tab="media">🖼️ Media</button>
            </div>
            <div class="header-actions">
                <button id="keyboardBtn" class="btn btn-secondary" title="Keyboard shortcuts (?)">⌨️</button>
                <button id="statsBtn" class="btn btn-secondary" title="Statistics">📊</button>
                <button id="settingsBtn" class="btn btn-secondary" title="Settings">⚙️</button>
                <button id="themeBtn" class="btn btn-secondary" title="Toggle theme">🌓</button>
            </div>
        </header>

        <!-- Search Tab -->
        <div class="tab-content active" data-content="search">
            <div class="search-view">
                <div class="search-header">
                    <div class="search-box-container">
                        <input type="search" id="mainSearch" class="search-box"
                               placeholder="Search conversations and messages..." autofocus>
                        <div class="search-options">
                            <label><input type="checkbox" id="searchContent"> Search message content</label>
                            <label><input type="checkbox" id="searchTitles" checked> Search titles</label>
                            <label><input type="checkbox" id="searchRegex"> Regex</label>
                        </div>
                    </div>
                </div>
                <div id="searchResults" class="search-results"></div>
            </div>
        </div>

        <!-- Browse Tab -->
        <div class="tab-content" data-content="browse">
            <div class="browse-view">
                <!-- Top Filter Bar -->
                <div class="filter-bar">
                    <div class="filter-bar-row">
                        <input type="search" id="filterSearch" placeholder="🔍 Filter conversations..." class="filter-search">
                        <select id="filterSource" class="filter-select">
                            <option value="">All Sources</option>
                        </select>
                        <select id="filterModel" class="filter-select">
                            <option value="">All Models</option>
                        </select>
                        <select id="filterTag" class="filter-select">
                            <option value="">All Tags</option>
                        </select>
                        <label class="filter-checkbox"><input type="checkbox" id="filterFavorites"> ⭐ Favorites</label>
                        <label class="filter-checkbox"><input type="checkbox" id="filterUnread"> 📖 Unread</label>
                        <label class="filter-checkbox"><input type="checkbox" id="filterAnnotated"> 📝 Notes</label>
                        <select id="sortSelect" class="filter-select">
                            <option value="date">Latest first</option>
                            <option value="date-asc">Oldest first</option>
                            <option value="title">Title A-Z</option>
                            <option value="messages">Most messages</option>
                            <option value="rating">Highest rated</option>
                        </select>
                    </div>
                </div>

                <!-- Two Column Layout -->
                <div class="browse-columns">
                    <aside class="conversation-sidebar">
                        <div id="favoritesDropZone" class="drop-zone">
                            ⭐ Drop here to favorite
                        </div>
                        <div id="conversationList" class="conversation-list"></div>
                    </aside>

                    <main class="conversation-content">
                        <div id="conversationView"></div>
                    </main>
                </div>
            </div>
        </div>

        <!-- Timeline Tab -->
        <div class="tab-content" data-content="timeline">
            <div class="timeline-view">
                <div class="timeline-header">
                    <h2>📅 Timeline</h2>
                    <div class="timeline-controls">
                        <label>Group by:
                            <select id="timelineGrouping">
                                <option value="day">Day</option>
                                <option value="week">Week</option>
                                <option value="month" selected>Month</option>
                                <option value="year">Year</option>
                            </select>
                        </label>
                    </div>
                </div>
                <div id="timelineContent" class="timeline-content"></div>
            </div>
        </div>

        <!-- Collections Tab -->
        <div class="tab-content" data-content="collections">
            <div class="collections-view">
                <div class="collections-header">
                    <h2>📚 Collections</h2>
                    <button id="newCollectionBtn" class="btn">+ New Collection</button>
                </div>
                <div id="collectionsList" class="collections-list"></div>
            </div>
        </div>

        <!-- Code Snippets Tab -->
        <div class="tab-content" data-content="snippets">
            <div class="snippets-view">
                <div class="snippets-header">
                    <h2>💾 Saved Code Snippets</h2>
                    <button id="clearSnippetsBtn" class="btn btn-danger">Clear All</button>
                </div>
                <div id="snippetsList" class="snippets-list"></div>
            </div>
        </div>

        <!-- Media Tab -->
        <div class="tab-content" data-content="media">
            <div class="media-view">
                <div class="media-header">
                    <h2>🖼️ Media Gallery</h2>
                    <div class="media-controls">
                        <input type="search" id="mediaSearch" placeholder="Filter media..." class="filter-search">
                        <select id="mediaSort" class="filter-select">
                            <option value="date">Latest first</option>
                            <option value="date-asc">Oldest first</option>
                            <option value="conversation">By conversation</option>
                        </select>
                        <label class="filter-checkbox">
                            <input type="checkbox" id="showCaptions" checked> Show captions
                        </label>
                    </div>
                </div>
                <div id="mediaGallery" class="media-gallery"></div>
            </div>
        </div>

        <!-- Modals -->
        <div id="statsModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📊 Statistics</h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div id="statsContent" class="modal-body"></div>
            </div>
        </div>

        <div id="settingsModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>⚙️ Settings</h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <h3>Preferences</h3>
                    <label>Font Size: <input type="range" id="fontSizeSlider" min="12" max="20" value="14"> <span id="fontSizeValue">14px</span></label>
                    <label>Messages per page: <input type="number" id="pageSize" min="10" max="100" value="50"></label>
                    <label><input type="checkbox" id="showTimestamps" checked> Show message timestamps</label>
                    <label><input type="checkbox" id="compactMode"> Compact view</label>

                    <h3>Data Management</h3>
                    <button id="clearLocalStorage" class="btn btn-danger">Clear All Local Data</button>
                    <p class="help-text">This will remove all favorites, annotations, collections, and preferences.</p>
                </div>
            </div>
        </div>

        <div id="annotationModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📝 Add Note</h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <textarea id="annotationText" placeholder="Enter your note..." rows="6"></textarea>
                    <div class="modal-actions">
                        <button id="saveAnnotation" class="btn">Save Note</button>
                        <button id="deleteAnnotation" class="btn btn-danger">Delete Note</button>
                    </div>
                </div>
            </div>
        </div>

        <div id="keyboardModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>⌨️ Keyboard Shortcuts</h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="shortcuts-grid">
                        <div class="shortcut-group">
                            <h3>Navigation</h3>
                            <div class="shortcut-item">
                                <kbd>/</kbd>
                                <span>Focus search</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>Ctrl</kbd> + <kbd>K</kbd>
                                <span>Quick search</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>j</kbd> / <kbd>k</kbd>
                                <span>Navigate conversations</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>Enter</kbd>
                                <span>Open conversation</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>Esc</kbd>
                                <span>Close modal / Clear search</span>
                            </div>
                        </div>
                        <div class="shortcut-group">
                            <h3>Actions</h3>
                            <div class="shortcut-item">
                                <kbd>f</kbd>
                                <span>Toggle favorite</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>c</kbd>
                                <span>Copy conversation</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>1</kbd> - <kbd>5</kbd>
                                <span>Rate conversation</span>
                            </div>
                            <div class="shortcut-item">
                                <kbd>?</kbd>
                                <span>Show this help</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Lightbox -->
        <div class="lightbox" id="lightbox">
            <button class="lightbox-close" onclick="closeLightbox()">×</button>
            <div class="lightbox-content">
                <img id="lightboxImage" class="lightbox-image" src="" alt="">
                <div id="lightboxCaption" class="lightbox-caption"></div>
            </div>
        </div>

        <!-- Footer -->
        <footer class="app-footer">
            Exported by <a href="https://github.com/your-org/ctk" target="_blank">CTK</a> (Conversation Toolkit)
            • Press <kbd>?</kbd> for keyboard shortcuts
        </footer>
    </div>

    <script>
{data_script}
    </script>
</body>
</html>"""
        return html

    def _get_css(self) -> str:
        """Get CSS styles"""
        return """
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --bg-tertiary: #e9ecef;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --border: #dee2e6;
    --accent: #0d6efd;
    --accent-hover: #0b5ed7;
    --success: #198754;
    --danger: #dc3545;
    --warning: #ffc107;
    --user-bg: #e7f3ff;
    --assistant-bg: #f3e5f5;
    --system-bg: #fff3cd;
    --shadow: 0 2px 4px rgba(0,0,0,0.1);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.15);
}

[data-theme="dark"] {
    --bg-primary: #1a1a1a;
    --bg-secondary: #2d2d2d;
    --bg-tertiary: #3a3a3a;
    --text-primary: #e8e8e8;
    --text-secondary: #a8a8a8;
    --border: #444;
    --user-bg: #1e3a5f;
    --assistant-bg: #3d2e4f;
    --system-bg: #4a3c2a;
    --shadow: 0 2px 4px rgba(0,0,0,0.3);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.5);
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    overflow: hidden;
}

.app { display: flex; flex-direction: column; height: 100vh; }

.header {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    padding: 0.75rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
}

.app-icon {
    font-size: 1.5rem;
    cursor: default;
    user-select: none;
}

.header-actions { display: flex; gap: 0.5rem; }

.btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
}

.btn:hover { background: var(--border); }
.btn-secondary { background: var(--bg-tertiary); }
.btn-danger { background: var(--danger); color: white; }
.btn-danger:hover { background: #bb2d3b; }

.tabs {
    display: flex;
    flex: 1;
    gap: 0.25rem;
    justify-content: center;
}

.tab {
    padding: 0.5rem 1rem;
    border: none;
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.9rem;
    border-radius: 6px;
    transition: all 0.2s;
}

.tab:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

.tab.active {
    color: var(--accent);
    background: var(--bg-tertiary);
    font-weight: 600;
}

.tab-content {
    display: none;
    flex: 1;
    overflow: hidden;
}

.tab-content.active { display: flex; flex-direction: column; }

/* Search View */
.search-view {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.search-header {
    padding: 2rem;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
}

.search-box-container {
    max-width: 800px;
    margin: 0 auto;
}

.search-box {
    width: 100%;
    padding: 1rem 1.5rem;
    font-size: 1.1rem;
    border: 2px solid var(--border);
    border-radius: 50px;
    background: var(--bg-primary);
    color: var(--text-primary);
    transition: all 0.2s;
}

.search-box:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.1);
}

.search-options {
    display: flex;
    gap: 1.5rem;
    margin-top: 1rem;
    justify-content: center;
}

.search-options label {
    font-size: 0.9rem;
    color: var(--text-secondary);
    cursor: pointer;
}

.search-results {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
}

.search-result {
    max-width: 900px;
    margin: 0 auto 1.5rem;
    padding: 1.5rem;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border);
    cursor: pointer;
    transition: all 0.2s;
}

.search-result:hover {
    border-color: var(--accent);
    box-shadow: var(--shadow);
}

.search-result-title {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--accent);
}

.search-result-meta {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 0.75rem;
}

.search-result-snippet {
    font-size: 0.95rem;
    line-height: 1.5;
}

.highlight {
    background: var(--warning);
    padding: 0 0.2rem;
    border-radius: 2px;
}

/* Browse View */
.browse-view {
    display: flex;
    flex-direction: column;
    height: 100%;
}

/* Top Filter Bar */
.filter-bar {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    padding: 0.75rem 1rem;
}

.filter-bar-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
}

.filter-search {
    flex: 1;
    min-width: 200px;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
}

.filter-select {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
    cursor: pointer;
}

.filter-checkbox {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
    white-space: nowrap;
}

.filter-checkbox:hover {
    background: var(--bg-tertiary);
}

.filter-checkbox input[type="checkbox"] {
    cursor: pointer;
}

/* Two Column Layout */
.browse-columns {
    display: flex;
    flex: 1;
    overflow: hidden;
}

.conversation-sidebar {
    width: 400px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.conversation-content {
    flex: 1;
    overflow-y: auto;
}

.conversation-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    min-height: 40vh;
}

.conversation-item {
    padding: 1rem;
    margin-bottom: 0.5rem;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
}

.conversation-item:hover {
    border-color: var(--accent);
    box-shadow: var(--shadow);
}

.conversation-item.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
}

.conversation-item.active .conv-meta { color: rgba(255,255,255,0.8); }

.conversation-item.favorite::before {
    content: '⭐';
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
}

.conversation-item.unread::after {
    content: '';
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    width: 8px;
    height: 8px;
    background: var(--accent);
    border-radius: 50%;
}

.conversation-item.dragging {
    opacity: 0.5;
    cursor: move;
}

.drop-zone {
    border: 2px dashed var(--border);
    background: var(--bg-secondary);
    padding: 1rem;
    margin: 1rem 0;
    border-radius: 4px;
    text-align: center;
    color: var(--text-secondary);
    transition: all 0.2s;
}

.drop-zone.drag-over {
    border-color: var(--primary);
    background: var(--accent);
    color: var(--primary);
    transform: scale(1.02);
}

.collection-card.drag-over {
    border-color: var(--primary);
    background: var(--accent);
    transform: scale(1.02);
}

.conv-title {
    font-weight: 600;
    margin-bottom: 0.25rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.conv-meta {
    font-size: 0.8rem;
    color: var(--text-secondary);
}

.conv-badges {
    display: flex;
    gap: 0.25rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
}

.badge {
    font-size: 0.7rem;
    padding: 0.2rem 0.5rem;
    background: var(--bg-tertiary);
    border-radius: 3px;
}

#conversationView {
    padding: 2rem;
}

.conversation-header {
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 2px solid var(--border);
}

.conversation-title {
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}

.conversation-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.message {
    margin-bottom: 1.5rem;
    padding: 1.25rem;
    border-radius: 8px;
    position: relative;
}

.message.user { background: var(--user-bg); margin-left: 2rem; }
.message.assistant { background: var(--assistant-bg); margin-right: 2rem; }
.message.system { background: var(--system-bg); font-size: 0.9rem; }

.message-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}

.message-role {
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    opacity: 0.7;
}

.message-actions {
    display: flex;
    gap: 0.25rem;
    opacity: 0;
    transition: opacity 0.2s;
}

.message:hover .message-actions { opacity: 1; }

.message-action {
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    background: rgba(0,0,0,0.1);
    border: none;
    border-radius: 3px;
    cursor: pointer;
}

.message-action:hover { background: rgba(0,0,0,0.2); }

.message-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.6;
}

.message-content code {
    background: rgba(0,0,0,0.1);
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    font-size: 0.9em;
}

.message-content pre {
    background: rgba(0,0,0,0.1);
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
    margin: 0.5rem 0;
}

.message-annotation {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: var(--warning);
    border-left: 3px solid #cc9a00;
    border-radius: 4px;
    font-size: 0.9rem;
}

.message-timestamp {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
}

.rating {
    display: inline-flex;
    gap: 0.25rem;
}

.rating-star {
    cursor: pointer;
    font-size: 1.2rem;
    color: var(--text-secondary);
    transition: color 0.2s, transform 0.2s;
}

.rating-star:hover {
    color: var(--warning);
    transform: scale(1.2);
}

.rating-star.active {
    color: var(--warning);
}

/* Timeline */
.timeline-view {
    padding: 2rem;
    overflow-y: auto;
}

.timeline-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
}

.timeline-controls select {
    padding: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
}

.timeline-content {
    position: relative;
}

.timeline-period {
    margin-bottom: 3rem;
}

.timeline-period-header {
    position: sticky;
    top: 0;
    background: var(--bg-primary);
    padding: 1rem 0;
    margin-bottom: 1rem;
    border-bottom: 2px solid var(--primary);
    z-index: 1;
}

.timeline-period-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--primary);
}

.timeline-period-count {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-left: 1rem;
}

.timeline-items {
    display: grid;
    gap: 1rem;
    padding-left: 2rem;
    border-left: 2px solid var(--border);
}

.timeline-item {
    position: relative;
    padding: 1rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
}

.timeline-item::before {
    content: '●';
    position: absolute;
    left: -2.65rem;
    top: 1rem;
    width: 1rem;
    height: 1rem;
    color: var(--primary);
    font-size: 1.5rem;
    line-height: 1;
}

.timeline-item:hover {
    transform: translateX(4px);
    border-color: var(--primary);
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.timeline-item-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
}

.timeline-item-meta {
    display: flex;
    gap: 1rem;
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.timeline-item-date {
    color: var(--primary);
}

.timeline-item.favorite .timeline-item-title::after {
    content: ' ⭐';
}

/* Collections */
.collections-view, .snippets-view {
    padding: 2rem;
    overflow-y: auto;
}

.collections-header, .snippets-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
}

.collection-card {
    padding: 1.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 1rem;
}

.collection-title {
    font-size: 1.2rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

.snippet-card {
    padding: 1rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 1rem;
}

.snippet-code {
    background: var(--bg-primary);
    padding: 1rem;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 0.9rem;
    overflow-x: auto;
}

/* Media Gallery */
.media-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
}

.media-header {
    padding: 1.5rem;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
}

.media-header h2 {
    margin-bottom: 1rem;
}

.media-controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
}

.media-gallery {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1.5rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, 300px);
    grid-auto-rows: min-content;
    gap: 1.5rem;
    justify-content: center;
}

.media-item {
    width: 300px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
}

.media-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.media-item .media-item-image {
    width: 300px;
    height: 300px;
    object-fit: cover;
    background: var(--bg-tertiary);
    display: block;
}

.media-item-info {
    padding: 0.75rem;
}

.media-item-caption {
    font-size: 0.9rem;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.media-item-meta {
    font-size: 0.8rem;
    color: var(--text-secondary);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.media-item-conversation {
    color: var(--link);
    text-decoration: none;
    cursor: pointer;
}

.media-item-conversation:hover {
    text-decoration: underline;
}

.media-empty {
    text-align: center;
    padding: 3rem;
    color: var(--text-secondary);
    grid-column: 1 / -1;
}

/* Modal */
.modal {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0,0,0,0.5);
    z-index: 1000;
    align-items: center;
    justify-content: center;
}

.modal.active { display: flex; }

.modal-content {
    background: var(--bg-primary);
    border-radius: 8px;
    max-width: 800px;
    max-height: 80vh;
    width: 90%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.modal-header {
    padding: 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-secondary);
}

.modal-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
}

.modal-body textarea {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-family: inherit;
    resize: vertical;
}

.modal-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.shortcuts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
}

.shortcut-group h3 {
    margin-bottom: 1rem;
    color: var(--primary);
}

.shortcut-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
    background: var(--bg-secondary);
    border-radius: 4px;
}

.shortcut-item kbd {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    font-family: monospace;
    font-size: 0.85rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 4px;
    box-shadow: 0 2px 0 var(--border);
}

.shortcut-item span {
    color: var(--text-secondary);
}

.help-text {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
}

@media (max-width: 768px) {
    .header {
        flex-wrap: wrap;
        padding: 0.5rem 1rem;
    }

    .tabs {
        order: 3;
        width: 100%;
        justify-content: flex-start;
        margin-top: 0.5rem;
        overflow-x: auto;
        flex-wrap: nowrap;
    }

    .tab {
        padding: 0.4rem 0.8rem;
        font-size: 0.85rem;
        white-space: nowrap;
    }

    .filter-bar-row {
        flex-direction: column;
        align-items: stretch;
    }

    .filter-search, .filter-select, .filter-checkbox {
        width: 100%;
    }

    .browse-columns {
        flex-direction: column;
    }

    .conversation-sidebar {
        width: 100%;
        max-height: 50vh;
    }

    .message.user, .message.assistant {
        margin-left: 0;
        margin-right: 0;
    }
}

@media print {
    /* Hide UI elements */
    .header,
    .tabs,
    .filter-bar,
    .conversation-sidebar,
    .btn,
    .modal,
    .conversation-actions,
    .message-actions,
    .rating,
    .search-view,
    .timeline-view,
    .collections-view,
    .snippets-view {
        display: none !important;
    }

    /* Show only the main conversation content */
    body {
        background: white;
        color: black;
    }

    .app {
        display: block;
    }

    .tab-content[data-content="browse"] {
        display: block !important;
    }

    .browse-view {
        display: block;
    }

    .browse-columns {
        display: block;
    }

    .conversation-content {
        width: 100%;
        max-width: none;
    }

    #conversationView {
        display: block;
    }

    /* Conversation header */
    .conversation-header {
        border-bottom: 2px solid black;
        padding-bottom: 1rem;
        margin-bottom: 2rem;
        page-break-after: avoid;
    }

    .conversation-title {
        font-size: 24pt;
        font-weight: bold;
        color: black;
    }

    .conversation-meta {
        color: #666;
        font-size: 10pt;
        margin-top: 0.5rem;
    }

    /* Messages */
    .message {
        page-break-inside: avoid;
        margin-bottom: 1.5rem;
        padding: 1rem;
        border: 1px solid #ccc;
        border-radius: 0;
    }

    .message-header {
        border-bottom: 1px solid #ccc;
        padding-bottom: 0.5rem;
        margin-bottom: 0.5rem;
    }

    .message-role {
        font-weight: bold;
        font-size: 12pt;
        color: black;
    }

    .message-timestamp {
        color: #666;
        font-size: 9pt;
    }

    .message-content {
        color: black;
        font-size: 11pt;
        line-height: 1.6;
    }

    /* Code blocks */
    pre {
        background: #f5f5f5 !important;
        border: 1px solid #ccc;
        padding: 0.5rem;
        overflow-x: visible;
        white-space: pre-wrap;
        word-wrap: break-word;
        page-break-inside: avoid;
    }

    code {
        background: #f5f5f5;
        color: black;
        font-family: 'Courier New', monospace;
        font-size: 10pt;
    }

    /* Links */
    a {
        color: black;
        text-decoration: underline;
    }

    a[href]:after {
        content: " (" attr(href) ")";
        font-size: 9pt;
        color: #666;
    }

    /* Page breaks */
    h1, h2, h3 {
        page-break-after: avoid;
    }

    /* Remove shadows and backgrounds */
    * {
        box-shadow: none !important;
        text-shadow: none !important;
    }
}

/* ==================== Code Highlighting & Math ==================== */

/* Syntax highlighting theme switching */
body[data-theme="light"] .hljs {
    background: #f6f8fa !important;
    color: #24292f !important;
}

body[data-theme="dark"] .hljs {
    background: #161b22 !important;
    color: #e6edf3 !important;
}

/* Code blocks */
.message-content pre {
    margin: 1rem 0;
    border-radius: 6px;
    overflow-x: auto;
}

.message-content pre code {
    background: transparent !important;
    padding: 0 !important;
    display: block;
    font-size: 0.9em;
    line-height: 1.5;
}

/* Inline code */
.message-content code:not(pre code) {
    background: rgba(127, 127, 127, 0.15);
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-family: 'Courier New', Consolas, Monaco, monospace;
    font-size: 0.9em;
}

/* KaTeX math */
.katex-display {
    margin: 1rem 0;
    overflow-x: auto;
    overflow-y: hidden;
}

.katex {
    font-size: 1.1em;
}

/* Markdown elements in messages */
.message-content h1,
.message-content h2,
.message-content h3,
.message-content h4,
.message-content h5,
.message-content h6 {
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    font-weight: 600;
}

.message-content h1 { font-size: 1.6em; }
.message-content h2 { font-size: 1.4em; }
.message-content h3 { font-size: 1.2em; }
.message-content h4 { font-size: 1.1em; }

.message-content ul,
.message-content ol {
    margin: 0.75rem 0;
    padding-left: 2rem;
}

.message-content li {
    margin: 0.25rem 0;
}

.message-content blockquote {
    border-left: 4px solid var(--border);
    padding-left: 1rem;
    margin: 1rem 0;
    color: var(--text-secondary);
    font-style: italic;
}

.message-content a {
    color: var(--accent);
    text-decoration: none;
}

.message-content a:hover {
    text-decoration: underline;
}

.message-content table {
    border-collapse: collapse;
    margin: 1rem 0;
    width: 100%;
}

.message-content th,
.message-content td {
    border: 1px solid var(--border);
    padding: 0.5rem;
    text-align: left;
}

.message-content th {
    background: var(--bg-secondary);
    font-weight: 600;
}

.message-content hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1.5rem 0;
}

/* ==================== Image Gallery ==================== */

.message-images {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
    margin: 1rem 0;
}

.message-image {
    position: relative;
    cursor: pointer;
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-tertiary);
    transition: transform 0.2s, box-shadow 0.2s;
}

.message-image:hover {
    transform: scale(1.02);
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.message-image img {
    width: 100%;
    height: auto;
    display: block;
    object-fit: cover;
    max-height: 300px;
}

.message-image.loading {
    min-height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
}

.message-image-caption {
    padding: 0.5rem;
    background: rgba(0,0,0,0.7);
    color: white;
    font-size: 0.85rem;
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    opacity: 0;
    transition: opacity 0.2s;
}

.message-image:hover .message-image-caption {
    opacity: 1;
}

/* Lightbox */
.lightbox {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.9);
    z-index: 10000;
    align-items: center;
    justify-content: center;
    padding: 2rem;
}

.lightbox.active {
    display: flex;
}

.lightbox-content {
    max-width: 90vw;
    max-height: 90vh;
    position: relative;
}

.lightbox-image {
    max-width: 100%;
    max-height: 90vh;
    object-fit: contain;
}

.lightbox-caption {
    color: white;
    text-align: center;
    margin-top: 1rem;
    font-size: 1rem;
}

.lightbox-close {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: rgba(255,255,255,0.2);
    border: none;
    color: white;
    font-size: 2rem;
    width: 3rem;
    height: 3rem;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
}

.lightbox-close:hover {
    background: rgba(255,255,255,0.3);
}

/* Loading spinner */
@keyframes spin {
    to { transform: rotate(360deg); }
}

.spinner {
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--text-secondary);
}

.empty-state-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}

.empty-state-title {
    font-size: 1.5rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
}

.empty-state-text {
    font-size: 1rem;
    max-width: 400px;
    margin: 0 auto;
}

/* Print styles */
@media print {
    body {
        background: white;
        color: black;
        overflow: visible;
    }

    .app {
        height: auto;
        overflow: visible;
    }

    .header,
    .header-actions,
    .tabs,
    .filter-bar,
    .conversation-sidebar,
    .message-actions,
    .modal,
    .lightbox {
        display: none !important;
    }

    .tab-content {
        display: block !important;
        overflow: visible;
    }

    .browse-view,
    .browse-columns,
    .conversation-content {
        display: block;
        overflow: visible;
    }

    .conversation-view {
        max-width: 100%;
        padding: 0;
    }

    .message {
        break-inside: avoid;
        page-break-inside: avoid;
        margin: 1rem 0;
        padding: 1rem;
        border: 1px solid #ccc;
        background: #f9f9f9 !important;
    }

    .message.user { background: #e7f3ff !important; }
    .message.assistant { background: #f3e5f5 !important; }

    pre {
        white-space: pre-wrap;
        word-wrap: break-word;
    }

    .conversation-header {
        border-bottom: 2px solid black;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
    }

    a { color: black; text-decoration: underline; }
}

/* Footer */
.app-footer {
    background: var(--bg-secondary);
    border-top: 1px solid var(--border);
    padding: 0.5rem 1rem;
    text-align: center;
    font-size: 0.8rem;
    color: var(--text-secondary);
}

.app-footer a {
    color: var(--accent);
    text-decoration: none;
}

.app-footer a:hover {
    text-decoration: underline;
}
"""

    def _get_javascript(self) -> str:
        """Get JavaScript code"""
        return """
// ==================== State Management ====================
class AppState {
    constructor() {
        this.conversations = [...CONVERSATIONS];
        this.currentConv = null;
        this.currentTab = 'search';
        this.filters = {
            source: '',
            model: '',
            tag: '',
            favorites: false,
            unread: false,
            annotated: false,
            search: ''
        };
        this.sort = 'date';

        // Load from localStorage
        this.favorites = new Set(JSON.parse(localStorage.getItem('favorites') || '[]'));
        this.annotations = JSON.parse(localStorage.getItem('annotations') || '{}');
        this.readStatus = new Set(JSON.parse(localStorage.getItem('readStatus') || '[]'));
        this.collections = JSON.parse(localStorage.getItem('collections') || '[]');
        this.snippets = JSON.parse(localStorage.getItem('snippets') || '[]');
        this.ratings = JSON.parse(localStorage.getItem('ratings') || '{}');
        this.customTags = JSON.parse(localStorage.getItem('customTags') || '{}');
        this.searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
        this.preferences = JSON.parse(localStorage.getItem('preferences') || '{}');
    }

    save(key) {
        const data = {
            favorites: Array.from(this.favorites),
            annotations: this.annotations,
            readStatus: Array.from(this.readStatus),
            collections: this.collections,
            snippets: this.snippets,
            ratings: this.ratings,
            customTags: this.customTags,
            searchHistory: this.searchHistory,
            preferences: this.preferences
        };
        localStorage.setItem(key, JSON.stringify(data[key]));
    }

    toggleFavorite(convId) {
        if (this.favorites.has(convId)) {
            this.favorites.delete(convId);
        } else {
            this.favorites.add(convId);
        }
        this.save('favorites');
    }

    setAnnotation(convId, messageId, text) {
        const key = `${convId}:${messageId}`;
        if (text) {
            this.annotations[key] = { text, timestamp: new Date().toISOString() };
        } else {
            delete this.annotations[key];
        }
        this.save('annotations');
    }

    markAsRead(convId) {
        this.readStatus.add(convId);
        this.save('readStatus');
    }

    setRating(convId, rating) {
        this.ratings[convId] = rating;
        this.save('ratings');
    }

    addToCollection(collectionName, convIds) {
        let collection = this.collections.find(c => c.name === collectionName);
        if (!collection) {
            collection = { name: collectionName, conversations: [], created: new Date().toISOString() };
            this.collections.push(collection);
        }
        collection.conversations = [...new Set([...collection.conversations, ...convIds])];
        this.save('collections');
    }

    saveSnippet(code, language, source) {
        this.snippets.push({
            id: Date.now().toString(),
            code,
            language,
            source,
            timestamp: new Date().toISOString()
        });
        this.save('snippets');
    }

    clearAllData() {
        if (confirm('Are you sure? This will delete all favorites, annotations, collections, and preferences.')) {
            localStorage.clear();
            location.reload();
        }
    }
}

const state = new AppState();

// ==================== Content Processing ====================

// Configure marked.js
marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (err) {
                console.error('Highlight error:', err);
            }
        }
        return hljs.highlightAuto(code).value;
    }
});

/**
 * Process message content with markdown and LaTeX rendering
 * @param {string} text - Raw message text
 * @returns {string} - HTML with rendered markdown and math
 */
function processMessageContent(text) {
    if (!text) return '';

    // Protect LaTeX blocks from markdown processing
    const mathBlocks = [];
    let processedText = text;

    // Extract display math blocks ($$...$$, \\[...\\])
    processedText = processedText.replace(/\\$\\$([\\s\\S]+?)\\$\\$/g, (match, content) => {
        const index = mathBlocks.length;
        mathBlocks.push({type: 'display', content: match});
        return `___MATH_BLOCK_${index}___`;
    });

    processedText = processedText.replace(/\\\\\\[([\\s\\S]+?)\\\\\\]/g, (match, content) => {
        const index = mathBlocks.length;
        mathBlocks.push({type: 'display', content: match});
        return `___MATH_BLOCK_${index}___`;
    });

    // Extract inline math ($...$, \\(...\\))
    processedText = processedText.replace(/\\$([^\\$\\n]+?)\\$/g, (match, content) => {
        const index = mathBlocks.length;
        mathBlocks.push({type: 'inline', content: match});
        return `___MATH_BLOCK_${index}___`;
    });

    processedText = processedText.replace(/\\\\\\(([^\\)]+?)\\\\\\)/g, (match, content) => {
        const index = mathBlocks.length;
        mathBlocks.push({type: 'inline', content: match});
        return `___MATH_BLOCK_${index}___`;
    });

    // Now render markdown
    let html = marked.parse(processedText);

    // Restore math blocks
    mathBlocks.forEach((block, index) => {
        html = html.replace(`___MATH_BLOCK_${index}___`, block.content);
    });

    return html;
}

/**
 * Render LaTeX math in an element after it's been added to the DOM
 * @param {HTMLElement} element - The element containing math expressions
 */
function renderMath(element) {
    if (typeof renderMathInElement !== 'undefined') {
        try {
            renderMathInElement(element, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '\\\\[', right: '\\\\]', display: true},
                    {left: '\\\\(', right: '\\\\)', display: false},
                    {left: '$', right: '$', display: false}
                ],
                throwOnError: false,
                strict: false
            });
        } catch (err) {
            console.error('KaTeX render error:', err);
        }
    }
}

// ==================== Init ====================
document.addEventListener('DOMContentLoaded', init);

function init() {
    setupTabs();
    setupEventListeners();
    populateFilters();
    applyPreferences();
    renderConversationList();

    // Set theme
    const theme = document.body.dataset.theme;
    if (theme === 'auto') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.body.dataset.theme = prefersDark ? 'dark' : 'light';
    }
}

function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            const tabName = tab.dataset.tab;
            document.querySelector(`[data-content="${tabName}"]`).classList.add('active');
            state.currentTab = tabName;

            // Update URL hash
            updateHash(tabName);

            if (tabName === 'timeline') renderTimeline();
            if (tabName === 'collections') renderCollections();
            if (tabName === 'snippets') renderSnippets();
            if (tabName === 'media') renderMediaGallery();
        });
    });
}

function setupEventListeners() {
    // Search
    document.getElementById('mainSearch').addEventListener('input', handleMainSearch);
    document.getElementById('filterSearch').addEventListener('input', applyFilters);

    // Filters
    document.getElementById('filterSource').addEventListener('change', applyFilters);
    document.getElementById('filterModel').addEventListener('change', applyFilters);
    document.getElementById('filterTag').addEventListener('change', applyFilters);
    document.getElementById('filterFavorites').addEventListener('change', applyFilters);
    document.getElementById('filterUnread').addEventListener('change', applyFilters);
    document.getElementById('filterAnnotated').addEventListener('change', applyFilters);

    // Sort
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        state.sort = e.target.value;
        renderConversationList();
    });

    // Timeline
    document.getElementById('timelineGrouping').addEventListener('change', renderTimeline);

    // Header actions
    document.getElementById('themeBtn').addEventListener('click', toggleTheme);
    document.getElementById('statsBtn').addEventListener('click', showStats);
    document.getElementById('settingsBtn').addEventListener('click', showSettings);
    document.getElementById('keyboardBtn').addEventListener('click', showKeyboardHelp);

    // Modals
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.remove('active');
        });
    });

    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    });

    // Settings
    document.getElementById('clearLocalStorage').addEventListener('click', () => state.clearAllData());
    document.getElementById('fontSizeSlider').addEventListener('input', (e) => {
        const size = e.target.value;
        document.getElementById('fontSizeValue').textContent = size + 'px';
        document.documentElement.style.fontSize = size + 'px';
        state.preferences.fontSize = size;
        state.save('preferences');
    });

    // Collections
    document.getElementById('newCollectionBtn').addEventListener('click', createCollection);

    // Snippets
    document.getElementById('clearSnippetsBtn').addEventListener('click', () => {
        if (confirm('Clear all saved snippets?')) {
            state.snippets = [];
            state.save('snippets');
            renderSnippets();
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcut);

    // Hash navigation (History API)
    window.addEventListener('hashchange', handleHashChange);
    handleHashChange(); // Handle initial hash on page load

    // Drag and drop zones
    setupDropZones();
}

function setupDropZones() {
    const favoritesZone = document.getElementById('favoritesDropZone');

    favoritesZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        favoritesZone.classList.add('drag-over');
    });

    favoritesZone.addEventListener('dragleave', () => {
        favoritesZone.classList.remove('drag-over');
    });

    favoritesZone.addEventListener('drop', (e) => {
        e.preventDefault();
        favoritesZone.classList.remove('drag-over');
        const convId = e.dataTransfer.getData('text/plain');
        if (convId) {
            state.toggleFavorite(convId);
            renderConversationList();
        }
    });
}

function handleHashChange() {
    const hash = window.location.hash.slice(1); // Remove '#'
    if (!hash) return;

    const parts = hash.split('/');
    const type = parts[0];

    if (type === 'conv' && parts[1]) {
        // Navigate to specific conversation: #conv/abc123
        const convId = parts[1];
        const conv = CONVERSATIONS.find(c => c.id === convId);
        if (conv) {
            document.querySelector('[data-tab="browse"]').click();
            setTimeout(() => showConversation(conv), 100);
        }
    } else if (['search', 'browse', 'timeline', 'collections', 'snippets'].includes(type)) {
        // Navigate to specific tab: #timeline, #collections, etc.
        const tabButton = document.querySelector(`[data-tab="${type}"]`);
        if (tabButton) tabButton.click();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function updateHash(path) {
    if (window.location.hash.slice(1) !== path) {
        window.history.pushState(null, '', '#' + path);
    }
}

function handleKeyboardShortcut(e) {
    // Ignore if typing in input/textarea
    if (e.target.matches('input, textarea') && !['Escape'].includes(e.key)) {
        // Allow Ctrl+K even in inputs
        if (!(e.key === 'k' && (e.ctrlKey || e.metaKey))) {
            return;
        }
    }

    const key = e.key.toLowerCase();
    const ctrl = e.ctrlKey || e.metaKey;

    // Ctrl+K or /: Focus search
    if ((key === 'k' && ctrl) || key === '/') {
        e.preventDefault();
        if (state.currentTab !== 'search') {
            document.querySelector('[data-tab="search"]').click();
        }
        document.getElementById('mainSearch').focus();
        return;
    }

    // ?: Show keyboard shortcuts
    if (key === '?' && !ctrl) {
        e.preventDefault();
        document.getElementById('keyboardModal').classList.add('active');
        return;
    }

    // Escape: Close modals or clear search
    if (key === 'escape') {
        const activeModal = document.querySelector('.modal.active');
        if (activeModal) {
            activeModal.classList.remove('active');
        } else {
            const searchInput = document.getElementById('mainSearch');
            if (searchInput.value) {
                searchInput.value = '';
                searchInput.dispatchEvent(new Event('input'));
            }
        }
        return;
    }

    // Don't handle other shortcuts if modal is open
    if (document.querySelector('.modal.active')) return;

    // j/k: Navigate conversations
    if ((key === 'j' || key === 'k') && state.currentTab === 'browse') {
        e.preventDefault();
        const items = Array.from(document.querySelectorAll('.conversation-item'));
        const activeIndex = items.findIndex(item => item.classList.contains('active'));

        let nextIndex;
        if (key === 'j') {
            nextIndex = activeIndex < items.length - 1 ? activeIndex + 1 : activeIndex;
        } else {
            nextIndex = activeIndex > 0 ? activeIndex - 1 : 0;
        }

        if (nextIndex >= 0 && nextIndex < items.length) {
            items[nextIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
            items[nextIndex].click();
        }
        return;
    }

    // Enter: Open selected conversation (in search results)
    if (key === 'enter' && state.currentTab === 'search') {
        const firstResult = document.querySelector('.search-result-item');
        if (firstResult) {
            firstResult.click();
        }
        return;
    }

    // Shortcuts that require a current conversation
    if (state.currentConv) {
        // f: Toggle favorite
        if (key === 'f') {
            e.preventDefault();
            state.toggleFavorite(state.currentConv.id);
            renderConversationList();
            showConversation(state.currentConv);
            return;
        }

        // c: Copy conversation
        if (key === 'c' && !ctrl) {
            e.preventDefault();
            copyConversation(state.currentConv.id);
            return;
        }

        // 1-5: Rate conversation
        if (['1', '2', '3', '4', '5'].includes(key)) {
            e.preventDefault();
            const rating = parseInt(key);
            state.setRating(state.currentConv.id, rating);
            showConversation(state.currentConv);
            renderConversationList();
            return;
        }
    }
}

function populateFilters() {
    const sources = [...new Set(CONVERSATIONS.map(c => c.source))].sort();
    const models = [...new Set(CONVERSATIONS.map(c => c.model))].sort();
    const tags = [...new Set(CONVERSATIONS.flatMap(c => c.tags))].sort();

    populateSelect('filterSource', sources);
    populateSelect('filterModel', models);
    populateSelect('filterTag', tags);
}

function populateSelect(id, options) {
    const select = document.getElementById(id);
    options.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt;
        option.textContent = opt;
        select.appendChild(option);
    });
}

function applyPreferences() {
    if (state.preferences.fontSize) {
        document.getElementById('fontSizeSlider').value = state.preferences.fontSize;
        document.getElementById('fontSizeValue').textContent = state.preferences.fontSize + 'px';
        document.documentElement.style.fontSize = state.preferences.fontSize + 'px';
    }
}

// ==================== Search ====================
function handleMainSearch(e) {
    const query = e.target.value.toLowerCase();
    const searchContent = document.getElementById('searchContent').checked;
    const searchTitles = document.getElementById('searchTitles').checked;
    const useRegex = document.getElementById('searchRegex').checked;

    const results = [];

    for (const conv of CONVERSATIONS) {
        let matches = [];

        // Search title
        if (searchTitles && conv.title.toLowerCase().includes(query)) {
            matches.push({ type: 'title', text: conv.title });
        }

        // Search messages
        if (searchContent) {
            for (const msg of conv.messages) {
                if (msg.content.toLowerCase().includes(query)) {
                    matches.push({
                        type: 'message',
                        role: msg.role,
                        text: msg.content,
                        id: msg.id
                    });
                }
            }
        }

        if (matches.length > 0) {
            results.push({ conversation: conv, matches });
        }
    }

    renderSearchResults(results, query);
}

function renderSearchResults(results, query) {
    const container = document.getElementById('searchResults');

    if (!query) {
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">Enter a search query to see results</div>';
        return;
    }

    if (results.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">No results found</div>';
        return;
    }

    container.innerHTML = '';

    for (const result of results) {
        const div = document.createElement('div');
        div.className = 'search-result';

        const title = document.createElement('div');
        title.className = 'search-result-title';
        title.textContent = result.conversation.title;
        div.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'search-result-meta';
        meta.textContent = `${result.conversation.source} • ${result.matches.length} match${result.matches.length > 1 ? 'es' : ''}`;
        div.appendChild(meta);

        const snippet = document.createElement('div');
        snippet.className = 'search-result-snippet';
        const firstMatch = result.matches[0];
        const text = firstMatch.text.substring(0, 200);
        snippet.innerHTML = highlightText(text, query);
        div.appendChild(snippet);

        div.addEventListener('click', () => {
            document.querySelector('[data-tab="browse"]').click();
            showConversation(result.conversation);
        });

        container.appendChild(div);
    }
}

function highlightText(text, query) {
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<span class="highlight">$1</span>');
}

// ==================== Browse ====================
function applyFilters() {
    state.filters = {
        source: document.getElementById('filterSource').value,
        model: document.getElementById('filterModel').value,
        tag: document.getElementById('filterTag').value,
        favorites: document.getElementById('filterFavorites').checked,
        unread: document.getElementById('filterUnread').checked,
        annotated: document.getElementById('filterAnnotated').checked,
        search: document.getElementById('filterSearch').value.toLowerCase()
    };

    renderConversationList();
}

function getFilteredConversations() {
    return CONVERSATIONS.filter(conv => {
        if (state.filters.source && conv.source !== state.filters.source) return false;
        if (state.filters.model && conv.model !== state.filters.model) return false;
        if (state.filters.tag && !conv.tags.includes(state.filters.tag)) return false;
        if (state.filters.favorites && !state.favorites.has(conv.id)) return false;
        if (state.filters.unread && state.readStatus.has(conv.id)) return false;
        if (state.filters.annotated) {
            const hasAnnotation = Object.keys(state.annotations).some(k => k.startsWith(conv.id + ':'));
            if (!hasAnnotation) return false;
        }
        if (state.filters.search && !conv.title.toLowerCase().includes(state.filters.search)) return false;
        return true;
    });
}

function renderConversationList() {
    let filtered = getFilteredConversations();

    // Sort
    filtered.sort((a, b) => {
        switch (state.sort) {
            case 'date':
                return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
            case 'date-asc':
                return new Date(a.updated_at || 0) - new Date(b.updated_at || 0);
            case 'title':
                return a.title.localeCompare(b.title);
            case 'messages':
                return b.message_count - a.message_count;
            case 'rating':
                return (state.ratings[b.id] || 0) - (state.ratings[a.id] || 0);
            default:
                return 0;
        }
    });

    const container = document.getElementById('conversationList');
    container.innerHTML = '';

    filtered.forEach(conv => {
        const item = createConversationItem(conv);
        container.appendChild(item);
    });
}

function createConversationItem(conv) {
    const div = document.createElement('div');
    div.className = 'conversation-item';
    div.dataset.convId = conv.id;
    div.draggable = true;
    if (state.favorites.has(conv.id)) div.classList.add('favorite');
    if (!state.readStatus.has(conv.id)) div.classList.add('unread');
    if (state.currentConv && state.currentConv.id === conv.id) div.classList.add('active');

    const title = document.createElement('div');
    title.className = 'conv-title';
    title.textContent = conv.title;
    div.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'conv-meta';
    meta.textContent = `${conv.message_count} messages • ${conv.source}`;
    div.appendChild(meta);

    const badges = document.createElement('div');
    badges.className = 'conv-badges';
    if (state.ratings[conv.id]) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = '⭐'.repeat(state.ratings[conv.id]);
        badges.appendChild(badge);
    }
    div.appendChild(badges);

    div.addEventListener('click', () => showConversation(conv));

    // Drag and drop handlers
    div.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', conv.id);
        e.dataTransfer.effectAllowed = 'move';
        div.classList.add('dragging');
    });

    div.addEventListener('dragend', () => {
        div.classList.remove('dragging');
    });

    return div;
}

function showConversation(conv) {
    state.currentConv = conv;
    state.markAsRead(conv.id);

    // Update URL hash for deep linking
    updateHash(`conv/${conv.id}`);

    // Update active state - find the item by checking conversation ID
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.remove('active');
    });

    // Mark the correct item as active by finding it in the DOM
    // This works whether called from a click event or programmatically
    setTimeout(() => {
        document.querySelectorAll('.conversation-item').forEach(item => {
            // Check if this item represents the current conversation
            // We'll add a data attribute to help with this
            if (item.dataset.convId === conv.id) {
                item.classList.add('active');
            }
        });
    }, 50);

    const container = document.getElementById('conversationView');
    container.innerHTML = '';

    // Header
    const header = document.createElement('div');
    header.className = 'conversation-header';

    const titleDiv = document.createElement('div');
    titleDiv.className = 'conversation-title';
    titleDiv.innerHTML = `
        ${conv.title}
        <button class="btn btn-secondary" onclick="state.toggleFavorite('${conv.id}'); renderConversationList();">
            ${state.favorites.has(conv.id) ? '⭐' : '☆'}
        </button>
    `;
    header.appendChild(titleDiv);

    const actions = document.createElement('div');
    actions.className = 'conversation-actions';

    // Rating stars
    const ratingDiv = document.createElement('div');
    ratingDiv.className = 'rating';
    const currentRating = state.ratings[conv.id] || 0;
    const stars = [];

    for (let i = 1; i <= 5; i++) {
        const star = document.createElement('span');
        star.className = 'rating-star' + (i <= currentRating ? ' active' : '');
        star.textContent = '★';
        star.dataset.rating = i;

        star.onmouseover = () => {
            stars.forEach((s, idx) => {
                if (idx < i) s.classList.add('active');
                else s.classList.remove('active');
            });
        };

        star.onmouseout = () => {
            stars.forEach((s, idx) => {
                if (idx < currentRating) s.classList.add('active');
                else s.classList.remove('active');
            });
        };

        star.onclick = () => {
            state.setRating(conv.id, i);
            showConversation(conv);
            renderConversationList();
        };

        stars.push(star);
        ratingDiv.appendChild(star);
    }
    actions.appendChild(ratingDiv);

    // Action buttons
    const buttonsDiv = document.createElement('div');
    buttonsDiv.innerHTML = `
        <button class="btn btn-secondary" onclick="addToCollectionPrompt(['${conv.id}'])">Add to Collection</button>
        <button class="btn btn-secondary" onclick="copyConversation('${conv.id}')">Copy</button>
    `;
    actions.appendChild(buttonsDiv);

    header.appendChild(actions);

    container.appendChild(header);

    // Messages
    conv.messages.forEach(msg => {
        const messageDiv = createMessageElement(conv, msg);
        container.appendChild(messageDiv);
    });
}

function createMessageElement(conv, msg) {
    const div = document.createElement('div');
    div.className = `message ${msg.role}`;

    const header = document.createElement('div');
    header.className = 'message-header';

    const role = document.createElement('span');
    role.className = 'message-role';
    role.textContent = msg.role;
    header.appendChild(role);

    const actions = document.createElement('div');
    actions.className = 'message-actions';
    actions.innerHTML = `
        <button class="message-action" onclick="addAnnotation('${conv.id}', '${msg.id}')">📝 Note</button>
        ${msg.has_code ? `<button class="message-action" onclick="extractCode('${conv.id}', '${msg.id}')">💾 Save Code</button>` : ''}
        <button class="message-action" onclick="copyMessage('${msg.id}')">📋 Copy</button>
    `;
    header.appendChild(actions);

    div.appendChild(header);

    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = processMessageContent(msg.content);
    div.appendChild(content);

    // Render LaTeX math after content is in DOM
    setTimeout(() => renderMath(content), 0);

    // Render images if present
    if (msg.images && msg.images.length > 0) {
        const imagesContainer = document.createElement('div');
        imagesContainer.className = 'message-images';

        msg.images.forEach((imageData, index) => {
            const imageWrapper = document.createElement('div');
            imageWrapper.className = 'message-image loading';

            const spinner = document.createElement('div');
            spinner.className = 'spinner';
            imageWrapper.appendChild(spinner);

            const img = document.createElement('img');
            img.loading = 'lazy';

            // Handle both URL and base64 data
            if (imageData.data) {
                img.src = `data:${imageData.mime_type || 'image/png'};base64,${imageData.data}`;
            } else if (imageData.url) {
                img.src = imageData.url;
            }

            img.alt = imageData.caption || 'Image';

            img.onload = () => {
                imageWrapper.classList.remove('loading');
                spinner.remove();
            };

            img.onerror = () => {
                imageWrapper.classList.remove('loading');
                spinner.remove();
                imageWrapper.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary);">⚠️ Failed to load image</div>';
            };

            imageWrapper.appendChild(img);

            // Add caption overlay if present
            if (imageData.caption) {
                const caption = document.createElement('div');
                caption.className = 'message-image-caption';
                caption.textContent = imageData.caption;
                imageWrapper.appendChild(caption);
            }

            // Click to open in lightbox
            imageWrapper.addEventListener('click', () => {
                openLightbox(img.src, imageData.caption);
            });

            imagesContainer.appendChild(imageWrapper);
        });

        div.appendChild(imagesContainer);
    }

    // Show annotation if exists
    const annotationKey = `${conv.id}:${msg.id}`;
    if (state.annotations[annotationKey]) {
        const annotation = document.createElement('div');
        annotation.className = 'message-annotation';
        annotation.textContent = '📝 ' + state.annotations[annotationKey].text;
        div.appendChild(annotation);
    }

    if (msg.timestamp) {
        const timestamp = document.createElement('div');
        timestamp.className = 'message-timestamp';
        timestamp.textContent = new Date(msg.timestamp).toLocaleString();
        div.appendChild(timestamp);
    }

    return div;
}

function renderTimeline() {
    const grouping = document.getElementById('timelineGrouping').value;
    const container = document.getElementById('timelineContent');
    container.innerHTML = '';

    // Get current filters from Browse tab
    const filtered = getFilteredConversations();

    // Group conversations by time period
    const groups = new Map();

    filtered.forEach(conv => {
        const date = new Date(conv.created_at);
        let periodKey;
        let periodLabel;

        switch (grouping) {
            case 'day':
                periodKey = date.toISOString().split('T')[0];
                periodLabel = date.toLocaleDateString('en-US', {
                    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
                });
                break;
            case 'week':
                const weekStart = new Date(date);
                weekStart.setDate(date.getDate() - date.getDay());
                periodKey = weekStart.toISOString().split('T')[0];
                periodLabel = `Week of ${weekStart.toLocaleDateString('en-US', {
                    month: 'long', day: 'numeric', year: 'numeric'
                })}`;
                break;
            case 'month':
                periodKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                periodLabel = date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
                break;
            case 'year':
                periodKey = String(date.getFullYear());
                periodLabel = String(date.getFullYear());
                break;
        }

        if (!groups.has(periodKey)) {
            groups.set(periodKey, { label: periodLabel, conversations: [], key: periodKey });
        }
        groups.get(periodKey).conversations.push(conv);
    });

    // Sort groups by key (descending - most recent first)
    const sortedGroups = Array.from(groups.values()).sort((a, b) =>
        b.key.localeCompare(a.key)
    );

    // Render each group
    sortedGroups.forEach(group => {
        const periodDiv = document.createElement('div');
        periodDiv.className = 'timeline-period';

        const headerDiv = document.createElement('div');
        headerDiv.className = 'timeline-period-header';
        headerDiv.innerHTML = `
            <span class="timeline-period-title">${group.label}</span>
            <span class="timeline-period-count">${group.conversations.length} conversation${group.conversations.length !== 1 ? 's' : ''}</span>
        `;
        periodDiv.appendChild(headerDiv);

        const itemsDiv = document.createElement('div');
        itemsDiv.className = 'timeline-items';

        // Sort conversations within group by date (most recent first)
        group.conversations.sort((a, b) =>
            new Date(b.created_at) - new Date(a.created_at)
        );

        group.conversations.forEach(conv => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'timeline-item';
            if (state.favorites.has(conv.id)) {
                itemDiv.classList.add('favorite');
            }

            const date = new Date(conv.created_at);
            const timeStr = date.toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });

            itemDiv.innerHTML = `
                <div class="timeline-item-title">${conv.title}</div>
                <div class="timeline-item-meta">
                    <span class="timeline-item-date">${timeStr}</span>
                    <span>${conv.message_count} messages</span>
                    <span>${conv.source}</span>
                    ${conv.model ? `<span>${conv.model}</span>` : ''}
                    ${state.ratings[conv.id] ? `<span>${'⭐'.repeat(state.ratings[conv.id])}</span>` : ''}
                </div>
            `;

            itemDiv.onclick = () => {
                document.querySelector('[data-tab="browse"]').click();
                setTimeout(() => showConversation(conv), 100);
            };

            itemsDiv.appendChild(itemDiv);
        });

        periodDiv.appendChild(itemsDiv);
        container.appendChild(periodDiv);
    });

    if (sortedGroups.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">No conversations to display</p>';
    }
}

// ==================== Actions ====================
function toggleTheme() {
    const current = document.body.dataset.theme;
    document.body.dataset.theme = current === 'dark' ? 'light' : 'dark';
}

function openLightbox(src, caption) {
    const lightbox = document.getElementById('lightbox');
    const image = document.getElementById('lightboxImage');
    const captionElement = document.getElementById('lightboxCaption');

    image.src = src;
    captionElement.textContent = caption || '';
    lightbox.classList.add('active');

    // Close on click outside image
    lightbox.onclick = (e) => {
        if (e.target === lightbox) {
            closeLightbox();
        }
    };

    // Close on Escape key
    document.addEventListener('keydown', lightboxKeyHandler);
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('active');
    document.removeEventListener('keydown', lightboxKeyHandler);
}

function lightboxKeyHandler(e) {
    if (e.key === 'Escape') {
        closeLightbox();
    }
}

function showStats() {
    const modal = document.getElementById('statsModal');
    const content = document.getElementById('statsContent');

    const userStats = {
        favorites: state.favorites.size,
        annotations: Object.keys(state.annotations).length,
        collections: state.collections.length,
        snippets: state.snippets.length,
        unread: CONVERSATIONS.length - state.readStatus.size
    };

    content.innerHTML = `
        <h3>Conversation Stats</h3>
        <p>Total: ${STATS.total_conversations}</p>
        <p>Total Messages: ${STATS.total_messages}</p>

        <h3>Your Activity</h3>
        <p>⭐ Favorites: ${userStats.favorites}</p>
        <p>📝 Annotations: ${userStats.annotations}</p>
        <p>📚 Collections: ${userStats.collections}</p>
        <p>💾 Saved Snippets: ${userStats.snippets}</p>
        <p>📖 Unread: ${userStats.unread}</p>
    `;

    modal.classList.add('active');
}

function showSettings() {
    document.getElementById('settingsModal').classList.add('active');
}

function showKeyboardHelp() {
    document.getElementById('keyboardModal').classList.add('active');
}

function addAnnotation(convId, msgId) {
    const modal = document.getElementById('annotationModal');
    const textarea = document.getElementById('annotationText');

    const key = `${convId}:${msgId}`;
    textarea.value = state.annotations[key]?.text || '';

    document.getElementById('saveAnnotation').onclick = () => {
        state.setAnnotation(convId, msgId, textarea.value);
        modal.classList.remove('active');
        showConversation(state.currentConv);
    };

    document.getElementById('deleteAnnotation').onclick = () => {
        state.setAnnotation(convId, msgId, null);
        modal.classList.remove('active');
        showConversation(state.currentConv);
    };

    modal.classList.add('active');
}

function createCollection() {
    const name = prompt('Collection name:');
    if (name) {
        state.addToCollection(name, []);
        renderCollections();
    }
}

function addToCollectionPrompt(convIds) {
    const name = prompt('Add to collection:');
    if (name) {
        state.addToCollection(name, convIds);
        alert('Added to collection!');
    }
}

function renderCollections() {
    const container = document.getElementById('collectionsList');
    container.innerHTML = '';

    if (state.collections.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 3rem; color: var(--text-secondary);">
                <p style="font-size: 1.2rem; margin-bottom: 1rem;">No collections yet</p>
                <p>Create collections to organize your favorite conversations</p>
            </div>
        `;
        return;
    }

    state.collections.forEach((collection, idx) => {
        const div = document.createElement('div');
        div.className = 'collection-card';
        div.dataset.collectionIdx = idx;

        // Make collection card a drop zone
        div.addEventListener('dragover', (e) => {
            e.preventDefault();
            div.classList.add('drag-over');
        });

        div.addEventListener('dragleave', () => {
            div.classList.remove('drag-over');
        });

        div.addEventListener('drop', (e) => {
            e.preventDefault();
            div.classList.remove('drag-over');
            const convId = e.dataTransfer.getData('text/plain');
            if (convId) {
                state.addToCollection(collection.name, [convId]);
                renderCollections();
            }
        });

        // Collection header
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;';

        const title = document.createElement('div');
        title.className = 'collection-title';
        title.textContent = collection.name;
        header.appendChild(title);

        const actions = document.createElement('div');
        actions.style.cssText = 'display: flex; gap: 0.5rem;';
        actions.innerHTML = `
            <button class="btn btn-secondary" onclick="renameCollection(${idx})" title="Rename">✏️</button>
            <button class="btn btn-danger" onclick="deleteCollection(${idx})" title="Delete">🗑️</button>
        `;
        header.appendChild(actions);

        div.appendChild(header);

        // Collection meta
        const meta = document.createElement('div');
        meta.style.cssText = 'font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 1rem;';
        meta.textContent = `${collection.conversations.length} conversations • Created ${new Date(collection.created).toLocaleDateString()}`;
        div.appendChild(meta);

        // Conversations in collection
        if (collection.conversations.length > 0) {
            const convList = document.createElement('div');
            convList.style.cssText = 'display: flex; flex-direction: column; gap: 0.5rem;';

            collection.conversations.forEach(convId => {
                const conv = CONVERSATIONS.find(c => c.id === convId);
                if (!conv) return; // Skip if conversation not found

                const convItem = document.createElement('div');
                convItem.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 4px;';

                const convInfo = document.createElement('div');
                convInfo.style.cssText = 'flex: 1; cursor: pointer;';
                convInfo.innerHTML = `
                    <div style="font-weight: 600; margin-bottom: 0.25rem;">${conv.title}</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary);">${conv.message_count} messages • ${conv.source}</div>
                `;
                convInfo.addEventListener('click', () => {
                    document.querySelector('[data-tab="browse"]').click();
                    setTimeout(() => showConversation(conv), 100);
                });

                const convActions = document.createElement('div');
                convActions.innerHTML = `
                    <button class="btn btn-danger" onclick="removeFromCollection(${idx}, '${convId}')" title="Remove from collection">✕</button>
                `;

                convItem.appendChild(convInfo);
                convItem.appendChild(convActions);
                convList.appendChild(convItem);
            });

            div.appendChild(convList);
        } else {
            const empty = document.createElement('div');
            empty.style.cssText = 'text-align: center; padding: 1rem; color: var(--text-secondary); font-style: italic;';
            empty.textContent = 'No conversations in this collection yet';
            div.appendChild(empty);
        }

        container.appendChild(div);
    });
}

function deleteCollection(index) {
    const collection = state.collections[index];
    if (confirm(`Delete collection "${collection.name}"?`)) {
        state.collections.splice(index, 1);
        state.save('collections');
        renderCollections();
    }
}

function renameCollection(index) {
    const collection = state.collections[index];
    const newName = prompt('Rename collection:', collection.name);
    if (newName && newName !== collection.name) {
        collection.name = newName;
        state.save('collections');
        renderCollections();
    }
}

function removeFromCollection(collectionIndex, convId) {
    const collection = state.collections[collectionIndex];
    collection.conversations = collection.conversations.filter(id => id !== convId);
    state.save('collections');
    renderCollections();
}

function extractCode(convId, msgId) {
    const conv = CONVERSATIONS.find(c => c.id === convId);
    const msg = conv.messages.find(m => m.id === msgId);

    // Extract code blocks
    const codeBlocks = msg.content.match(/```[\\s\\S]*?```/g);
    if (codeBlocks) {
        codeBlocks.forEach(block => {
            const code = block.replace(/```\\w*\\n?/, '').replace(/```$/, '');
            state.saveSnippet(code, 'unknown', `${conv.title} - ${msg.role}`);
        });
        alert('Code saved to snippets!');
    }
}

function renderSnippets() {
    const container = document.getElementById('snippetsList');
    container.innerHTML = '';

    state.snippets.forEach(snippet => {
        const div = document.createElement('div');
        div.className = 'snippet-card';
        div.innerHTML = `
            <p><small>${snippet.source} • ${new Date(snippet.timestamp).toLocaleDateString()}</small></p>
            <pre class="snippet-code">${snippet.code}</pre>
        `;
        container.appendChild(div);
    });
}

// ==================== Media Gallery ====================
function renderMediaGallery() {
    const container = document.getElementById('mediaGallery');
    const searchInput = document.getElementById('mediaSearch');
    const sortSelect = document.getElementById('mediaSort');
    const showCaptionsCheckbox = document.getElementById('showCaptions');

    // Collect all media items from all conversations
    const mediaItems = [];

    CONVERSATIONS.forEach(conv => {
        if (conv.messages) {
            conv.messages.forEach(msg => {
                if (msg.images && msg.images.length > 0) {
                    msg.images.forEach(image => {
                        mediaItems.push({
                            url: image.url,
                            data: image.data,
                            mime_type: image.mime_type || 'image/png',
                            caption: image.caption || '',
                            conversationId: conv.id,
                            conversationTitle: conv.title,
                            messageId: msg.id,
                            timestamp: msg.timestamp || conv.created_at
                        });
                    });
                }
            });
        }
    });

    // Apply search filter
    const searchTerm = searchInput.value.toLowerCase();
    const filteredItems = searchTerm
        ? mediaItems.filter(item =>
            item.caption.toLowerCase().includes(searchTerm) ||
            item.conversationTitle.toLowerCase().includes(searchTerm)
          )
        : mediaItems;

    // Apply sorting
    const sortBy = sortSelect.value;
    filteredItems.sort((a, b) => {
        if (sortBy === 'date') {
            return new Date(b.timestamp) - new Date(a.timestamp);
        } else if (sortBy === 'date-asc') {
            return new Date(a.timestamp) - new Date(b.timestamp);
        } else if (sortBy === 'conversation') {
            return a.conversationTitle.localeCompare(b.conversationTitle);
        }
        return 0;
    });

    // Render gallery
    container.innerHTML = '';

    if (filteredItems.length === 0) {
        container.innerHTML = '<div class="media-empty">No media found</div>';
        return;
    }

    const showCaptions = showCaptionsCheckbox.checked;

    filteredItems.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'media-item';

        const captionHtml = showCaptions && item.caption
            ? `<div class="media-item-caption">${escapeHtml(item.caption)}</div>`
            : '';

        // Use base64 data if available, otherwise fall back to URL
        const imgSrc = item.data
            ? `data:${item.mime_type};base64,${item.data}`
            : item.url;

        div.innerHTML = `
            <img src="${imgSrc}" alt="${escapeHtml(item.caption)}" class="media-item-image">
            <div class="media-item-info">
                ${captionHtml}
                <div class="media-item-meta">
                    <a class="media-item-conversation" data-conv-id="${item.conversationId}">
                        ${escapeHtml(item.conversationTitle.substring(0, 30))}${item.conversationTitle.length > 30 ? '...' : ''}
                    </a>
                    ${item.timestamp ? `<span>${new Date(item.timestamp).toLocaleDateString()}</span>` : ''}
                </div>
            </div>
        `;

        // Click to open in lightbox
        div.querySelector('img').addEventListener('click', () => {
            openLightbox(imgSrc, item.caption);
        });

        // Click conversation link to navigate
        div.querySelector('.media-item-conversation').addEventListener('click', (e) => {
            e.stopPropagation();
            const conv = CONVERSATIONS.find(c => c.id === item.conversationId);
            if (conv) {
                document.querySelector('[data-tab="browse"]').click();
                setTimeout(() => showConversation(conv), 100);
            }
        });

        container.appendChild(div);
    });

    // Setup event listeners for controls (only once)
    if (!searchInput.dataset.listener) {
        searchInput.addEventListener('input', renderMediaGallery);
        sortSelect.addEventListener('change', renderMediaGallery);
        showCaptionsCheckbox.addEventListener('change', renderMediaGallery);
        searchInput.dataset.listener = 'true';
    }
}

function copyMessage(msgId) {
    // Implementation
    alert('Copied!');
}

function copyConversation(convId) {
    const conv = CONVERSATIONS.find(c => c.id === convId);
    if (!conv) return;

    // Copy conversation as formatted text
    let text = `${conv.title}\n${'='.repeat(conv.title.length)}\n\n`;
    conv.messages.forEach(msg => {
        text += `[${msg.role.toUpperCase()}]\n${msg.content}\n\n`;
    });

    navigator.clipboard.writeText(text).then(() => {
        alert('Conversation copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy conversation');
    });
}
"""


    def _get_jsonl_loader(self) -> str:
        """Get JavaScript code to load conversations from JSONL file"""
        return """
// Show loading indicator
const loadingDiv = document.createElement('div');
loadingDiv.id = 'loading-indicator';
loadingDiv.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: var(--bg-primary); padding: 2rem; border-radius: 8px; box-shadow: var(--shadow); z-index: 10000; text-align: center;';
loadingDiv.innerHTML = '<div style="font-size: 1.5rem; margin-bottom: 1rem;">Loading conversations...</div><div id="loading-progress">0 loaded</div>';
document.body.appendChild(loadingDiv);

// Load conversations from JSONL
fetch('conversations.jsonl')
    .then(response => {
        if (!response.ok) {
            throw new Error(`Failed to load conversations.jsonl: ${response.status} ${response.statusText}`);
        }
        return response.text();
    })
    .then(text => {
        const lines = text.trim().split('\\n');
        const progressDiv = document.getElementById('loading-progress');

        lines.forEach((line, index) => {
            if (!line.trim()) return;

            try {
                const obj = JSON.parse(line);

                // Check if this is the stats object
                if (obj.__stats__) {
                    STATS = obj.__stats__;
                } else {
                    CONVERSATIONS.push(obj);

                    // Update progress every 100 conversations
                    if (CONVERSATIONS.length % 100 === 0) {
                        progressDiv.textContent = `${CONVERSATIONS.length} loaded`;
                    }
                }
            } catch (e) {
                console.error('Error parsing JSON line', index + 1, ':', e);
            }
        });

        // Remove loading indicator
        loadingDiv.remove();

        // Initialize the app now that data is loaded
        document.addEventListener('DOMContentLoaded', init);
        if (document.readyState === 'loading') {
            // DOM not ready yet, event listener will fire
        } else {
            // DOM already loaded, call init directly
            init();
        }
    })
    .catch(error => {
        console.error('Error loading conversations:', error);
        loadingDiv.innerHTML = `
            <div style="color: var(--danger); font-size: 1.2rem; margin-bottom: 1rem;">⚠️ Error Loading Data</div>
            <div style="margin-bottom: 1rem;">${error.message}</div>
            <div style="font-size: 0.9rem; color: var(--text-secondary);">
                <p>This HTML file needs to load data from <code>conversations.jsonl</code>.</p>
                <p style="margin-top: 0.5rem;">Make sure:</p>
                <ul style="text-align: left; margin-top: 0.5rem;">
                    <li>Both files are in the same directory</li>
                    <li>You're viewing this via a web server (not file://)</li>
                </ul>
                <p style="margin-top: 1rem;">To serve locally, run: <code>python -m http.server</code></p>
            </div>
        `;
    });
"""


# Register the exporter
exporter = HTMLExporter()

