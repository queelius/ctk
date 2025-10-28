#!/usr/bin/env python3
"""
Test /rag commands in TUI programmatically
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ctk.core.database import ConversationDB as Database
from ctk.core.models import ConversationTree, Message, MessageRole, ConversationMetadata, MessageContent
from datetime import datetime
import uuid

def create_test_conversation(title, messages_data, tags=None):
    """Create a test conversation"""
    conv = ConversationTree(
        id=f"test_{uuid.uuid4().hex[:8]}",
        title=title,
        metadata=ConversationMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=tags or []
        )
    )

    for role, content in messages_data:
        msg = Message(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            role=MessageRole.from_string(role),
            content=MessageContent(text=content),
            timestamp=datetime.now()
        )
        conv.add_message(msg)

    return conv

def main():
    print("Setting up test database for TUI RAG commands...")

    # Use the test database
    db_path = "/tmp/ctk_test_rag_tui"

    # Clean up if exists
    import shutil
    if Path(db_path).exists():
        shutil.rmtree(db_path)

    db = Database(db_path)

    # Create test conversations
    conversations = [
        create_test_conversation(
            "Python async programming",
            [
                ("user", "How do I use async/await in Python?"),
                ("assistant", "Async/await allows you to write concurrent code using coroutines."),
            ],
            tags=["python", "async"]
        ),
        create_test_conversation(
            "JavaScript promises",
            [
                ("user", "Explain JavaScript promises"),
                ("assistant", "Promises represent asynchronous operations in JavaScript."),
            ],
            tags=["javascript", "async"]
        ),
        create_test_conversation(
            "Python FastAPI tutorial",
            [
                ("user", "How do I build a REST API with FastAPI?"),
                ("assistant", "FastAPI is a modern Python web framework for building APIs."),
            ],
            tags=["python", "web", "api"]
        ),
    ]

    for conv in conversations:
        db.save_conversation(conv)
        print(f"  Saved: {conv.title}")

    print(f"\n✓ Created test database at: {db_path}")
    print(f"✓ Added {len(conversations)} conversations")
    print("\nNow you can test /rag commands in TUI:")
    print(f"  ctk chat --db {db_path}")
    print("\nThen try:")
    print("  /rag embeddings")
    print("  /list")
    print("  /rag similar <conversation_id>")
    print("\nExample workflow:")
    print("  1. /rag embeddings              # Generate embeddings")
    print("  2. /list                        # Get conversation IDs")
    print("  3. /rag similar test_XXXXXXXX   # Find similar to first conversation")

if __name__ == "__main__":
    main()
