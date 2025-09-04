"""
Base class for LLM-based taggers
"""

import json
from typing import List, Dict, Optional, Any
from abc import abstractmethod

from ctk.core.plugin import BasePlugin
from ctk.core.models import ConversationTree
from ctk.core.config import get_config


class BaseLLMTagger(BasePlugin):
    """Base class for LLM-based automatic tagging"""
    
    description = "LLM-based automatic tagging"
    version = "1.0.0"
    
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, **kwargs):
        """
        Initialize LLM tagger
        
        Args:
            model: Model to use (provider-specific)
            base_url: Override base URL for custom endpoints
            api_key: API key for providers that require it
            **kwargs: Additional provider-specific parameters
        """
        self.config = get_config()
        self.provider_name = self.get_provider_name()
        
        # Load provider config
        provider_config = self.config.get_provider_config(self.provider_name)
        
        # Set attributes with overrides
        self.model = model or provider_config.get('default_model')
        self.base_url = base_url or provider_config.get('base_url')
        self.api_key = api_key or self.config.get_api_key(self.provider_name)
        self.timeout = kwargs.get('timeout', provider_config.get('timeout', 30))
        
        # Store additional kwargs
        self.kwargs = kwargs
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name for this tagger"""
        pass
    
    @abstractmethod
    def call_api(self, prompt: str) -> Optional[str]:
        """
        Call the provider's API with the prompt
        
        Args:
            prompt: The prompt to send
            
        Returns:
            The response text or None if failed
        """
        pass
    
    def validate(self, data) -> bool:
        """Check if we can process this data"""
        return isinstance(data, (ConversationTree, list))
    
    def create_tagging_prompt(self, text: str) -> str:
        """Create prompt for tag generation"""
        prompt = f"""Analyze this conversation and generate relevant tags.

Consider:
1. Main topics discussed
2. Technologies, tools, or frameworks mentioned
3. Problem domains (e.g., web development, data science, etc.)
4. Programming languages
5. Concepts or theories
6. Project type or use case

Conversation excerpt:
{text[:3000]}

Generate 5-10 relevant tags. Return ONLY a JSON array of tag strings, nothing else.
Example: ["python", "machine-learning", "pandas", "data-analysis", "tutorial"]

Tags:"""
        return prompt
    
    def create_categorization_prompt(self, text: str) -> str:
        """Create prompt for detailed categorization"""
        prompt = f"""Analyze this conversation and provide detailed categorization.

Conversation excerpt:
{text[:3000]}

Return a JSON object with:
- "primary_topic": main subject (e.g., "web development", "data science")
- "tags": array of 5-10 relevant tags
- "complexity": "beginner", "intermediate", or "advanced"
- "type": "tutorial", "debugging", "discussion", "code-review", or "other"
- "languages": programming languages mentioned (array)
- "frameworks": frameworks/libraries mentioned (array)
- "concepts": key concepts discussed (array, max 5)

Return ONLY valid JSON, nothing else."""
        return prompt
    
    def extract_text(self, conversation: ConversationTree) -> str:
        """Extract relevant text from conversation"""
        messages = conversation.get_longest_path()
        texts = []
        
        # Get first few and last few messages for context
        relevant_messages = messages[:5] + messages[-5:] if len(messages) > 10 else messages
        
        for msg in relevant_messages:
            if msg.role.value in ['user', 'assistant']:
                text = msg.content.get_text()
                if text:
                    texts.append(f"{msg.role.value}: {text[:500]}")
        
        return '\n'.join(texts)
    
    def parse_tags_response(self, response: str) -> List[str]:
        """Parse LLM response to extract tags"""
        if not response:
            return []
        
        try:
            # Try to parse as JSON array
            if '[' in response and ']' in response:
                # Extract JSON array
                start = response.index('[')
                end = response.rindex(']') + 1
                json_str = response[start:end]
                tags = json.loads(json_str)
                
                if isinstance(tags, list):
                    # Clean and validate tags
                    clean_tags = []
                    for tag in tags:
                        if isinstance(tag, str):
                            # Clean tag: lowercase, replace spaces with hyphens
                            clean_tag = tag.lower().strip().replace(' ', '-')
                            # Remove special characters except hyphens
                            clean_tag = ''.join(c for c in clean_tag if c.isalnum() or c == '-')
                            if clean_tag and len(clean_tag) > 1:
                                clean_tags.append(clean_tag)
                    return clean_tags[:15]  # Limit to 15 tags
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            pass
        
        # Fallback: extract comma-separated values
        if ',' in response:
            tags = response.split(',')
            clean_tags = []
            for tag in tags:
                clean_tag = tag.strip().lower().replace(' ', '-')
                clean_tag = ''.join(c for c in clean_tag if c.isalnum() or c == '-')
                if clean_tag and len(clean_tag) > 1:
                    clean_tags.append(clean_tag)
            return clean_tags[:15]
        
        return []
    
    def parse_categorization_response(self, response: str) -> Dict[str, Any]:
        """Parse categorization response"""
        if not response:
            return {}
        
        try:
            # Parse JSON response
            if '{' in response and '}' in response:
                start = response.index('{')
                end = response.rindex('}') + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        
        return {}
    
    def tag_conversation(self, conversation: ConversationTree) -> List[str]:
        """Generate tags for a conversation using LLM"""
        # Extract text
        text = self.extract_text(conversation)
        if not text:
            return []
        
        # Create prompt
        prompt = self.create_tagging_prompt(text)
        
        # Call API
        response = self.call_api(prompt)
        
        # Parse response
        tags = self.parse_tags_response(response)
        
        return tags
    
    def categorize_conversation(self, conversation: ConversationTree) -> Dict[str, Any]:
        """Get detailed categorization from LLM"""
        # Extract text
        text = self.extract_text(conversation)
        if not text:
            return {}
        
        # Create prompt
        prompt = self.create_categorization_prompt(text)
        
        # Call API
        response = self.call_api(prompt)
        
        # Parse response
        return self.parse_categorization_response(response)
    
    def batch_tag_conversations(self, conversations: List[ConversationTree],
                               progress_callback=None) -> Dict[str, List[str]]:
        """Tag multiple conversations with progress updates"""
        results = {}
        
        for idx, conv in enumerate(conversations):
            if progress_callback:
                progress_callback(idx, len(conversations), conv.title)
            
            tags = self.tag_conversation(conv)
            results[conv.id] = tags
        
        return results