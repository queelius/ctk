#!/usr/bin/env python3
"""
Auto-tagging CLI for CTK
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ctk.core.database import ConversationDB
from ctk.core.config import get_config
from ctk.integrations.taggers import (
    TFIDFTagger,
    OllamaTagger,
    OpenAITagger,
    AnthropicTagger,
    OpenRouterTagger,
    LocalTagger
)


def get_tagger(provider: str, model: Optional[str] = None, 
               base_url: Optional[str] = None):
    """Get a tagger instance for the specified provider"""
    taggers = {
        'tfidf': TFIDFTagger,
        'ollama': OllamaTagger,
        'openai': OpenAITagger,
        'anthropic': AnthropicTagger,
        'openrouter': OpenRouterTagger,
        'local': LocalTagger
    }
    
    if provider not in taggers:
        print(f"Unknown provider: {provider}")
        print(f"Available providers: {', '.join(taggers.keys())}")
        return None
    
    if provider == 'tfidf':
        return TFIDFTagger()
    else:
        kwargs = {}
        if model:
            kwargs['model'] = model
        if base_url:
            kwargs['base_url'] = base_url
        return taggers[provider](**kwargs)


def main():
    parser = argparse.ArgumentParser(description='Auto-tag conversations')
    parser.add_argument('--db', required=True, help='Database path')
    parser.add_argument('--provider', default='tfidf',
                       choices=['tfidf', 'ollama', 'openai', 'anthropic', 'openrouter', 'local'],
                       help='Tagging provider (default: tfidf)')
    parser.add_argument('--model', help='Model to use (provider-specific)')
    parser.add_argument('--base-url', help='Override base URL for API')
    parser.add_argument('--conversation', help='Tag specific conversation ID')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of conversations to tag (default: 10)')
    parser.add_argument('--all', action='store_true',
                       help='Tag all conversations')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show tags without saving')
    parser.add_argument('--num-tags', type=int, default=10,
                       help='Maximum number of tags per conversation (default: 10)')
    parser.add_argument('--append', action='store_true',
                       help='Append tags instead of replacing')
    parser.add_argument('--config', help='Path to config file')
    
    args = parser.parse_args()
    
    # Load config if specified
    if args.config:
        from ctk.core.config import Config
        config = Config(Path(args.config))
    else:
        config = get_config()
    
    # Open database
    db = ConversationDB(args.db)
    
    # Get tagger
    tagger = get_tagger(args.provider, args.model, args.base_url)
    if not tagger:
        return 1
    
    # Check provider availability for LLM taggers
    if args.provider == 'ollama':
        if not tagger.check_connection():
            print("Warning: Ollama not running. Start with: ollama serve")
            if not args.dry_run:
                return 1
    elif args.provider in ['openai', 'anthropic', 'openrouter']:
        if not tagger.api_key:
            print(f"Error: {args.provider.upper()}_API_KEY not set")
            print(f"Set environment variable or add to ~/.ctk/config.json")
            return 1
    
    # Get conversations to tag
    if args.conversation:
        # Single conversation
        conv = db.load_conversation(args.conversation)
        if not conv:
            print(f"Conversation not found: {args.conversation}")
            return 1
        conversations = [conv]
    else:
        # Multiple conversations
        limit = None if args.all else args.limit
        conv_list = db.list_conversations(limit=limit)
        conversations = []
        for conv_data in conv_list:
            conv = db.load_conversation(conv_data['id'])
            if conv:
                conversations.append(conv)
    
    if not conversations:
        print("No conversations to tag")
        return 0
    
    print(f"Tagging {len(conversations)} conversation(s) using {args.provider}")
    if args.provider != 'tfidf':
        print(f"Model: {tagger.model}")
    print()
    
    # Tag conversations
    for idx, conv in enumerate(conversations, 1):
        print(f"[{idx}/{len(conversations)}] {conv.title or 'Untitled'}")
        
        # Generate tags
        if args.provider == 'tfidf':
            tags = tagger.tag_conversation(conv, num_tags=args.num_tags)
        else:
            tags = tagger.tag_conversation(conv)[:args.num_tags]
        
        if not tags:
            print("  No tags generated")
            continue
        
        # Show tags
        print(f"  Tags: {', '.join(tags)}")
        
        # Save if not dry run
        if not args.dry_run:
            if args.append:
                # Append to existing tags
                existing = set(conv.metadata.tags)
                conv.metadata.tags = list(existing | set(tags))
            else:
                # Replace tags
                conv.metadata.tags = tags
            
            db.save_conversation(conv)
            print("  ✓ Saved")
        
        print()
    
    # Show statistics
    if args.provider == 'tfidf' and len(conversations) > 1:
        print("Updating TF-IDF corpus statistics...")
        tagger.update_corpus_statistics(conversations)
        print(f"Corpus size: {tagger.total_documents} documents")
    
    db.close()
    print("Done!")
    return 0


if __name__ == '__main__':
    sys.exit(main())