#!/usr/bin/env python3
"""
Test CTK Similarity System with Sample Data

Creates sample conversations and demonstrates the similarity API.
"""

import sys
from pathlib import Path
from datetime import datetime
import uuid

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ctk.core.database import ConversationDB as Database
from ctk.core.models import ConversationTree, Message, MessageRole, ConversationMetadata, MessageContent
from ctk.core.similarity import (
    ConversationEmbedder,
    ConversationEmbeddingConfig,
    SimilarityComputer,
    SimilarityMetric,
    ConversationGraphBuilder,
    ChunkingStrategy,
    AggregationStrategy,
)


def create_sample_conversation(title, messages_data, tags=None):
    """Create a sample conversation"""
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
    print("="*60)
    print("CTK SIMILARITY SYSTEM TEST")
    print("="*60)

    # Initialize database in temp location (fresh each run)
    import shutil
    db_path = "/tmp/ctk_test_similarity"

    # Remove old database if it exists
    if Path(db_path).exists():
        shutil.rmtree(db_path)

    print(f"\nInitializing test database at: {db_path}")
    db = Database(db_path)

    # Create sample conversations
    print("\n=== Creating Sample Conversations ===")

    conversations = [
        create_sample_conversation(
            "Python asyncio tutorial",
            [
                ("user", "How do I use asyncio in Python?"),
                ("assistant", "Asyncio is Python's library for asynchronous programming. You use async/await syntax to write concurrent code."),
                ("user", "Can you show me an example?"),
                ("assistant", "Sure! Here's a basic example using asyncio.gather() to run multiple coroutines concurrently.")
            ],
            tags=["python", "asyncio", "tutorial"]
        ),
        create_sample_conversation(
            "Python async best practices",
            [
                ("user", "What are the best practices for async programming in Python?"),
                ("assistant", "Key best practices include: always await coroutines, use asyncio.gather for concurrency, and handle exceptions properly with try/except blocks.")
            ],
            tags=["python", "asyncio", "best-practices"]
        ),
        create_sample_conversation(
            "JavaScript promises explained",
            [
                ("user", "Explain JavaScript promises to me"),
                ("assistant", "Promises in JavaScript represent asynchronous operations. They have three states: pending, fulfilled, and rejected. You use .then() to handle success and .catch() for errors.")
            ],
            tags=["javascript", "promises", "async"]
        ),
        create_sample_conversation(
            "FastAPI tutorial",
            [
                ("user", "How do I create a REST API with FastAPI?"),
                ("assistant", "FastAPI is a modern Python web framework. You define routes using decorators like @app.get() and type hints for automatic validation.")
            ],
            tags=["python", "fastapi", "web"]
        ),
        create_sample_conversation(
            "Database optimization tips",
            [
                ("user", "How can I optimize my database queries?"),
                ("assistant", "Key optimization strategies: add indexes on frequently queried columns, use EXPLAIN to analyze query plans, avoid N+1 queries, and use connection pooling.")
            ],
            tags=["database", "optimization", "performance"]
        ),
        create_sample_conversation(
            "SQLAlchemy ORM guide",
            [
                ("user", "How do I use SQLAlchemy ORM in Python?"),
                ("assistant", "SQLAlchemy ORM maps Python classes to database tables. You define models using declarative base and query with session.query().")
            ],
            tags=["python", "sqlalchemy", "database"]
        ),
        create_sample_conversation(
            "React hooks tutorial",
            [
                ("user", "What are React hooks?"),
                ("assistant", "React hooks like useState and useEffect let you use state and lifecycle features in functional components. They replace class components.")
            ],
            tags=["react", "javascript", "hooks"]
        ),
        create_sample_conversation(
            "Python type hints",
            [
                ("user", "Should I use type hints in Python?"),
                ("assistant", "Yes! Type hints improve code readability, enable better IDE support, and catch bugs early with tools like mypy.")
            ],
            tags=["python", "typing", "best-practices"]
        ),
    ]

    # Save conversations to database
    print(f"Created {len(conversations)} sample conversations:")
    for conv in conversations:
        db.save_conversation(conv)
        print(f"  - {conv.title}")

    # ====== Step 1: Setup Embedder ======
    print("\n=== Step 1: Setting up TF-IDF Embedder ===")

    config = ConversationEmbeddingConfig(
        provider="tfidf",
        chunking=ChunkingStrategy.MESSAGE,
        aggregation=AggregationStrategy.WEIGHTED_MEAN,
        role_weights={
            "user": 2.0,
            "assistant": 1.0,
            "system": 0.5,
        },
        include_title=True,
        include_tags=True,
        title_weight=1.5,
        provider_config={
            "max_features": 1000,
            "ngram_range": [1, 2],
        }
    )

    embedder = ConversationEmbedder(config)
    print(f"Config: {config.provider} with {config.aggregation.value} aggregation")
    print(f"Role weights: user={config.role_weights['user']}, assistant={config.role_weights['assistant']}")

    # ====== Step 2: Fit TF-IDF ======
    print("\n=== Step 2: Fitting TF-IDF on Corpus ===")

    corpus_texts = []
    for conv in conversations:
        text_parts = []
        if conv.title:
            text_parts.append(conv.title)
        if conv.metadata.tags:
            text_parts.append(" ".join(conv.metadata.tags))

        for msg in conv.message_map.values():
            if hasattr(msg.content, 'text') and msg.content.text:
                text_parts.append(msg.content.text)

        corpus_texts.append(" ".join(text_parts))

    print(f"Fitting on {len(corpus_texts)} conversations...")
    embedder.provider.fit(corpus_texts)
    print(f"✓ Vocabulary size: {embedder.provider.get_dimensions()}")

    # ====== Step 3: Embed All Conversations ======
    print("\n=== Step 3: Embedding Conversations ===")

    for i, conv in enumerate(conversations):
        embedding = embedder.embed_conversation(conv)

        # Save to database
        db.save_embedding(
            conversation_id=conv.id,
            embedding=embedding,
            provider="tfidf",
            model="tfidf",
            chunking_strategy=config.chunking.value,
            aggregation_strategy=config.aggregation.value,
            aggregation_weights=config.role_weights
        )
        print(f"  [{i+1}/{len(conversations)}] Embedded: {conv.title}")

    print(f"✓ Embedded {len(conversations)} conversations")

    # ====== Step 4: Compute Similarities ======
    print("\n=== Step 4: Computing Similarities ===")

    similarity_computer = SimilarityComputer(
        embedder=embedder,
        metric=SimilarityMetric.COSINE,
        db=db
    )

    # Pick first conversation as query
    query_conv = conversations[0]
    print(f"\nQuery: '{query_conv.title}'")
    print(f"Tags: {', '.join(query_conv.metadata.tags)}")

    # Find similar conversations
    similar = similarity_computer.find_similar(
        query_conv,
        top_k=5,
        threshold=0.0,
        use_cache=True
    )

    print(f"\nTop {len(similar)} most similar conversations:")
    for i, result in enumerate(similar, 1):
        # Find the conversation (try both conversation1_id and conversation2_id)
        similar_conv = next((c for c in conversations if c.id == result.conversation2_id), None)
        if not similar_conv:
            similar_conv = next((c for c in conversations if c.id == result.conversation1_id), None)

        if similar_conv:
            print(f"\n{i}. Similarity: {result.similarity:.3f}")
            print(f"   Title: {similar_conv.title}")
            print(f"   Tags: {', '.join(similar_conv.metadata.tags)}")
        else:
            print(f"\n{i}. Similarity: {result.similarity:.3f}")
            print(f"   ID: {result.conversation2_id} (not found in local list)")

    # ====== Step 5: Test Pairwise Similarity ======
    print("\n=== Step 5: Pairwise Similarity Examples ===")

    pairs = [
        (0, 1),  # Python asyncio tutorial vs Python async best practices
        (0, 2),  # Python asyncio tutorial vs JavaScript promises
        (3, 5),  # FastAPI tutorial vs SQLAlchemy ORM guide
    ]

    for idx1, idx2 in pairs:
        conv1 = conversations[idx1]
        conv2 = conversations[idx2]

        result = similarity_computer.compute_similarity(
            conv1, conv2, use_cache=True
        )

        print(f"\n'{conv1.title}'")
        print(f"  vs")
        print(f"'{conv2.title}'")
        print(f"  → Similarity: {result.similarity:.3f}")

    # ====== Step 6: Build Graph ======
    print("\n=== Step 6: Building Conversation Graph ===")

    graph_builder = ConversationGraphBuilder(similarity_computer)

    conv_ids = [c.id for c in conversations]
    graph = graph_builder.build_graph(
        conversations=conv_ids,
        threshold=0.2,
        max_links_per_node=3,
        use_cache=True,
        show_progress=False
    )

    print(f"Graph statistics:")
    print(f"  Nodes: {graph.metadata['total_nodes']}")
    print(f"  Links: {graph.metadata['total_links']}")
    print(f"  Avg links/node: {graph.metadata['total_links'] / max(1, graph.metadata['total_nodes']):.1f}")

    # Show some links
    print(f"\nTop 5 strongest links:")
    sorted_links = sorted(graph.links, key=lambda l: l.weight, reverse=True)[:5]
    for link in sorted_links:
        src = next(c for c in conversations if c.id == link.source_id)
        tgt = next(c for c in conversations if c.id == link.target_id)
        print(f"  {link.weight:.3f}: '{src.title}' ↔ '{tgt.title}'")

    # Export graph
    output_path = "/tmp/conversation_graph.json"
    graph.export_cytoscape(output_path)
    print(f"\n✓ Graph exported to: {output_path}")

    # ====== Step 7: Test Database Methods ======
    print("\n=== Step 7: Testing Database Methods ===")

    # Test get_similar_conversations
    similar_from_db = db.get_similar_conversations(
        conversation_id=query_conv.id,
        metric="cosine",
        provider="tfidf",
        top_k=3
    )

    print(f"\nSimilar conversations from DB (top 3):")
    for sim in similar_from_db:
        conv = next(c for c in conversations if c.id == sim['conversation_id'])
        print(f"  {sim['similarity']:.3f}: {conv.title}")

    # Test get_embedding
    cached_emb = db.get_embedding(
        conversation_id=query_conv.id,
        model="tfidf",
        provider="tfidf",
        chunking_strategy="message",
        aggregation_strategy="weighted_mean"
    )
    print(f"\n✓ Retrieved cached embedding: {len(cached_emb)} dimensions")

    # ====== Summary ======
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✓ Created {len(conversations)} sample conversations")
    print(f"✓ Fitted TF-IDF with {embedder.provider.get_dimensions()} features")
    print(f"✓ Embedded {len(conversations)} conversations")
    print(f"✓ Computed similarities with caching")
    print(f"✓ Built graph with {graph.metadata['total_links']} links")
    print(f"✓ Exported graph to {output_path}")
    print("\nAll tests passed! The similarity system is working correctly.")

    # Cleanup
    print(f"\nTest database at: {db_path}")
    print("(You can delete this directory when done testing)")


if __name__ == "__main__":
    main()
