#!/usr/bin/env python3
"""
Debug script to test /recent filtering logic
"""

from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ctk.core.database import ConversationDB

def test_recent_filtering(db_path):
    """Test the recent filtering logic"""
    db = ConversationDB(db_path)

    # Get all conversations
    all_convs = db.list_conversations()

    print(f"Total conversations: {len(all_convs)}")
    print()

    # Check dates
    print("Sample conversation dates:")
    for i, conv in enumerate(all_convs[:10]):
        print(f"  {i+1}. {conv.id[:12]}... - created: {conv.created_at}, updated: {conv.updated_at}")
    print()

    # Test filtering logic
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    print(f"Current time: {now}")
    print(f"Today start: {today_start}")
    print(f"Week start: {week_start}")
    print(f"Month start: {month_start}")
    print()

    # Apply filters
    today_count = 0
    this_week_count = 0
    this_month_count = 0
    older_count = 0
    no_date_count = 0

    for conv in all_convs:
        # Use created_at (not updated_at) for recent filtering
        conv_date = conv.created_at or conv.updated_at
        if not conv_date:
            no_date_count += 1
            continue

        # Check if timezone-aware
        if conv_date.tzinfo is not None:
            print(f"WARNING: Timezone-aware datetime found: {conv_date}")

        if conv_date >= today_start:
            today_count += 1
        elif week_start <= conv_date < today_start:
            this_week_count += 1
        elif month_start <= conv_date < week_start:
            this_month_count += 1
        elif conv_date < month_start:
            older_count += 1

    print(f"Filtering results:")
    print(f"  Today: {today_count}")
    print(f"  This week: {this_week_count}")
    print(f"  This month: {this_month_count}")
    print(f"  Older: {older_count}")
    print(f"  No date: {no_date_count}")
    print()

    total_filtered = today_count + this_week_count + this_month_count + older_count
    print(f"Total filtered: {total_filtered} (expected: {len(all_convs) - no_date_count})")

    # Show some samples from each category
    print("\nSample from 'today' category:")
    count = 0
    for conv in all_convs:
        conv_date = conv.created_at or conv.updated_at
        if conv_date and conv_date >= today_start:
            print(f"  {conv.id[:12]}... - {conv_date} - {conv.title[:40] if conv.title else '(no title)'}")
            count += 1
            if count >= 3:
                break

    print("\nSample from 'this-month' category:")
    count = 0
    for conv in all_convs:
        conv_date = conv.created_at or conv.updated_at
        if conv_date and month_start <= conv_date < week_start:
            print(f"  {conv.id[:12]}... - {conv_date} - {conv.title[:40] if conv.title else '(no title)'}")
            count += 1
            if count >= 3:
                break

    db.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python debug_recent_filtering.py <database_path>")
        sys.exit(1)

    test_recent_filtering(sys.argv[1])
