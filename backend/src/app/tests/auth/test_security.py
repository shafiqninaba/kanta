"""
Tests for auth.security module.

This module tests JWT token creation/verification, password hashing,
and authentication dependencies.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.auth.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_get_password_hash_returns_hashed_password(self):
        """Test that password hashing returns a hashed string."""
        password = "test_password123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_verify_password_with_correct_password(self):
        """Test password verification with correct password."""
        password = "test_password123"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_password_with_incorrect_password(self):
        """Test password verification with incorrect password."""
        password = "test_password123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False

    def test_different_passwords_produce_different_hashes(self):
        """Test that different passwords produce different hashes."""
        password1 = "password123"
        password2 = "password456"
        
        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)
        
        assert hash1 != hash2


class TestJWTTokens:
    """Test JWT token creation and decoding."""

    @patch("app.auth.security.settings")
    def test_create_access_token_with_default_expiry(self, mock_settings):
        """Test JWT token creation with default expiry."""
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        
        subject = "test_user"
        token = create_access_token(subject)
        
        # Decode without verification to check payload
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["sub"] == subject
        assert "exp" in payload

    @patch("app.auth.security.settings")
    def test_create_access_token_with_custom_expiry(self, mock_settings):
        """Test JWT token creation with custom expiry."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        
        subject = "test_user"
        custom_delta = timedelta(minutes=60)
        token = create_access_token(subject, expires_delta=custom_delta)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["sub"] == subject

    @patch("app.auth.security.settings")
    def test_create_access_token_with_non_string_subject(self, mock_settings):
        """Test JWT token creation with non-string subject."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        
        subject = 12345  # integer subject
        token = create_access_token(subject)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["sub"] == str(subject)

    @patch("app.auth.security.settings")
    def test_decode_access_token_valid_token(self, mock_settings):
        """Test decoding valid JWT token."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        
        subject = "test_user"
        token = create_access_token(subject)
        
        decoded_subject = decode_access_token(token)
        assert decoded_subject == subject

    @patch("app.auth.security.settings")
    def test_decode_access_token_expired_token(self, mock_settings):
        """Test decoding expired JWT token."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        
        subject = "test_user"
        # Create token that expires immediately
        expired_delta = timedelta(seconds=-1)
        token = create_access_token(subject, expires_delta=expired_delta)
        
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    @patch("app.auth.security.settings")
    def test_decode_access_token_invalid_signature(self, mock_settings):
        """Test decoding token with invalid signature."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        
        # Create token with different secret
        invalid_token = jwt.encode(
            {"sub": "test_user", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
            "wrong_secret",
            algorithm="HS256"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(invalid_token)
        
        assert exc_info.value.status_code == 401

    @patch("app.auth.security.settings")
    def test_decode_access_token_missing_subject(self, mock_settings):
        """Test decoding token without subject claim."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        
        # Create token without 'sub' claim
        token_without_sub = jwt.encode(
            {"exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
            "test_secret",
            algorithm="HS256"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token_without_sub)
        
        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in exc_info.value.detail

    def test_decode_access_token_malformed_token(self):
        """Test decoding malformed token."""
        malformed_token = "invalid.token.format"
        
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(malformed_token)
        
        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    """Test get_current_user dependency."""

    @patch("app.auth.security.decode_access_token")
    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, mock_decode):
        """Test get_current_user with valid token."""
        mock_decode.return_value = "test_user"
        token = "valid_token"
        
        user = await get_current_user(token)
        
        assert user == "test_user"
        mock_decode.assert_called_once_with(token)

    @patch("app.auth.security.decode_access_token")
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_decode):
        """Test get_current_user with invalid token."""
        mock_decode.side_effect = HTTPException(status_code=401, detail="Invalid token")
        token = "invalid_token"
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)
        
        assert exc_info.value.status_code == 401


class TestOAuth2Integration:
    """Test OAuth2 scheme configuration."""

    def test_oauth2_scheme_token_url(self):
        """Test that OAuth2 scheme is configured with correct token URL."""
        from app.auth.security import oauth2_scheme
        
        # The tokenUrl should contain the API version string
        assert "/auth/token" in oauth2_scheme.tokenUrl