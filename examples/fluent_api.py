#!/usr/bin/env python3
"""
Examples of using CTK's fluent Python API

This demonstrates the pythonic, chainable interface for working with conversations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ctk.api import CTK, conversation, load, from_db
from ctk.core.models import MessageRole


def example_quick_operations():
    """Quick one-liner operations"""
    print("=" * 60)
    print("Quick Operations Examples")
    print("=" * 60)

    # Quick load and export
    print("\n1. Load JSON and export as Markdown:")
    print('CTK.load("chat.json").export_as("markdown").save("chat.md")')

    # Quick conversion between formats
    print("\n2. Convert ChatGPT export to JSONL:")
    print('load("chatgpt.json").with_format("openai").export_as("jsonl").save("training.jsonl")')

    # Filter and transform
    print("\n3. Filter technical conversations:")
    print('''load("all_chats.json")
    .filter(lambda c: "python" in c.title.lower())
    .add_tags("technical", "python")
    .export_as("json")
    .save("python_chats.json")''')


def example_building_conversations():
    """Building conversations programmatically"""
    print("\n" + "=" * 60)
    print("Building Conversations")
    print("=" * 60)

    # Linear conversation
    linear_chat = (conversation("Python Help")
        .system("You are a Python expert")
        .user("How do I use async/await?")
        .assistant("Here's how async/await works in Python...")
        .user("Can you show an example?")
        .assistant("```python\nasync def fetch_data():\n    await asyncio.sleep(1)\n    return 'data'\n```")
        .with_metadata(source="manual", model="gpt-4")
        .with_tags("python", "async", "tutorial")
        .build())

    print(f"\nCreated linear conversation with {len(linear_chat.message_map)} messages")

    # Branching conversation
    branching_chat = (conversation("Creative Writing")
        .user("Write a haiku about programming")
        .assistant("Code flows like water\nBugs surface in production\nDebugger saves day")
        .branch()  # Start alternative response
        .assistant("Syntax errors bloom\nLike flowers in my IDE\nSemicolon missing")
        .build())

    paths = branching_chat.get_all_paths()
    print(f"Created branching conversation with {len(paths)} paths")


def example_database_operations():
    """Database operations with fluent API"""
    print("\n" + "=" * 60)
    print("Database Operations")
    print("=" * 60)

    # Initialize with database
    ctk = CTK("example.db")

    print("\n1. Import with metadata:")
    print('''ctk.import_from("export.json")
    .with_format("openai")
    .with_tags("imported", "2024")
    .with_project("CustomerSupport")
    .save()''')

    print("\n2. Search with filters:")
    print('''results = ctk.search("error handling")
    .in_source("ChatGPT")
    .with_model("gpt-4")
    .limit(20)
    .get()''')

    print("\n3. Query conversations:")
    print('''recent = ctk.conversations()
    .where(source="Claude")
    .order_by("updated_at", desc=True)
    .limit(10)
    .get()''')

    print("\n4. Batch operations:")
    print('''with ctk.batch():
    ctk.import_from("file1.json").save()
    ctk.import_from("file2.json").save()
    ctk.import_from("file3.json").save()''')


def example_advanced_queries():
    """Advanced querying and filtering"""
    print("\n" + "=" * 60)
    print("Advanced Queries")
    print("=" * 60)

    ctk = CTK("example.db")

    print("\n1. Complex search with export:")
    print('''ctk.search("machine learning")
    .in_source("ChatGPT")
    .with_tags("ai", "ml")
    .limit(50)
    .export_as("markdown")
    .with_paths("longest")
    .include_metadata()
    .save("ml_discussions.md")''')

    print("\n2. Pagination:")
    print('''page1 = ctk.conversations().limit(10).offset(0).get()
page2 = ctk.conversations().limit(10).offset(10).get()''')

    print("\n3. Count and delete:")
    print('''# Count old conversations
count = ctk.conversations()
    .where(source="ChatGPT")
    .where(model="gpt-3.5-turbo")
    .count()

# Delete them
deleted = ctk.conversations()
    .where(source="ChatGPT")
    .where(model="gpt-3.5-turbo")
    .delete_all()''')


def example_export_options():
    """Export with various options"""
    print("\n" + "=" * 60)
    print("Export Options")
    print("=" * 60)

    # Assuming we have conversations loaded
    conversations = [
        conversation("Example Chat")
        .user("Hello")
        .assistant("Hi there!")
        .build()
    ]

    from ctk.api import ExportBuilder

    print("\n1. Markdown with full options:")
    print('''ExportBuilder(conversations, "markdown")
    .with_paths("all")
    .include_metadata(True)
    .include_timestamps(True)
    .include_tree_structure(True)
    .save("full_export.md")''')

    print("\n2. JSON with format styles:")
    print('''# Native CTK format (preserves tree)
ExportBuilder(conversations, "json")
    .format_style("ctk")
    .pretty_print(True)
    .save("ctk_format.json")

# OpenAI compatible format
ExportBuilder(conversations, "json")
    .format_style("openai")
    .save("openai_format.json")

# Anthropic compatible format
ExportBuilder(conversations, "json")
    .format_style("anthropic")
    .save("anthropic_format.json")''')


def example_transform_pipeline():
    """Complex transformation pipeline"""
    print("\n" + "=" * 60)
    print("Transformation Pipeline")
    print("=" * 60)

    print('''
# Load, filter, transform, and export in a single pipeline
load("all_conversations.json")
    .filter(lambda c: len(c.message_map) > 10)  # Only long conversations
    .filter(lambda c: c.metadata.source == "ChatGPT")  # Only from ChatGPT
    .transform(lambda c: add_word_count(c))  # Add word count metadata
    .add_tags("processed", "long-form")
    .export_as("jsonl")
    .save("filtered_conversations.jsonl")

def add_word_count(conv):
    """Add word count to metadata"""
    total_words = sum(
        len(msg.content.get_text().split())
        for msg in conv.message_map.values()
        if msg.content
    )
    conv.metadata.custom_data['word_count'] = total_words
    return conv
''')


def example_multimodal_content():
    """Working with multimodal content"""
    print("\n" + "=" * 60)
    print("Multimodal Content")
    print("=" * 60)

    print('''
# Build conversation with images and tool calls
conv = (conversation("Technical Demo")
    .user("Analyze this image",
          images=[{"url": "https://example.com/chart.png"}])
    .assistant("I can see a chart showing...",
               tools=[{
                   "name": "calculate_trend",
                   "arguments": {"data": [1, 2, 3, 4, 5]}
               }])
    .user("What's the trend?")
    .assistant("The trend is increasing linearly")
    .build())
''')


def example_real_world_workflow():
    """Real-world workflow example"""
    print("\n" + "=" * 60)
    print("Real-World Workflow")
    print("=" * 60)

    print('''
# Complete workflow: Import, process, analyze, export

from ctk.api import CTK

# Setup
ctk = CTK("production.db")

# 1. Import from multiple sources
with ctk.batch():
    # Import ChatGPT conversations
    ctk.import_from("exports/chatgpt_2024.json")
       .with_format("openai")
       .with_tags("chatgpt", "2024")
       .save()

    # Import Claude conversations
    ctk.import_from("exports/claude_2024.json")
       .with_format("anthropic")
       .with_tags("claude", "2024")
       .save()

# 2. Search and analyze
python_convs = ctk.search("python")
                  .limit(100)
                  .get()

print(f"Found {len(python_convs)} Python-related conversations")

# 3. Get statistics
stats = ctk.stats()
print(f"Total conversations: {stats['total_conversations']}")
print(f"Total messages: {stats['total_messages']}")

# 4. Export recent technical discussions
ctk.conversations()
   .where(project="TechnicalDocs")
   .order_by("updated_at", desc=True)
   .limit(50)
   .export_as("markdown")
   .with_paths("longest")
   .include_metadata()
   .save("reports/recent_technical.md")

# 5. Clean up old data
deleted_count = ctk.conversations()
                   .where(source="ChatGPT")
                   .where(model="gpt-3.5-turbo")
                   .delete_all()

print(f"Cleaned up {deleted_count} old conversations")
''')


def main():
    """Run all examples"""
    example_quick_operations()
    example_building_conversations()
    example_database_operations()
    example_advanced_queries()
    example_export_options()
    example_transform_pipeline()
    example_multimodal_content()
    example_real_world_workflow()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()