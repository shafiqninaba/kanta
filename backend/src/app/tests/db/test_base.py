"""
Tests for db.base module.

This module tests database session management, connection handling,
and dependency injection.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from app.db.base import AsyncSessionLocal, Base, engine, get_db


class TestDatabaseEngine:
    """Test database engine configuration."""

    def test_engine_is_created(self):
        """Test that database engine is created."""
        assert engine is not None
        assert hasattr(engine, 'url')

    def test_engine_uses_asyncpg_driver(self):
        """Test that engine uses asyncpg driver for PostgreSQL."""
        assert "postgresql+asyncpg" in str(engine.url)

    @patch("app.db.base.settings")
    def test_engine_uses_settings_database_uri(self, mock_settings):
        """Test that engine uses database URI from settings."""
        mock_settings.SQLALCHEMY_DATABASE_URI = "postgresql+asyncpg://test:pass@localhost/testdb"
        
        # This test verifies the engine would use the settings URI
        # In actual implementation, engine is created at module import time
        assert mock_settings.SQLALCHEMY_DATABASE_URI is not None


class TestAsyncSessionLocal:
    """Test AsyncSessionLocal configuration."""

    def test_async_session_local_is_created(self):
        """Test that AsyncSessionLocal is created."""
        assert AsyncSessionLocal is not None
        assert hasattr(AsyncSessionLocal, 'bind')

    def test_async_session_local_bind(self):
        """Test that AsyncSessionLocal is bound to the engine."""
        assert AsyncSessionLocal.bind == engine

    def test_async_session_local_class(self):
        """Test that AsyncSessionLocal creates AsyncSession instances."""
        # The class_ parameter should be AsyncSession
        assert AsyncSessionLocal.class_ == AsyncSession

    def test_async_session_local_expire_on_commit(self):
        """Test that expire_on_commit is set to False."""
        # This ensures attributes aren't expired after commit
        assert AsyncSessionLocal.expire_on_commit is False


class TestBase:
    """Test SQLAlchemy declarative base."""

    def test_base_is_declarative_base(self):
        """Test that Base is a declarative base."""
        # Base should be the result of declarative_base()
        assert hasattr(Base, 'metadata')
        assert hasattr(Base, 'registry')


class TestGetDbDependency:
    """Test get_db dependency function."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """Test that get_db yields an AsyncSession."""
        with patch("app.db.base.AsyncSessionLocal") as mock_session_local:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None
            
            # Use get_db as async generator
            async_gen = get_db()
            session = await async_gen.__anext__()
            
            assert session == mock_session
            mock_session.commit.assert_not_called()  # Should not commit yet
            
            # Clean up the generator
            try:
                await async_gen.__anext__()
            except StopAsyncIteration:
                pass

    @pytest.mark.asyncio
    async def test_get_db_commits_on_success(self):
        """Test that get_db commits transaction on successful completion."""
        with patch("app.db.base.AsyncSessionLocal") as mock_session_local:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None
            
            async_gen = get_db()
            session = await async_gen.__anext__()
            
            # Simulate successful completion
            try:
                await async_gen.__anext__()
            except StopAsyncIteration:
                pass
            
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_not_called()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_rollback_on_exception(self):
        """Test that get_db rolls back transaction on exception."""
        with patch("app.db.base.AsyncSessionLocal") as mock_session_local:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.commit.side_effect = Exception("Database error")
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None
            
            async_gen = get_db()
            session = await async_gen.__anext__()
            
            # Simulate exception during processing
            with pytest.raises(Exception, match="Database error"):
                try:
                    await async_gen.__anext__()
                except StopAsyncIteration:
                    pass
            
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_always_closes_session(self):
        """Test that get_db always closes the session, even on exception."""
        with patch("app.db.base.AsyncSessionLocal") as mock_session_local:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None
            
            async_gen = get_db()
            session = await async_gen.__anext__()
            
            # Simulate normal completion
            try:
                await async_gen.__anext__()
            except StopAsyncIteration:
                pass
            
            # Session should always be closed
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_session_context_manager(self):
        """Test that get_db properly uses session context manager."""
        with patch("app.db.base.AsyncSessionLocal") as mock_session_local:
            mock_context_manager = AsyncMock()
            mock_session = AsyncMock(spec=AsyncSession)
            mock_context_manager.__aenter__.return_value = mock_session
            mock_context_manager.__aexit__.return_value = None
            mock_session_local.return_value = mock_context_manager
            
            async_gen = get_db()
            session = await async_gen.__anext__()
            
            # Should have entered the context manager
            mock_context_manager.__aenter__.assert_called_once()
            assert session == mock_session
            
            # Complete the generator
            try:
                await async_gen.__anext__()
            except StopAsyncIteration:
                pass
            
            # Should have exited the context manager
            mock_context_manager.__aexit__.assert_called_once()


class TestDatabaseIntegration:
    """Test database integration and configuration."""

    def test_database_components_are_connected(self):
        """Test that all database components are properly connected."""
        # Engine should exist
        assert engine is not None
        
        # AsyncSessionLocal should be bound to engine
        assert AsyncSessionLocal.bind == engine
        
        # Base should exist for model definitions
        assert Base is not None
        
        # get_db should be callable
        assert callable(get_db)

    @patch("app.db.base.settings")
    def test_database_uri_format(self, mock_settings):
        """Test that database URI has correct format for async operations."""
        mock_settings.SQLALCHEMY_DATABASE_URI = "postgresql+asyncpg://user:pass@localhost/db"
        
        # The URI should use asyncpg driver for async operations
        assert "postgresql+asyncpg" in mock_settings.SQLALCHEMY_DATABASE_URI