"""
HTML Exporter - Generate static HTML site for browsing conversations
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from ctk.core.models import ConversationTree
from ctk.core.plugin import ExporterPlugin


class HTMLExporter(ExporterPlugin):
    """Export conversations to a static HTML site"""

    name = "html"
    description = "Export conversations to interactive HTML site"
    version = "1.0.0"

    def validate(self, data: Any) -> bool:
        """HTML is an export-only format"""
        return False

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations to HTML"""
        return self.export_conversations(conversations, **kwargs)

    def export_conversations(
        self,
        conversations: List[ConversationTree],
        include_metadata: bool = True,
        theme: str = 'auto',
        group_by: str = 'date',
        show_tree: bool = True,
        **kwargs
    ) -> str:
        """
        Export conversations to interactive HTML site

        Args:
            conversations: List of conversations to export
            output_path: Path to output HTML file
            include_metadata: Include conversation metadata
            theme: Theme (light, dark, auto)
            group_by: Grouping strategy (date, source, model, tag)
            show_tree: Show conversation tree structure
        """
        # Prepare conversation data for JavaScript
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

            # Update date range
            for msg in all_messages:
                if msg.timestamp:
                    if not stats['date_range']['earliest'] or msg.timestamp < stats['date_range']['earliest']:
                        stats['date_range']['earliest'] = msg.timestamp
                    if not stats['date_range']['latest'] or msg.timestamp > stats['date_range']['latest']:
                        stats['date_range']['latest'] = msg.timestamp

            # Build message tree for display
            for msg in sorted(all_messages, key=lambda m: m.timestamp or datetime.min):
                msg_dict = {
                    'id': msg.id,
                    'role': msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                    'content': msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content),
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'parent_id': msg.parent_id,
                    'has_images': bool(msg.content.images) if hasattr(msg.content, 'images') else False,
                    'has_tools': bool(msg.content.tool_calls) if hasattr(msg.content, 'tool_calls') else False
                }
                messages.append(msg_dict)

            # Gather metadata
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

        # Convert dates to ISO strings for JSON
        if stats['date_range']['earliest']:
            stats['date_range']['earliest'] = stats['date_range']['earliest'].isoformat()
        if stats['date_range']['latest']:
            stats['date_range']['latest'] = stats['date_range']['latest'].isoformat()

        # Generate and return HTML
        return self._generate_html(
            conv_data,
            stats,
            theme=theme,
            group_by=group_by,
            show_tree=show_tree
        )

    def _generate_html(
        self,
        conversations: List[Dict],
        stats: Dict,
        theme: str,
        group_by: str,
        show_tree: bool
    ) -> str:
        """Generate complete HTML document"""

        # Escape JSON for safe embedding in HTML/JavaScript
        conv_json = json.dumps(conversations, ensure_ascii=False, indent=2)
        stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

        # Escape HTML-sensitive characters to prevent breaking the page
        conv_json = conv_json.replace('</script>', '<\\/script>')
        conv_json = conv_json.replace('<!--', '<\\!--')
        stats_json = stats_json.replace('</script>', '<\\/script>')
        stats_json = stats_json.replace('<!--', '<\\!--')

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversation Browser</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body data-theme="{theme}">
    <div class="app-container">
        <!-- Header -->
        <header class="app-header">
            <h1>💬 Conversation Browser</h1>
            <div class="header-controls">
                <button id="statsBtn" class="btn btn-secondary">📊 Statistics</button>
                <button id="themeToggle" class="btn btn-secondary">🌓 Theme</button>
            </div>
        </header>

        <!-- Main Content -->
        <div class="app-main">
            <!-- Sidebar -->
            <aside class="sidebar">
                <div class="sidebar-header">
                    <input type="search" id="searchBox" placeholder="Search conversations..." class="search-input">
                </div>

                <div class="filters">
                    <div class="filter-group">
                        <label>View:</label>
                        <select id="viewMode" class="filter-select">
                            <option value="list">List</option>
                            <option value="timeline" selected>Timeline</option>
                            <option value="tree">Tree View</option>
                        </select>
                    </div>

                    <div class="filter-group">
                        <label>Source:</label>
                        <select id="filterSource" class="filter-select">
                            <option value="">All Sources</option>
                        </select>
                    </div>

                    <div class="filter-group">
                        <label>Model:</label>
                        <select id="filterModel" class="filter-select">
                            <option value="">All Models</option>
                        </select>
                    </div>

                    <div class="filter-group">
                        <label>Tag:</label>
                        <select id="filterTag" class="filter-select">
                            <option value="">All Tags</option>
                        </select>
                    </div>
                </div>

                <div id="conversationList" class="conversation-list"></div>
            </aside>

            <!-- Main Content Area -->
            <main class="content-area">
                <div id="conversationView" class="conversation-view">
                    <div class="welcome-screen">
                        <h2>Welcome to Conversation Browser</h2>
                        <p>Select a conversation from the sidebar to view it.</p>
                        <div class="stats-preview">
                            <div class="stat-box">
                                <div class="stat-value" id="totalConvs">0</div>
                                <div class="stat-label">Conversations</div>
                            </div>
                            <div class="stat-box">
                                <div class="stat-value" id="totalMsgs">0</div>
                                <div class="stat-label">Messages</div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <!-- Statistics Modal -->
    <div id="statsModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>📊 Statistics</h2>
                <button class="modal-close">&times;</button>
            </div>
            <div id="statsContent" class="modal-body"></div>
        </div>
    </div>

    <script>
        // Data
        const CONVERSATIONS = {conv_json};
        const STATS = {stats_json};

        {self._get_javascript(show_tree)}
    </script>
