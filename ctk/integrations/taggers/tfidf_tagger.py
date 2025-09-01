"""
TF-IDF based auto-tagger - fast and local
"""

import re
from collections import Counter
from typing import List, Set, Dict, Tuple
import math

from ctk.core.plugin import BasePlugin
from ctk.core.models import ConversationTree, Message


class TFIDFTagger(BasePlugin):
    """Fast TF-IDF based auto-tagger"""
    
    name = "tfidf"
    description = "TF-IDF based automatic tagging"
    version = "1.0.0"
    
    # Common stop words to ignore
    STOP_WORDS = set([
        'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
        'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
        'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her',
        'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
        'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
        'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no',
        'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your',
        'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then',
        'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also',
        'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first',
        'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
        'give', 'day', 'most', 'us', 'is', 'was', 'are', 'been', 'has',
        'had', 'were', 'said', 'did', 'get', 'may', 'am', 'let', 'put',
        'here', 'very', 'too', 'much', 'really', 'going', 'why', 'before',
        'never', 'being', 'sure', 'yes', 'no', 'maybe', 'okay', 'oh',
    ])
    
    # Domain-specific keyword patterns
    DOMAIN_PATTERNS = {
        'python': r'\b(python|pip|django|flask|pandas|numpy|jupyter)\b',
        'javascript': r'\b(javascript|js|node|npm|react|vue|angular)\b',
        'machine-learning': r'\b(ml|machine learning|neural|network|training|model|dataset|tensor)\b',
        'ai': r'\b(ai|artificial intelligence|gpt|llm|transformer|attention|embedding)\b',
        'database': r'\b(database|sql|postgresql|mysql|mongodb|redis|query)\b',
        'devops': r'\b(docker|kubernetes|k8s|ci/cd|deployment|container)\b',
        'api': r'\b(api|rest|graphql|endpoint|request|response|http)\b',
        'security': r'\b(security|encryption|auth|oauth|jwt|password|vulnerability)\b',
        'frontend': r'\b(frontend|ui|ux|css|html|design|responsive|layout)\b',
        'backend': r'\b(backend|server|microservice|architecture|scalability)\b',
        'data-science': r'\b(data science|analysis|visualization|statistics|regression)\b',
        'cloud': r'\b(cloud|aws|azure|gcp|lambda|serverless|s3)\b',
        'mobile': r'\b(mobile|ios|android|swift|kotlin|react native)\b',
        'testing': r'\b(test|testing|unit test|integration|pytest|jest|mock)\b',
        'linux': r'\b(linux|ubuntu|debian|bash|shell|terminal|command)\b',
        'git': r'\b(git|github|gitlab|merge|branch|commit|pull request)\b',
        'algorithms': r'\b(algorithm|complexity|big o|sorting|search|graph|tree)\b',
        'crypto': r'\b(blockchain|bitcoin|ethereum|crypto|wallet|defi|nft)\b',
        'math': r'\b(mathematics|equation|calculus|algebra|statistics|probability)\b',
        'physics': r'\b(physics|quantum|relativity|particle|energy|force)\b',
        'biology': r'\b(biology|dna|gene|protein|cell|evolution|species)\b',
        'chemistry': r'\b(chemistry|molecule|reaction|compound|element|periodic)\b',
        'philosophy': r'\b(philosophy|ethics|consciousness|existential|metaphysics)\b',
        'economics': r'\b(economics|market|finance|trading|investment|stock)\b',
        'writing': r'\b(writing|essay|article|blog|story|narrative|grammar)\b',
        'education': r'\b(education|learning|teaching|student|course|curriculum)\b',
        'gaming': r'\b(game|gaming|player|level|quest|rpg|fps|mmorpg)\b',
        'music': r'\b(music|song|melody|rhythm|instrument|composer|genre)\b',
        'art': r'\b(art|painting|drawing|sculpture|artistic|gallery|museum)\b',
        'health': r'\b(health|medical|doctor|patient|treatment|diagnosis|disease)\b',
        'fitness': r'\b(fitness|exercise|workout|gym|muscle|cardio|nutrition)\b',
        'cooking': r'\b(cooking|recipe|ingredient|bake|chef|cuisine|food)\b',
        'travel': r'\b(travel|trip|vacation|destination|flight|hotel|tourism)\b',
        'language': r'\b(language|translation|grammar|vocabulary|linguistics)\b',
        'legal': r'\b(legal|law|lawyer|court|contract|regulation|compliance)\b',
        'business': r'\b(business|company|startup|entrepreneur|management|strategy)\b',
        'marketing': r'\b(marketing|advertising|campaign|brand|seo|social media)\b',
    }
    
    def __init__(self):
        self.document_frequencies = {}
        self.total_documents = 0
    
    def validate(self, data):
        """Check if we can process this data"""
        return isinstance(data, (ConversationTree, list))
    
    def extract_text(self, conversation: ConversationTree) -> str:
        """Extract all text from a conversation"""
        messages = conversation.get_longest_path()
        texts = []
        
        for msg in messages:
            if msg.role.value in ['user', 'assistant']:
                text = msg.content.get_text()
                if text:
                    texts.append(text)
        
        return ' '.join(texts)
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize and clean text"""
        # Convert to lowercase and extract words
        text = text.lower()
        words = re.findall(r'\b[a-z]+\b', text)
        
        # Remove stop words and short words
        words = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]
        
        return words
    
    def calculate_tf(self, words: List[str]) -> Dict[str, float]:
        """Calculate term frequency"""
        word_count = len(words)
        if word_count == 0:
            return {}
        
        counter = Counter(words)
        tf = {word: count / word_count for word, count in counter.items()}
        return tf
    
    def calculate_tfidf(self, tf: Dict[str, float]) -> Dict[str, float]:
        """Calculate TF-IDF scores"""
        tfidf = {}
        
        for word, freq in tf.items():
            # IDF = log(total_docs / (1 + docs_with_word))
            docs_with_word = self.document_frequencies.get(word, 0)
            idf = math.log((self.total_documents + 1) / (1 + docs_with_word))
            tfidf[word] = freq * idf
        
        return tfidf
    
    def extract_domain_tags(self, text: str) -> Set[str]:
        """Extract domain-specific tags based on patterns"""
        tags = set()
        text_lower = text.lower()
        
        for tag, pattern in self.DOMAIN_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                tags.add(tag)
        
        return tags
    
    def extract_key_phrases(self, text: str, words: List[str]) -> Set[str]:
        """Extract important phrases (bigrams/trigrams)"""
        phrases = set()
        
        # Look for capitalized phrases (likely proper nouns or important terms)
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
        for phrase in capitalized[:5]:  # Top 5 capitalized phrases
            if len(phrase) < 30:  # Reasonable length
                phrases.add(phrase.lower().replace(' ', '-'))
        
        # Common technical patterns
        # Version numbers (e.g., Python 3.9)
        versions = re.findall(r'\b([A-Za-z]+)\s+(\d+(?:\.\d+)*)\b', text)
        for name, version in versions[:3]:
            if name.lower() not in self.STOP_WORDS:
                phrases.add(f"{name.lower()}-{version}")
        
        # Acronyms
        acronyms = re.findall(r'\b[A-Z]{2,6}\b', text)
        for acronym in set(acronyms[:5]):
            if acronym not in ['THE', 'AND', 'FOR', 'BUT']:
                phrases.add(acronym.lower())
        
        return phrases
    
    def tag_conversation(self, conversation: ConversationTree, 
                        num_tags: int = 10) -> List[str]:
        """Generate tags for a conversation"""
        # Extract text
        text = self.extract_text(conversation)
        if not text:
            return []
        
        # Get domain tags first (high confidence)
        domain_tags = self.extract_domain_tags(text)
        
        # Tokenize and calculate TF
        words = self.tokenize(text)
        if not words:
            return list(domain_tags)[:num_tags]
        
        tf = self.calculate_tf(words)
        
        # Calculate TF-IDF if we have document frequencies
        if self.total_documents > 0:
            tfidf = self.calculate_tfidf(tf)
        else:
            tfidf = tf
        
        # Get top keywords
        top_keywords = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        keyword_tags = []
        
        for word, score in top_keywords[:20]:
            # Filter out very common words even if they passed stop words
            if score > 0.01 and len(word) > 3:
                keyword_tags.append(word)
        
        # Extract key phrases
        phrase_tags = self.extract_key_phrases(text, words)
        
        # Combine all tags
        all_tags = list(domain_tags) + keyword_tags[:5] + list(phrase_tags)[:3]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in all_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        return unique_tags[:num_tags]
    
    def update_corpus_statistics(self, conversations: List[ConversationTree]):
        """Update document frequencies for better TF-IDF calculation"""
        for conv in conversations:
            text = self.extract_text(conv)
            words = set(self.tokenize(text))
            
            for word in words:
                self.document_frequencies[word] = self.document_frequencies.get(word, 0) + 1
            
            self.total_documents += 1
    
    def analyze_conversation(self, conversation: ConversationTree) -> Dict:
        """Detailed analysis of a conversation"""
        text = self.extract_text(conversation)
        words = self.tokenize(text)
        
        # Basic stats
        stats = {
            'word_count': len(text.split()),
            'unique_words': len(set(words)),
            'message_count': len(conversation.get_longest_path()),
        }
        
        # Language detection (simple heuristic)
        code_indicators = ['def ', 'function ', 'class ', 'import ', 'const ', 'var ']
        has_code = any(indicator in text for indicator in code_indicators)
        stats['has_code'] = has_code
        
        # Question/answer pattern
        questions = len(re.findall(r'\?', text))
        stats['questions'] = questions
        
        # Suggested tags
        stats['suggested_tags'] = self.tag_conversation(conversation)
        
        # Topic confidence
        domain_matches = {}
        for domain, pattern in self.DOMAIN_PATTERNS.items():
            matches = len(re.findall(pattern, text.lower()))
            if matches > 0:
                domain_matches[domain] = matches
        
        stats['topics'] = sorted(domain_matches.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return stats