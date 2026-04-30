# models/user.py
import hashlib
from typing import Optional, Dict, List, Any
from datetime import datetime


class User:
    """User model for authentication and management"""
    
    def __init__(self, user_id: str = None, username: str = "", email: str = "", 
                 password_hash: str = "", role: str = "operator", 
                 is_active: bool = True, created_at: str = None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role  # "admin" or "operator"
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow().isoformat()
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        return self.password_hash == self.hash_password(password)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for database storage"""
        return {
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Create user from dictionary"""
        return cls(
            user_id=data.get("user_id"),
            username=data.get("username", ""),
            email=data.get("email", ""),
            password_hash=data.get("password_hash", ""),
            role=data.get("role", "operator"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at")
        )
