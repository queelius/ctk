"""
context.py - Context class for CTK operations
"""

import os
import logging
from typing import List, Dict, Any, Optional, Union, Callable

logger = logging.getLogger(__name__)

class CTKContext:
    """
    Context object for CTK operations.
    
    This class holds the state needed for operations on conversation data,
    including the library directory path and loaded conversations.
    """
    
    def __init__(self, lib_dir: Optional[str] = None, conversations: Optional[List[Dict]] = None):
        """
        Initialize the CTK context.
        
        Args:
            lib_dir: Path to the conversation library directory
            conversations: Pre-loaded conversation data
        """
        self.lib_dir = lib_dir
        self._conversations = conversations
        self._modified = False
        
    @property
    def conversations(self) -> List[Dict]:
        """
        Get conversations, loading from disk if necessary.
        
        Returns:
            List of conversation dictionaries
        """
        if self._conversations is None and self.lib_dir:
            from .utils import load_conversations
            self._conversations = load_conversations(self.lib_dir)
            logger.debug(f"Loaded {len(self._conversations)} conversations from {self.lib_dir}")
        return self._conversations or []
    
    @conversations.setter
    def conversations(self, value: List[Dict]):
        """
        Set conversations and mark context as modified.
        
        Args:
            value: List of conversation dictionaries
        """
        self._conversations = value
        self._modified = True
    
    def save_conversations(self) -> bool:
        """
        Save conversations back to disk if they've been modified.
        
        Returns:
            True if conversations were saved, False otherwise
        """
        if self._modified and self._conversations is not None and self.lib_dir:
            from .utils import save_conversations
            save_conversations(self.lib_dir, self._conversations)
            self._modified = False
            logger.debug(f"Saved {len(self._conversations)} conversations to {self.lib_dir}")
            return True
        return False
    
    def mark_modified(self):
        """Mark conversations as modified."""
        self._modified = True
    
    def ensure_lib_dir(self) -> bool:
        """
        Ensure the library directory exists.
        
        Returns:
            True if the directory exists or was created, False otherwise
        """
        if not self.lib_dir:
            logger.error("No library directory specified")
            return False
        
        if not os.path.exists(self.lib_dir):
            try:
                os.makedirs(self.lib_dir)
                logger.debug(f"Created library directory: {self.lib_dir}")
            except OSError as e:
                logger.error(f"Could not create library directory: {e}")
                return False
        
        return True
    
    def get_conversation(self, index: int) -> Optional[Dict]:
        """
        Get a single conversation by index.
        
        Args:
            index: Index of the conversation
            
        Returns:
            Conversation dictionary or None if not found
        """
        conversations = self.conversations
        if 0 <= index < len(conversations):
            return conversations[index]
        logger.warning(f"Conversation index {index} out of range")
        return None
    
    def get_conversations_by_indices(self, indices: List[int]) -> List[Dict]:
        """
        Get multiple conversations by indices.
        
        Args:
            indices: List of conversation indices
            
        Returns:
            List of conversation dictionaries for valid indices
        """
        conversations = self.conversations
        result = []
        for index in indices:
            if 0 <= index < len(conversations):
                result.append(conversations[index])
            else:
                logger.warning(f"Conversation index {index} out of range")
        return result
    
    def find_conversations(self, predicate: Callable[[Dict], bool]) -> List[Dict]:
        """
        Find conversations that match a predicate function.
        
        Args:
            predicate: Function that takes a conversation and returns True/False
            
        Returns:
            List of matching conversations
        """
        return [conv for conv in self.conversations if predicate(conv)]