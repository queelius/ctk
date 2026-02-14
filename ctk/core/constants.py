"""
Global constants for CTK.

Centralizes magic numbers used across LLM providers, database operations,
and display formatting. Import from here instead of hardcoding values.
"""

# --- Network Timeouts (seconds) ---

DEFAULT_TIMEOUT = 120        # Default LLM chat/stream timeout
HEALTH_CHECK_TIMEOUT = 5     # Quick health/availability check
MODEL_LIST_TIMEOUT = 30      # Listing available models
SHORT_TIMEOUT = 2            # Very short checks (Ollama health)
EMBEDDING_TIMEOUT = 60       # Embedding generation timeout
MIGRATION_LOCK_TIMEOUT = 30.0  # Database migration lock

# --- Database & Query Limits ---

DEFAULT_SEARCH_LIMIT = 1000  # FTS5 search result limit
DEFAULT_TIMELINE_LIMIT = 30  # Timeline query default limit
SEARCH_BUFFER = 100          # Extra records fetched for post-filtering
TITLE_MATCH_BOOST = 10       # Boost factor for title matches in search
AMBIGUITY_CHECK_LIMIT = 2    # Max matches to check for ambiguous IDs

# --- Input Validation Limits ---

MAX_QUERY_LENGTH = 10000     # Maximum search query length
MAX_TITLE_LENGTH = 1000      # Maximum conversation title length
MAX_ID_LENGTH = 200          # Maximum conversation ID length
MAX_RESULT_LIMIT = 10000     # Maximum results per query

# --- Display ---

TITLE_TRUNCATE_WIDTH = 60    # Truncation width for titles in tables
TITLE_TRUNCATE_WIDTH_SHORT = 50  # Shorter truncation width

# --- Estimation ---

CHARS_PER_TOKEN = 4          # Rough characters-per-token estimate
