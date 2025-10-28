#!/usr/bin/env python3
"""
CTK Similarity API - Quick Start Example

This example demonstrates how to use the similarity API to:
1. Embed conversations using TF-IDF
2. Compute similarity between conversations
3. Find similar conversations
4. Build a conversation graph
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ctk.core.database import ConversationDB as Database
from ctk.core.similarity import (
    ConversationEmbedder,
    ConversationEmbeddingConfig,
    SimilarityComputer,
    SimilarityMetric,
    ConversationGraphBuilder,
)
from ctk.integrations.embeddings.tfidf import TFIDFEmbedding


def main():
    # Initialize database
    print("Initializing database...")
    db = Database("conversations")  # Default database path

    # Get all conversations
    conversations = db.list_conversations()
    print(f"Found {len(conversations)} conversations")

    if len(conversations) == 0:
        print("No conversations found. Please import some conversations first.")
        print("Example: ctk import data.json")
        return

    # ====== Step 1: Prepare TF-IDF Embedder ======
    print("\n=== Step 1: Initializing TF-IDF Embedder ===")

    config = ConversationEmbeddingConfig(
        provider="tfidf",
        role_weights={
            "user": 2.0,      # Weight user messages 2x
            "assistant": 1.0,  # Baseline weight
            "system": 0.5,     # System messages less important
        },
        include_title=True,
        include_tags=True,
        title_weight=1.5,
        provider_config={
            "max_features": 5000,   # Vocabulary size
            "ngram_range": [1, 2],  # Unigrams + bigrams
        }
    )

    embedder = ConversationEmbedder(config)
    print(f"Embedder config: {config.provider} with {config.aggregation.value} aggregation")

    # ====== Step 2: Fit TF-IDF on Corpus ======
    print("\n=== Step 2: Fitting TF-IDF on Conversation Corpus ===")

    # Extract all text from conversations
    corpus_texts = []
    conversation_objs = []

    for conv_summary in conversations:
        conv = db.get_conversation(conv_summary.id)
        if conv:
            conversation_objs.append(conv)

            # Extract text from all messages
            text_parts = []
            if conv.title:
                text_parts.append(conv.title)
            if conv.tags:
                text_parts.append(" ".join(conv.tags))

            for msg in conv.messages.values():
                # Extract text content
                if hasattr(msg, 'content') and isinstance(msg.content, str):
                    text_parts.append(msg.content)

            corpus_texts.append(" ".join(text_parts))

    print(f"Fitting TF-IDF on {len(corpus_texts)} conversations...")
    embedder.provider.fit(corpus_texts)
    print(f"Vocabulary size: {embedder.provider.get_dimensions()}")

    # ====== Step 3: Embed All Conversations ======
    print("\n=== Step 3: Embedding All Conversations ===")

    for i, conv in enumerate(conversation_objs):
        if i % 10 == 0:
            print(f"Embedded {i}/{len(conversation_objs)} conversations...", end='\r')

        # Embed conversation (this will cache in database)
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

    print(f"\nEmbedded {len(conversation_objs)} conversations")

    # ====== Step 4: Compute Similarities ======
    print("\n=== Step 4: Computing Similarities ===")

    similarity_computer = SimilarityComputer(
        embedder=embedder,
        metric=SimilarityMetric.COSINE,
        db=db
    )

    # Pick first conversation as query
    if len(conversation_objs) > 0:
        query_conv = conversation_objs[0]
        print(f"\nQuery conversation: {query_conv.id}")
        print(f"Title: {query_conv.title}")

        # Find top 5 similar conversations
        similar = similarity_computer.find_similar(
            query_conv,
            top_k=5,
            threshold=0.1,  # Minimum similarity
            use_cache=True
        )

        print(f"\nTop {len(similar)} similar conversations:")
        for i, result in enumerate(similar, 1):
            # Get conversation details
            similar_conv = db.get_conversation(result.conversation2_id)
            if similar_conv:
                print(f"{i}. [{result.similarity:.3f}] {similar_conv.title}")
                print(f"   ID: {result.conversation2_id}")
                if similar_conv.tags:
                    print(f"   Tags: {', '.join(similar_conv.tags)}")

    # ====== Step 5: Build Conversation Graph ======
    print("\n=== Step 5: Building Conversation Graph ===")

    graph_builder = ConversationGraphBuilder(similarity_computer)

    # Build graph (only for first 50 conversations to keep it fast)
    conv_ids = [c.id for c in conversation_objs[:min(50, len(conversation_objs))]]
    print(f"Building graph for {len(conv_ids)} conversations...")

    graph = graph_builder.build_graph(
        conversations=conv_ids,
        threshold=0.3,  # Minimum similarity for creating link
        max_links_per_node=5,  # Max outgoing links per conversation
        use_cache=True,
        show_progress=False
    )

    print(f"Graph built:")
    print(f"  Nodes: {graph.metadata['total_nodes']}")
    print(f"  Links: {graph.metadata['total_links']}")
    print(f"  Average links per node: {graph.metadata['total_links'] / max(1, graph.metadata['total_nodes']):.1f}")

    # Export graph
    output_path = "conversation_graph.json"
    graph.export_cytoscape(output_path)
    print(f"\nGraph exported to: {output_path}")

    # Optional: Detect communities if we have enough nodes
    if len(conv_ids) >= 10:
        try:
            print("\n=== Detecting Communities ===")
            communities = graph_builder.detect_communities(graph, algorithm="greedy_modularity")
            num_communities = len(set(communities.values()))
            print(f"Found {num_communities} communities")

            # Show community sizes
            from collections import Counter
            comm_sizes = Counter(communities.values())
            print("\nCommunity sizes:")
            for comm_id, size in comm_sizes.most_common(5):
                print(f"  Community {comm_id}: {size} conversations")

        except ImportError as e:
            print(f"Community detection requires python-louvain: {e}")
        except Exception as e:
            print(f"Community detection failed: {e}")

    # ====== Summary ======
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✓ Embedded {len(conversation_objs)} conversations")
    print(f"✓ Computed similarities (cached in database)")
    print(f"✓ Built graph with {graph.metadata['total_links']} links")
    print(f"✓ Exported graph to {output_path}")
    print("\nYou can now:")
    print("  - Use similarity_computer.find_similar() to find related conversations")
    print("  - Query database with db.get_similar_conversations()")
    print("  - Visualize the graph with Cytoscape.js or other tools")


if __name__ == "__main__":
    main()