</body>
</html>"""

    def _get_css(self) -> str:
        """Get CSS styles"""
        return """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f5f5f5;
    --bg-tertiary: #e8e8e8;
    --text-primary: #1a1a1a;
    --text-secondary: #666666;
    --border-color: #dddddd;
    --accent-color: #3b82f6;
    --accent-hover: #2563eb;
    --user-bg: #e3f2fd;
    --assistant-bg: #f3e5f5;
    --system-bg: #fff3e0;
    --shadow: 0 2px 8px rgba(0,0,0,0.1);
}

[data-theme="dark"] {
    --bg-primary: #1a1a1a;
    --bg-secondary: #2d2d2d;
    --bg-tertiary: #3a3a3a;
    --text-primary: #e8e8e8;
    --text-secondary: #a8a8a8;
    --border-color: #444444;
    --user-bg: #1e3a5f;
    --assistant-bg: #3d2e4f;
    --system-bg: #4a3c2a;
    --shadow: 0 2px 8px rgba(0,0,0,0.3);
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
}

.app-container {
    height: 100vh;
    display: flex;
    flex-direction: column;
}

.app-header {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.app-header h1 {
    font-size: 1.5rem;
}

.header-controls {
    display: flex;
    gap: 0.5rem;
}

.btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
}

.btn-secondary {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.btn-secondary:hover {
    background: var(--border-color);
}

.app-main {
    flex: 1;
    display: flex;
    overflow: hidden;
}

.sidebar {
    width: 350px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.sidebar-header {
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.search-input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.9rem;
}

.filters {
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.filter-group {
    margin-bottom: 0.75rem;
}

.filter-group label {
    display: block;
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 0.25rem;
}

.filter-select {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.9rem;
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
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
}

.conversation-item:hover {
    border-color: var(--accent-color);
    box-shadow: var(--shadow);
}

.conversation-item.active {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
}

.conversation-item.active .conv-meta {
    color: rgba(255,255,255,0.8);
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

.conv-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.5rem;
}

.tag {
    font-size: 0.75rem;
    padding: 0.2rem 0.5rem;
    background: var(--bg-tertiary);
    border-radius: 3px;
}

.timeline-group {
    margin-bottom: 1.5rem;
}

.timeline-header {
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.5rem 1rem;
    background: var(--bg-tertiary);
    border-radius: 4px;
    margin-bottom: 0.5rem;
    position: sticky;
    top: 0;
    z-index: 10;
}

.content-area {
    flex: 1;
    overflow-y: auto;
    background: var(--bg-primary);
}

.conversation-view {
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem;
}

.welcome-screen {
    text-align: center;
    padding: 4rem 2rem;
}

.welcome-screen h2 {
    margin-bottom: 1rem;
    color: var(--text-primary);
}

.welcome-screen p {
    color: var(--text-secondary);
    margin-bottom: 2rem;
}

.stats-preview {
    display: flex;
    gap: 2rem;
    justify-content: center;
    margin-top: 2rem;
}

.stat-box {
    padding: 1.5rem;
    background: var(--bg-secondary);
    border-radius: 8px;
    min-width: 150px;
}

.stat-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--accent-color);
}

.stat-label {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
}

.conversation-header {
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 2px solid var(--border-color);
}

.conversation-title {
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
}

.conversation-meta {
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.message {
    margin-bottom: 1.5rem;
    padding: 1.25rem;
    border-radius: 8px;
    position: relative;
}

.message.user {
    background: var(--user-bg);
    margin-left: 2rem;
}

.message.assistant {
    background: var(--assistant-bg);
    margin-right: 2rem;
}

.message.system {
    background: var(--system-bg);
    font-size: 0.9rem;
}

.message-role {
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
    opacity: 0.7;
}

.message-content {
    white-space: pre-wrap;
    word-wrap: break-word;
}

.message-timestamp {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
}

.message-badges {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
}

.badge {
    font-size: 0.7rem;
    padding: 0.2rem 0.5rem;
    background: rgba(0,0,0,0.1);
    border-radius: 3px;
}

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

.modal.active {
    display: flex;
}

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
    border-bottom: 1px solid var(--border-color);
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
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}

.stats-section {
    margin-bottom: 2rem;
}

.stats-section h3 {
    margin-bottom: 1rem;
}

.stats-list {
    list-style: none;
}

.stats-list li {
    padding: 0.5rem;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-color);
}

