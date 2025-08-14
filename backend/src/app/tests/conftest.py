"""
Root conftest.py for all test modules.

This file contains shared fixtures and configuration for all tests.
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Add the app directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def utc_now():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_async_session():
    """Return a mock async SQLAlchemy session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_settings():
    """Mock settings object with common test values."""
    settings = MagicMock()
    settings.API_V1_STR = "/api/v1"
    settings.PROJECT_NAME = "Test Kanta"
    settings.PROJECT_DESCRIPTION = "Test API for uploading faces."
    settings.POSTGRES_SERVER = "localhost"
    settings.POSTGRES_USER = "test_user"
    settings.POSTGRES_PASSWORD = "test_pass"
    settings.POSTGRES_DB = "test_db"
    settings.POSTGRES_PORT = 5432
    settings.SQLALCHEMY_DATABASE_URI = "postgresql+asyncpg://test_user:test_pass@localhost/test_db"
    settings.AZURE_STORAGE_CONNECTION_STRING = None
    settings.AZURE_ACCOUNT_URL = None
    settings.JWT_SECRET = "test_secret_key"
    settings.ALGORITHM = "HS256"
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    settings.BACKEND_CORS_ORIGINS = []
    return settings


@pytest.fixture
def sample_jwt_payload():
    """Sample JWT payload for testing."""
    return {
        "sub": "test_user",
        "exp": datetime.now(timezone.utc).timestamp() + 1800  # 30 minutes from now
    }


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return "test_user_123"