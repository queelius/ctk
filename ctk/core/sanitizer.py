"""
Optional sanitization for sensitive data in conversations
"""

import re
from typing import Dict, List, Pattern, Optional, Any
from dataclasses import dataclass


@dataclass
class SanitizationRule:
    """Rule for sanitizing sensitive data"""
    name: str
    pattern: Pattern
    replacement: str
    enabled: bool = True


class Sanitizer:
    """Sanitize sensitive information in conversations"""
    
    def __init__(self, enabled: bool = False, custom_rules: Optional[List[SanitizationRule]] = None):
        """
        Initialize sanitizer
        
        Args:
            enabled: Whether sanitization is enabled
            custom_rules: Additional custom sanitization rules
        """
        self.enabled = enabled
        self.rules: List[SanitizationRule] = []
        
        if enabled:
            self._init_default_rules()
            if custom_rules:
                self.rules.extend(custom_rules)
    
    def _init_default_rules(self):
        """Initialize default sanitization rules"""
        self.rules = [
            # API Keys
            SanitizationRule(
                name="openai_api_key",
                pattern=re.compile(r'sk-[A-Za-z0-9]{48}'),
                replacement="sk-***REDACTED***"
            ),
            SanitizationRule(
                name="anthropic_api_key",
                pattern=re.compile(r'sk-ant-[A-Za-z0-9]{90,}'),
                replacement="sk-ant-***REDACTED***"
            ),
            SanitizationRule(
                name="generic_api_key",
                pattern=re.compile(r'(?i)(api[_-]?key|apikey|api[_-]?secret|apisecret)[\s:="\']*([A-Za-z0-9_\-]{20,})'),
                replacement=r'\1=***REDACTED***'
            ),
            
            # AWS Credentials
            SanitizationRule(
                name="aws_access_key",
                pattern=re.compile(r'(?i)(AKIA[A-Z0-9]{16})'),
                replacement="AKIA***REDACTED***"
            ),
            SanitizationRule(
                name="aws_secret_key",
                pattern=re.compile(r'(?i)(aws[_-]?secret[_-]?access[_-]?key|aws[_-]?secret)[\s:="\']*([A-Za-z0-9/+=]{40})'),
                replacement=r'\1=***REDACTED***'
            ),
            
            # Passwords
            SanitizationRule(
                name="password",
                pattern=re.compile(r'(?i)(password|passwd|pwd|pass)[\s:="\']*([^\s"\']{8,})'),
                replacement=r'\1=***REDACTED***'
            ),
            
            # Tokens
            SanitizationRule(
                name="jwt_token",
                pattern=re.compile(r'eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'),
                replacement="***JWT_REDACTED***"
            ),
            SanitizationRule(
                name="bearer_token",
                pattern=re.compile(r'(?i)bearer\s+([A-Za-z0-9_\-\.]+)'),
                replacement="Bearer ***REDACTED***"
            ),
            SanitizationRule(
                name="github_token",
                pattern=re.compile(r'ghp_[A-Za-z0-9]{36}'),
                replacement="ghp_***REDACTED***"
            ),
            
            # Database URLs
            SanitizationRule(
                name="database_url",
                pattern=re.compile(r'(?i)(postgres|postgresql|mysql|mongodb|redis|sqlite|mssql):\/\/([^:]+):([^@]+)@'),
                replacement=r'\1://***USER***:***PASS***@'
            ),
            
            # SSH Keys (partial match for safety)
            SanitizationRule(
                name="ssh_private_key",
                pattern=re.compile(r'-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END'),
                replacement="-----BEGIN PRIVATE KEY-----\n***REDACTED***\n-----END PRIVATE KEY-----"
            ),
            
            # Credit Cards
            SanitizationRule(
                name="credit_card",
                pattern=re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b'),
                replacement="****-****-****-****"
            ),
            
            # Email addresses (optional, disabled by default)
            SanitizationRule(
                name="email",
                pattern=re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
                replacement="***EMAIL***",
                enabled=False  # Disabled by default as emails might be intentional
            ),
            
            # IP Addresses (optional, disabled by default)
            SanitizationRule(
                name="ip_address",
                pattern=re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'),
                replacement="***.***.***.***",
                enabled=False  # Disabled by default
            ),
        ]
    
    def sanitize_text(self, text: str) -> str:
        """
        Sanitize sensitive information in text
        
        Args:
            text: Text to sanitize
        
        Returns:
            Sanitized text
        """
        if not self.enabled or not text:
            return text
        
        sanitized = text
        for rule in self.rules:
            if rule.enabled:
                sanitized = rule.pattern.sub(rule.replacement, sanitized)
        
        return sanitized
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize sensitive information in a dictionary
        
        Args:
            data: Dictionary to sanitize
        
        Returns:
            Sanitized dictionary
        """
        if not self.enabled:
            return data
        
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = self.sanitize_text(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_text(item) if isinstance(item, str)
                    else self.sanitize_dict(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def add_rule(self, rule: SanitizationRule):
        """Add a custom sanitization rule"""
        self.rules.append(rule)
    
    def enable_rule(self, name: str):
        """Enable a specific rule by name"""
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = True
                break
    
    def disable_rule(self, name: str):
        """Disable a specific rule by name"""
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = False
                break
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """List all available rules"""
        return [
            {
                'name': rule.name,
                'pattern': rule.pattern.pattern,
                'enabled': rule.enabled
            }
            for rule in self.rules
        ]