@media (max-width: 768px) {
    .sidebar {
        width: 100%;
        max-width: none;
    }

    .app-main {
        flex-direction: column;
    }

    .message.user, .message.assistant {
        margin-left: 0;
        margin-right: 0;
    }
}
"""

    def _get_javascript(self, show_tree: bool) -> str:
        """Get JavaScript code"""
        return """
// State
let currentConversation = null;
let filteredConversations = [...CONVERSATIONS];
let viewMode = 'timeline';

// Initialize
document.addEventListener('DOMContentLoaded', init);

function init() {
    setupEventListeners();
    populateFilters();
    updateStats();
    renderConversationList();

    // Set initial theme
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = document.body.dataset.theme;
    if (theme === 'auto') {
        document.body.dataset.theme = prefersDark ? 'dark' : 'light';
    }
}

function setupEventListeners() {
    // Search
    document.getElementById('searchBox').addEventListener('input', handleSearch);

    // Filters
    document.getElementById('viewMode').addEventListener('change', handleViewModeChange);
    document.getElementById('filterSource').addEventListener('change', applyFilters);
    document.getElementById('filterModel').addEventListener('change', applyFilters);
    document.getElementById('filterTag').addEventListener('change', applyFilters);

    // Theme toggle
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);

    // Stats modal
    document.getElementById('statsBtn').addEventListener('click', showStats);
    document.querySelector('.modal-close').addEventListener('click', hideStats);
    document.getElementById('statsModal').addEventListener('click', (e) => {
        if (e.target.id === 'statsModal') hideStats();
    });
}

