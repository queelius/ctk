"""
Semantic search and index command handlers

Implements: semantic (search, similar), index (build, status, clear)
"""

import logging
from typing import Callable, Dict, List, Optional

import numpy as np

from ctk.core.command_dispatcher import CommandResult
from ctk.core.database import ConversationDB
from ctk.core.similarity import cosine_similarity, extract_conversation_text
from ctk.core.vfs import VFSPathParser
from ctk.core.vfs_navigator import VFSNavigator

logger = logging.getLogger(__name__)


class SemanticCommands:
    """Handler for semantic search commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize semantic command handlers.

        Args:
            db: Database instance
            navigator: VFS navigator for path resolution
            tui_instance: Optional TUI instance for current path state
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_semantic(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Semantic search and similarity commands.

        Usage:
            semantic search <query>    - Search by meaning using TF-IDF embeddings
            semantic similar <id>      - Find conversations similar to given ID
            semantic similar .         - Similar to current conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with search results
        """
        if not args:
            return CommandResult(
                success=False,
                output="",
                error=(
                    "Usage: semantic search <query> | semantic similar <id>\n"
                    "  semantic search <query>  - Search by meaning\n"
                    "  semantic similar <id>    - Find similar conversations\n"
                    "  semantic similar .       - Similar to current conversation"
                ),
            )

        subcommand = args[0].lower()

        if subcommand == "search":
            return self._semantic_search(args[1:])
        elif subcommand == "similar":
            return self._semantic_similar(args[1:])
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"semantic: unknown subcommand: {subcommand}",
            )

    def _semantic_search(self, args: List[str]) -> CommandResult:
        """
        Search conversations by meaning using TF-IDF embeddings.

        Args:
            args: Query terms

        Returns:
            CommandResult with matching conversations
        """
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="semantic search: query required",
            )

        query = " ".join(args)

        # Check if embeddings exist
        embeddings = self.db.get_all_embeddings(provider="tfidf")
        if not embeddings:
            return CommandResult(
                success=True,
                output="No embeddings found. Run 'index build' first.",
            )

        try:
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding

            # Re-fit TF-IDF on corpus so we can embed the query in the same space
            texts = self._get_corpus_texts(embeddings)
            tfidf = TFIDFEmbedding({})
            tfidf.fit(texts)

            # Embed the query using the re-fit vectorizer, then compare against
            # stored embeddings. Note: stored embeddings were built from the same
            # corpus via 'index build', so re-fitting on the same texts produces
            # the same vector space.
            query_response = tfidf.embed(query)
            query_vec = np.array(query_response.embedding)

            # Compare against all embedded conversations
            results = []
            for emb_dict in embeddings:
                conv_id = emb_dict["conversation_id"]
                emb_vec = np.array(emb_dict["embedding"])

                score = cosine_similarity(query_vec, emb_vec)
                if score > 0.0:
                    results.append((conv_id, score))

            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)

            if not results:
                return CommandResult(
                    success=True,
                    output="No matching conversations found.",
                )

            # Format output
            lines = []
            for conv_id, score in results[:10]:
                conv = self.db.load_conversation(conv_id)
                title = conv.title if conv else "Untitled"
                short_id = conv_id[:8]
                lines.append(f"{score:.3f}  {short_id}  {title}")

            output = "\n".join(lines) + "\n"
            return CommandResult(success=True, output=output)

        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"semantic search: {str(e)}",
            )

    def _semantic_similar(self, args: List[str]) -> CommandResult:
        """
        Find conversations similar to a given conversation.

        Args:
            args: Conversation ID or '.' for current

        Returns:
            CommandResult with similar conversations
        """
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="semantic similar: conversation ID required (or '.' for current)",
            )

        identifier = args[0]

        # Resolve '.' to current conversation
        if identifier == ".":
            conv_id = self._resolve_current_conversation()
            if not conv_id:
                return CommandResult(
                    success=False,
                    output="",
                    error="semantic similar: not in a conversation directory",
                )
        else:
            # Resolve identifier to full ID
            resolved = self.db.resolve_identifier(identifier)
            if not resolved:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"semantic similar: conversation not found: {identifier}",
                )
            conv_id = resolved[0]

        # Check if embeddings exist
        embeddings = self.db.get_all_embeddings(provider="tfidf")
        if not embeddings:
            return CommandResult(
                success=True,
                output="No embeddings found. Run 'index build' first.",
            )

        # Check if the target conversation has an embedding
        target_emb = None
        for emb_dict in embeddings:
            if emb_dict["conversation_id"] == conv_id:
                target_emb = emb_dict
                break

        if not target_emb:
            return CommandResult(
                success=True,
                output=(
                    f"No embedding for conversation {conv_id[:8]}. "
                    "Run 'index build' to generate embeddings."
                ),
            )

        try:
            target_vec = np.array(target_emb["embedding"])

            # Compare against all other stored embeddings using cosine similarity
            results = []
            for emb_dict in embeddings:
                other_id = emb_dict["conversation_id"]
                if other_id == conv_id:
                    continue

                other_vec = np.array(emb_dict["embedding"])
                score = cosine_similarity(target_vec, other_vec)
                if score > 0.0:
                    results.append((other_id, score))

            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)

            if not results:
                return CommandResult(
                    success=True,
                    output="No similar conversations found.",
                )

            # Format output
            conv = self.db.load_conversation(conv_id)
            header_title = conv.title if conv else "Untitled"
            lines = [f"Similar to: {conv_id[:8]} ({header_title})", ""]

            for other_id, score in results[:10]:
                other_conv = self.db.load_conversation(other_id)
                title = other_conv.title if other_conv else "Untitled"
                short_id = other_id[:8]
                lines.append(f"{score:.3f}  {short_id}  {title}")

            output = "\n".join(lines) + "\n"
            return CommandResult(success=True, output=output)

        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"semantic similar: {str(e)}",
            )

    def _resolve_current_conversation(self) -> Optional[str]:
        """Resolve the current conversation from TUI VFS path."""
        if not self.tui:
            return None

        try:
            parsed = VFSPathParser.parse(self.tui.vfs_cwd)
            return parsed.conversation_id
        except (ValueError, AttributeError):
            return None

    def _get_corpus_texts(self, embeddings: List[dict]) -> List[str]:
        """
        Extract text from conversations for TF-IDF fitting.

        Uses the shared extract_conversation_text() to ensure consistent
        text extraction across index build, TUI search, and MCP search.

        Args:
            embeddings: List of embedding dicts from database

        Returns:
            List of text strings for each conversation
        """
        texts = []
        for emb_dict in embeddings:
            conv_id = emb_dict["conversation_id"]
            conv = self.db.load_conversation(conv_id)
            if conv:
                texts.append(extract_conversation_text(conv))
            else:
                texts.append("")
        return texts


