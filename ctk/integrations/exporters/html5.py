"""
HTML5 Advanced Exporter - Interactive browser-based conversation viewer with localStorage
"""

import json
from datetime import datetime
from typing import List, Dict, Any
from ctk.core.models import ConversationTree
from ctk.core.plugin import ExporterPlugin


class HTML5Exporter(ExporterPlugin):
    """Export conversations to advanced HTML5 app with localStorage features"""

    name = "html5"
    description = "Export to advanced HTML5 app with annotations, bookmarks, and more"
    version = "1.0.0"

    def validate(self, data: Any) -> bool:
        """HTML5 is an export-only format"""
        return False

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations to HTML5"""
        return self.export_conversations(conversations, **kwargs)

    def export_conversations(
        self,
        conversations: List[ConversationTree],
        include_metadata: bool = True,
        theme: str = 'auto',
        **kwargs
    ) -> str:
        """
        Export conversations to advanced HTML5 application

        Args:
            conversations: List of conversations to export
            include_metadata: Include conversation metadata
            theme: Theme (light, dark, auto)
        """
        # Prepare conversation data
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

                msg_dict = {
                    'id': msg.id,
                    'role': msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                    'content': msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content),
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'parent_id': msg.parent_id,
                    'has_code': '```' in (msg.content.get_text() if hasattr(msg.content, 'get_text') else ''),
                    'has_images': bool(msg.content.images) if hasattr(msg.content, 'images') else False,
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

        return self._generate_html(conv_data, stats, theme)

    def _generate_html(self, conversations: List[Dict], stats: Dict, theme: str) -> str:
        """Generate complete HTML5 document"""

        conv_json = json.dumps(conversations, ensure_ascii=False, indent=2)
        stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

        # Escape for safe embedding
        conv_json = conv_json.replace('</script>', '<\\/script>').replace('<!--', '<\\!--')
        stats_json = stats_json.replace('</script>', '<\\/script>').replace('<!--', '<\\!--')

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversation Browser Plus</title>
    <style>{self._get_css()}</style>
</head>
<body data-theme="{theme}">
    <div class="app">
        <!-- Header -->
        <header class="header">
            <h1>💬 Conversation Browser <span class="plus">Plus</span></h1>
            <div class="header-actions">
                <button id="statsBtn" class="btn btn-secondary">📊 Stats</button>
                <button id="settingsBtn" class="btn btn-secondary">⚙️</button>
                <button id="themeBtn" class="btn btn-secondary">🌓</button>
            </div>
        </header>

        <!-- Tabs -->
        <div class="tabs">
            <button class="tab active" data-tab="search">🔍 Search</button>
            <button class="tab" data-tab="browse">📚 Browse</button>
            <button class="tab" data-tab="timeline">📅 Timeline</button>
            <button class="tab" data-tab="collections">⭐ Collections</button>
            <button class="tab" data-tab="snippets">💾 Code Snippets</button>
        </div>

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
                <aside class="sidebar">
                    <div class="sidebar-controls">
                        <input type="search" id="filterSearch" placeholder="Filter..." class="filter-input">

                        <details class="filter-section" open>
                            <summary>Filters</summary>
                            <label>Source: <select id="filterSource"><option value="">All</option></select></label>
                            <label>Model: <select id="filterModel"><option value="">All</option></select></label>
                            <label>Tag: <select id="filterTag"><option value="">All</option></select></label>
                            <label><input type="checkbox" id="filterFavorites"> ⭐ Favorites only</label>
                            <label><input type="checkbox" id="filterUnread"> 📖 Unread only</label>
                            <label><input type="checkbox" id="filterAnnotated"> 📝 With notes</label>
                        </details>

                        <details class="filter-section">
                            <summary>Sort</summary>
                            <label><input type="radio" name="sort" value="date" checked> Latest first</label>
                            <label><input type="radio" name="sort" value="date-asc"> Oldest first</label>
                            <label><input type="radio" name="sort" value="title"> Title A-Z</label>
                            <label><input type="radio" name="sort" value="messages"> Most messages</label>
                            <label><input type="radio" name="sort" value="rating"> Highest rated</label>
                        </details>
                    </div>
                    <div id="favoritesDropZone" class="drop-zone">
                        ⭐ Drop here to favorite
                    </div>
                    <div id="conversationList" class="conversation-list"></div>
                </aside>

                <main class="main-content">
                    <div id="conversationView"></div>
                </main>
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
    </div>

    <script>
        const CONVERSATIONS = {conv_json};
        const STATS = {stats_json};
        {self._get_javascript()}
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
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header h1 { font-size: 1.5rem; }
.header h1 .plus { color: var(--accent); font-weight: 700; }

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
    background: var(--bg-secondary);
    border-bottom: 2px solid var(--border);
    padding: 0 1.5rem;
}

.tab {
    padding: 0.75rem 1.5rem;
    border: none;
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.95rem;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
}

.tab:hover { color: var(--text-primary); }
.tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
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
    height: 100%;
}

.sidebar {
    width: 350px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
}

.sidebar-controls {
    padding: 1rem;
    border-bottom: 1px solid var(--border);
}

.filter-input {
    width: 100%;
    padding: 0.5rem;
    margin-bottom: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
}

.filter-section {
    margin-bottom: 0.75rem;
}

.filter-section summary {
    cursor: pointer;
    font-weight: 600;
    padding: 0.5rem;
    border-radius: 4px;
}

.filter-section summary:hover { background: var(--bg-tertiary); }

.filter-section label {
    display: block;
    padding: 0.4rem 1rem;
    font-size: 0.9rem;
}

.filter-section select,
.filter-section input[type="number"] {
    width: 100%;
    padding: 0.25rem;
    margin-top: 0.25rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
}

.conversation-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
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

.main-content {
    flex: 1;
    overflow-y: auto;
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
    .sidebar { width: 100%; max-width: none; }
    .browse-view { flex-direction: column; }
    .message.user, .message.assistant { margin-left: 0; margin-right: 0; }
}

@media print {
    /* Hide UI elements */
    .header,
    .tabs,
    .sidebar,
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

    .main-content {
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
    document.querySelectorAll('input[name="sort"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            state.sort = e.target.value;
            renderConversationList();
        });
    });

    // Timeline
    document.getElementById('timelineGrouping').addEventListener('change', renderTimeline);

    // Header actions
    document.getElementById('themeBtn').addEventListener('click', toggleTheme);
    document.getElementById('statsBtn').addEventListener('click', showStats);
    document.getElementById('settingsBtn').addEventListener('click', showSettings);

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
    content.textContent = msg.content;
    div.appendChild(content);

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