function populateFilters() {
    const sources = Object.keys(STATS.sources).sort();
    const models = Object.keys(STATS.models).sort();
    const tags = Object.keys(STATS.tags).sort();

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

function handleSearch(e) {
    const query = e.target.value.toLowerCase();
    applyFilters();

    if (query) {
        filteredConversations = filteredConversations.filter(conv => {
            return conv.title.toLowerCase().includes(query) ||
                   conv.messages.some(m => m.content.toLowerCase().includes(query));
        });
    }

    renderConversationList();
}

function handleViewModeChange(e) {
    viewMode = e.target.value;
    renderConversationList();
}

function applyFilters() {
    const source = document.getElementById('filterSource').value;
    const model = document.getElementById('filterModel').value;
    const tag = document.getElementById('filterTag').value;

    filteredConversations = CONVERSATIONS.filter(conv => {
        if (source && conv.source !== source) return false;
        if (model && conv.model !== model) return false;
        if (tag && !conv.tags.includes(tag)) return false;
        return true;
    });

    renderConversationList();
}

function renderConversationList() {
    const container = document.getElementById('conversationList');
    container.innerHTML = '';

    if (viewMode === 'timeline') {
        renderTimelineView(container);
    } else if (viewMode === 'tree') {
        renderTreeView(container);
    } else {
        renderListView(container);
    }
}

function renderListView(container) {
    filteredConversations.forEach(conv => {
        container.appendChild(createConversationItem(conv));
    });
}

function renderTimelineView(container) {
    // Group by date
    const groups = {};
    filteredConversations.forEach(conv => {
        if (!conv.created_at) return;
        const date = new Date(conv.created_at);
        const key = date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        if (!groups[key]) groups[key] = [];
        groups[key].push(conv);
    });

    // Sort groups by date (newest first)
    const sortedKeys = Object.keys(groups).sort((a, b) => {
        return new Date(groups[b][0].created_at) - new Date(groups[a][0].created_at);
    });

    sortedKeys.forEach(key => {
        const group = document.createElement('div');
        group.className = 'timeline-group';

        const header = document.createElement('div');
        header.className = 'timeline-header';
        header.textContent = key;
        group.appendChild(header);

        groups[key].forEach(conv => {
            group.appendChild(createConversationItem(conv));
        });

        container.appendChild(group);
    });
}

function renderTreeView(container) {
    // Group by source
    const groups = {};
    filteredConversations.forEach(conv => {
        const source = conv.source || 'Unknown';
        if (!groups[source]) groups[source] = [];
        groups[source].push(conv);
    });

    Object.keys(groups).sort().forEach(source => {
        const group = document.createElement('div');
        group.className = 'timeline-group';

        const header = document.createElement('div');
        header.className = 'timeline-header';
        header.textContent = `${source} (${groups[source].length})`;
        group.appendChild(header);

        groups[source].forEach(conv => {
            group.appendChild(createConversationItem(conv));
        });

        container.appendChild(group);
    });
}

function createConversationItem(conv) {
    const item = document.createElement('div');
    item.className = 'conversation-item';
    if (currentConversation && currentConversation.id === conv.id) {
        item.classList.add('active');
    }

    const title = document.createElement('div');
    title.className = 'conv-title';
    title.textContent = conv.title;
    item.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'conv-meta';
    meta.textContent = `${conv.message_count} messages • ${conv.source}`;
    if (conv.model && conv.model !== 'Unknown') {
        meta.textContent += ` • ${conv.model}`;
    }
    item.appendChild(meta);

    if (conv.tags && conv.tags.length > 0) {
        const tags = document.createElement('div');
        tags.className = 'conv-tags';
        conv.tags.slice(0, 3).forEach(tag => {
            const tagEl = document.createElement('span');
            tagEl.className = 'tag';
            tagEl.textContent = tag;
            tags.appendChild(tagEl);
        });
        item.appendChild(tags);
    }

    item.addEventListener('click', () => showConversation(conv));

    return item;
}

function showConversation(conv) {
    currentConversation = conv;

    // Update active state
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.remove('active');
    });
    event.currentTarget.classList.add('active');

    // Render conversation
    const container = document.getElementById('conversationView');
    container.innerHTML = '';

    // Header
    const header = document.createElement('div');
    header.className = 'conversation-header';

    const title = document.createElement('h2');
    title.className = 'conversation-title';
    title.textContent = conv.title;
    header.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'conversation-meta';
    let metaText = `${conv.message_count} messages`;
    if (conv.created_at) {
        const date = new Date(conv.created_at);
        metaText += ` • Created ${date.toLocaleDateString()}`;
    }
    metaText += ` • ${conv.source}`;
    if (conv.model && conv.model !== 'Unknown') {
        metaText += ` • ${conv.model}`;
    }
    meta.textContent = metaText;
    header.appendChild(meta);

    container.appendChild(header);

    // Messages
    conv.messages.forEach(msg => {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${msg.role}`;

        const role = document.createElement('div');
        role.className = 'message-role';
        role.textContent = msg.role;
        messageEl.appendChild(role);

        const content = document.createElement('div');
        content.className = 'message-content';
        content.textContent = msg.content;
        messageEl.appendChild(content);

        if (msg.has_images || msg.has_tools) {
            const badges = document.createElement('div');
            badges.className = 'message-badges';
            if (msg.has_images) {
                const badge = document.createElement('span');
                badge.className = 'badge';
                badge.textContent = '🖼️ Has images';
                badges.appendChild(badge);
            }
            if (msg.has_tools) {
                const badge = document.createElement('span');
                badge.className = 'badge';
                badge.textContent = '🛠️ Tool calls';
                badges.appendChild(badge);
            }
            messageEl.appendChild(badges);
        }

        if (msg.timestamp) {
            const timestamp = document.createElement('div');
            timestamp.className = 'message-timestamp';
            const date = new Date(msg.timestamp);
            timestamp.textContent = date.toLocaleString();
            messageEl.appendChild(timestamp);
        }

        container.appendChild(messageEl);
    });
}

function toggleTheme() {
    const current = document.body.dataset.theme;
    document.body.dataset.theme = current === 'dark' ? 'light' : 'dark';
}

function updateStats() {
    document.getElementById('totalConvs').textContent = STATS.total_conversations;
    document.getElementById('totalMsgs').textContent = STATS.total_messages;
}

function showStats() {
    const modal = document.getElementById('statsModal');
    const content = document.getElementById('statsContent');

    content.innerHTML = `
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-value">${STATS.total_conversations}</div>
                <div class="stat-label">Total Conversations</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">${STATS.total_messages}</div>
                <div class="stat-label">Total Messages</div>
            </div>
        </div>

        <div class="stats-section">
            <h3>Sources</h3>
            <ul class="stats-list">
                ${Object.entries(STATS.sources).map(([k, v]) =>
                    `<li><span>${k}</span><span>${v}</span></li>`
                ).join('')}
            </ul>
        </div>

        <div class="stats-section">
            <h3>Models</h3>
            <ul class="stats-list">
                ${Object.entries(STATS.models).slice(0, 10).map(([k, v]) =>
                    `<li><span>${k}</span><span>${v}</span></li>`
                ).join('')}
            </ul>
        </div>

        ${Object.keys(STATS.tags).length > 0 ? `
        <div class="stats-section">
            <h3>Top Tags</h3>
            <ul class="stats-list">
                ${Object.entries(STATS.tags).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k, v]) =>
                    `<li><span>${k}</span><span>${v}</span></li>`
                ).join('')}
            </ul>
        </div>
        ` : ''}
    `;

    modal.classList.add('active');
}

function hideStats() {
    document.getElementById('statsModal').classList.remove('active');
}
"""