class IndexCommands:
    """Handler for index (embedding) management commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize index command handlers.

        Args:
            db: Database instance
            navigator: VFS navigator for path resolution
            tui_instance: Optional TUI instance
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_index(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Manage embedding index.

        Usage:
            index build [--provider tfidf] [--limit N]  - Build TF-IDF embeddings
            index status                                  - Show embedding stats
            index clear [--provider tfidf]               - Remove cached embeddings

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with operation results
        """
        if not args:
            return CommandResult(
                success=False,
                output="",
                error=(
                    "Usage: index build | index status | index clear\n"
                    "  index build [--provider tfidf] [--limit N]  - Build embeddings\n"
                    "  index status                                 - Show stats\n"
                    "  index clear [--provider tfidf]               - Clear embeddings"
                ),
            )

        subcommand = args[0].lower()

        if subcommand == "build":
            return self._index_build(args[1:])
        elif subcommand == "status":
            return self._index_status(args[1:])
        elif subcommand == "clear":
            return self._index_clear(args[1:])
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"index: unknown subcommand: {subcommand}",
            )

    def _index_build(self, args: List[str]) -> CommandResult:
        """
        Build TF-IDF embeddings for conversations.

        Args:
            args: Optional flags (--provider, --limit)

        Returns:
            CommandResult with build summary
        """
        # Parse arguments
        provider = "tfidf"
        limit = None

        i = 0
        while i < len(args):
            if args[i] == "--provider" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
            elif args[i] == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except ValueError:
                    return CommandResult(
                        success=False,
                        output="",
                        error=f"index build: invalid limit: {args[i + 1]}",
                    )
                i += 2
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"index build: unknown option: {args[i]}",
                )

        if provider != "tfidf":
            return CommandResult(
                success=False,
                output="",
                error=f"index build: unsupported provider: {provider} (only 'tfidf' supported)",
            )

        try:
            from ctk.core.similarity import (ConversationEmbedder,
                                             ConversationEmbeddingConfig)

            # Load conversations
            conversations_summary = self.db.list_conversations(limit=limit or 10000)
            if not conversations_summary:
                return CommandResult(
                    success=True,
                    output="No conversations to index.",
                )

            conversations = []
            for summary in conversations_summary:
                conv = self.db.load_conversation(summary.id)
                if conv:
                    conversations.append(conv)

            if not conversations:
                return CommandResult(
                    success=True,
                    output="No conversations to index.",
                )

            # Extract texts for TF-IDF fitting (canonical extraction)
            texts = [extract_conversation_text(conv) for conv in conversations]

            # Fit TF-IDF and generate embeddings
            config = ConversationEmbeddingConfig(provider="tfidf")
            embedder = ConversationEmbedder(config)
            embedder.provider.fit(texts)

            # Generate and save embeddings
            saved_count = 0
            for conv in conversations:
                embedding = embedder.embed_conversation(conv)
                self.db.save_embedding(
                    conversation_id=conv.id,
                    embedding=embedding.tolist(),
                    provider="tfidf",
                    model="tfidf",
                    chunking_strategy=config.chunking.value,
                    aggregation_strategy=config.aggregation.value,
                    aggregation_weights=config.role_weights,
                )
                saved_count += 1

            return CommandResult(
                success=True,
                output=f"Built {saved_count} embeddings ({provider}).\n",
            )

        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"index build: {str(e)}",
            )

    def _index_status(self, args: List[str]) -> CommandResult:
        """
        Show embedding index status.

        Returns:
            CommandResult with embedding statistics
        """
        try:
            all_embeddings = self.db.get_all_embeddings()
            stats = self.db.get_statistics()
            total_conversations = stats.get("total_conversations", 0)

            if not all_embeddings:
                return CommandResult(
                    success=True,
                    output=(
                        "Embedding index status:\n"
                        f"  Total conversations: {total_conversations}\n"
                        "  Indexed: 0\n"
                        "  Coverage: 0%\n"
                    ),
                )

            # Group by provider
            by_provider: Dict[str, int] = {}
            for emb in all_embeddings:
                prov = emb.get("provider", "unknown")
                by_provider[prov] = by_provider.get(prov, 0) + 1

            # Unique conversations with embeddings
            unique_conv_ids = set(emb["conversation_id"] for emb in all_embeddings)
            indexed_count = len(unique_conv_ids)
            coverage = (
                (indexed_count / total_conversations * 100)
                if total_conversations > 0
                else 0
            )

            lines = [
                "Embedding index status:",
                f"  Total conversations: {total_conversations}",
                f"  Indexed: {indexed_count}",
                f"  Coverage: {coverage:.0f}%",
                f"  Total embeddings: {len(all_embeddings)}",
            ]

            if by_provider:
                lines.append("  By provider:")
                for prov, count in sorted(by_provider.items()):
                    lines.append(f"    {prov}: {count}")

            # Show dimensions if available
            if all_embeddings:
                dims = all_embeddings[0].get("dimensions")
                if dims:
                    lines.append(f"  Dimensions: {dims}")

            return CommandResult(success=True, output="\n".join(lines) + "\n")

        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"index status: {str(e)}",
            )

    def _index_clear(self, args: List[str]) -> CommandResult:
        """
        Clear cached embeddings.

        Args:
            args: Optional flags (--provider)

        Returns:
            CommandResult with deletion summary
        """
        # Parse arguments
        provider = None

        i = 0
        while i < len(args):
            if args[i] == "--provider" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"index clear: unknown option: {args[i]}",
                )

        try:
            count = self.db.delete_embeddings(provider=provider)
            if count == 0:
                return CommandResult(
                    success=True,
                    output="No embeddings to clear.\n",
                )
            return CommandResult(
                success=True,
                output=f"Cleared {count} embeddings.\n",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"index clear: {str(e)}",
            )


def create_semantic_commands(
    db: ConversationDB, navigator: VFSNavigator, tui_instance=None
) -> Dict[str, Callable]:
    """
    Create semantic and index command handlers.

    Args:
        db: Database instance
        navigator: VFS navigator
        tui_instance: Optional TUI instance

    Returns:
        Dictionary mapping command names to handlers
    """
    semantic = SemanticCommands(db, navigator, tui_instance)
    index = IndexCommands(db, navigator, tui_instance)

    return {
        "semantic": semantic.cmd_semantic,
        "index": index.cmd_index,
    }
