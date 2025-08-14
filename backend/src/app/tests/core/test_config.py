"""
Tests for core.config module.

This module tests Settings validation, environment variable parsing,
and database URI construction.
"""
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


class TestSettings:
    """Test Settings configuration class."""

    def test_settings_initialization_with_required_fields(self):
        """Test Settings initialization with all required fields."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db",
            POSTGRES_PORT=5432
        )
        
        assert settings.POSTGRES_SERVER == "localhost"
        assert settings.POSTGRES_USER == "test_user"
        assert settings.POSTGRES_PASSWORD == "test_pass"
        assert settings.POSTGRES_DB == "test_db"
        assert settings.POSTGRES_PORT == 5432

    def test_settings_default_values(self):
        """Test Settings default values."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db"
        )
        
        assert settings.API_V1_STR == "/api/v1"
        assert settings.PROJECT_NAME == "Kanta"
        assert settings.PROJECT_DESCRIPTION == "API for uploading faces."
        assert settings.POSTGRES_PORT == 5432
        assert settings.ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert settings.BACKEND_CORS_ORIGINS == []

    def test_postgres_port_string_conversion(self):
        """Test POSTGRES_PORT conversion from string to int."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db",
            POSTGRES_PORT="5433"  # string input
        )
        
        assert settings.POSTGRES_PORT == 5433
        assert isinstance(settings.POSTGRES_PORT, int)

    def test_postgres_port_invalid_string(self):
        """Test POSTGRES_PORT validation with invalid string."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="test_user",
                POSTGRES_PASSWORD="test_pass",
                POSTGRES_DB="test_db",
                POSTGRES_PORT="invalid_port"
            )
        
        assert "POSTGRES_PORT must be an integer" in str(exc_info.value)

    def test_sqlalchemy_database_uri_construction(self):
        """Test automatic SQLALCHEMY_DATABASE_URI construction."""
        settings = Settings(
            POSTGRES_SERVER="db.example.com",
            POSTGRES_USER="myuser",
            POSTGRES_PASSWORD="mypass",
            POSTGRES_DB="mydb",
            POSTGRES_PORT=5432
        )
        
        expected_uri = "postgresql+asyncpg://myuser:mypass@db.example.com/mydb"
        assert settings.SQLALCHEMY_DATABASE_URI == expected_uri

    def test_azure_blob_optional_fields(self):
        """Test Azure Blob Storage optional configuration fields."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db"
        )
        
        assert settings.AZURE_STORAGE_CONNECTION_STRING is None
        assert settings.AZURE_ACCOUNT_URL is None

    def test_azure_blob_with_values(self):
        """Test Azure Blob Storage configuration with values."""
        connection_string = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key"
        account_url = "https://test.blob.core.windows.net"
        
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db",
            AZURE_STORAGE_CONNECTION_STRING=connection_string,
            AZURE_ACCOUNT_URL=account_url
        )
        
        assert settings.AZURE_STORAGE_CONNECTION_STRING == connection_string
        assert settings.AZURE_ACCOUNT_URL == account_url

    @patch.dict(os.environ, {
        'POSTGRES_SERVER': 'env_server',
        'POSTGRES_USER': 'env_user',
        'POSTGRES_PASSWORD': 'env_pass',
        'POSTGRES_DB': 'env_db',
        'POSTGRES_PORT': '5433'
    })
    def test_settings_from_environment_variables(self):
        """Test Settings initialization from environment variables."""
        settings = Settings()
        
        assert settings.POSTGRES_SERVER == "env_server"
        assert settings.POSTGRES_USER == "env_user"
        assert settings.POSTGRES_PASSWORD == "env_pass"
        assert settings.POSTGRES_DB == "env_db"
        assert settings.POSTGRES_PORT == 5433

    def test_missing_required_postgres_fields(self):
        """Test validation error when required PostgreSQL fields are missing."""
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        error_str = str(exc_info.value)
        assert "POSTGRES_SERVER" in error_str
        assert "POSTGRES_USER" in error_str
        assert "POSTGRES_PASSWORD" in error_str
        assert "POSTGRES_DB" in error_str


class TestGetSettings:
    """Test get_settings function and caching."""

    @patch.dict(os.environ, {
        'POSTGRES_SERVER': 'cache_test_server',
        'POSTGRES_USER': 'cache_test_user',
        'POSTGRES_PASSWORD': 'cache_test_pass',
        'POSTGRES_DB': 'cache_test_db'
    })
    def test_get_settings_returns_settings_instance(self):
        """Test get_settings returns Settings instance."""
        # Clear cache before test
        get_settings.cache_clear()
        
        settings = get_settings()
        
        assert isinstance(settings, Settings)
        assert settings.POSTGRES_SERVER == "cache_test_server"

    @patch.dict(os.environ, {
        'POSTGRES_SERVER': 'cache_test_server',
        'POSTGRES_USER': 'cache_test_user',
        'POSTGRES_PASSWORD': 'cache_test_pass',
        'POSTGRES_DB': 'cache_test_db'
    })
    def test_get_settings_caching(self):
        """Test get_settings caching behavior."""
        # Clear cache before test
        get_settings.cache_clear()
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should return the same instance due to LRU cache
        assert settings1 is settings2


class TestSettingsConfig:
    """Test Settings configuration options."""

    def test_case_sensitive_config(self):
        """Test that Settings configuration is case sensitive."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db"
        )
        
        # Access the Config class to check case_sensitive
        assert settings.Config.case_sensitive is True

    def test_env_file_config(self):
        """Test that Settings is configured to read from .env file."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_pass",
            POSTGRES_DB="test_db"
        )
        
        assert settings.Config.env_file == ".env"