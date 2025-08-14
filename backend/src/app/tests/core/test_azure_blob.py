"""
Tests for core.azure_blob module.

This module tests Azure Blob Storage client setup, container operations,
and dependency injection.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from app.core.azure_blob import (
    get_blob_service,
    get_event_container,
    setup_blob_service_client,
)


class TestSetupBlobServiceClient:
    """Test BlobServiceClient setup function."""

    @patch("app.core.azure_blob.BlobServiceClient")
    def test_setup_with_connection_string(self, mock_blob_service_client):
        """Test BlobServiceClient setup with connection string."""
        connection_string = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key"
        mock_client = Mock()
        mock_blob_service_client.from_connection_string.return_value = mock_client
        
        result = setup_blob_service_client(connection_string=connection_string)
        
        mock_blob_service_client.from_connection_string.assert_called_once_with(connection_string)
        assert result == mock_client

    @patch("app.core.azure_blob.BlobServiceClient")
    @patch("app.core.azure_blob.DefaultAzureCredential")
    def test_setup_with_account_url_default_credential(self, mock_credential_class, mock_blob_service_client):
        """Test BlobServiceClient setup with account URL and default credential."""
        account_url = "https://testaccount.blob.core.windows.net"
        mock_credential = Mock()
        mock_credential_class.return_value = mock_credential
        mock_client = Mock()
        mock_blob_service_client.return_value = mock_client
        
        result = setup_blob_service_client(account_url=account_url)
        
        mock_credential_class.assert_called_once()
        mock_blob_service_client.assert_called_once_with(
            account_url=account_url, 
            credential=mock_credential
        )
        assert result == mock_client

    @patch("app.core.azure_blob.BlobServiceClient")
    def test_setup_with_account_url_custom_credential(self, mock_blob_service_client):
        """Test BlobServiceClient setup with account URL and custom credential."""
        account_url = "https://testaccount.blob.core.windows.net"
        custom_credential = Mock()
        mock_client = Mock()
        mock_blob_service_client.return_value = mock_client
        
        result = setup_blob_service_client(
            account_url=account_url, 
            credential=custom_credential
        )
        
        mock_blob_service_client.assert_called_once_with(
            account_url=account_url, 
            credential=custom_credential
        )
        assert result == mock_client

    def test_setup_without_connection_string_or_account_url(self):
        """Test that ValueError is raised when neither connection_string nor account_url provided."""
        with pytest.raises(ValueError) as exc_info:
            setup_blob_service_client()
        
        assert "Provide either connection_string or account_url" in str(exc_info.value)

    def test_setup_with_both_connection_string_and_account_url(self):
        """Test that connection_string takes precedence when both are provided."""
        connection_string = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=key"
        account_url = "https://testaccount.blob.core.windows.net"
        
        with patch("app.core.azure_blob.BlobServiceClient") as mock_blob_service_client:
            mock_client = Mock()
            mock_blob_service_client.from_connection_string.return_value = mock_client
            
            result = setup_blob_service_client(
                connection_string=connection_string,
                account_url=account_url
            )
            
            # Should use connection_string method, not account_url
            mock_blob_service_client.from_connection_string.assert_called_once_with(connection_string)
            mock_blob_service_client.assert_not_called()
            assert result == mock_client


class TestGetBlobService:
    """Test get_blob_service dependency function."""

    def test_get_blob_service_returns_client(self):
        """Test that get_blob_service returns the global BlobServiceClient."""
        # This test verifies the function returns the global client
        # Since the global client is initialized at module level,
        # we need to mock it for testing
        with patch("app.core.azure_blob._blob_client") as mock_client:
            result = get_blob_service()
            assert result == mock_client

    def test_get_blob_service_caching(self):
        """Test that get_blob_service uses LRU cache."""
        # Clear cache before test
        get_blob_service.cache_clear()
        
        with patch("app.core.azure_blob._blob_client") as mock_client:
            result1 = get_blob_service()
            result2 = get_blob_service()
            
            # Both calls should return the same instance due to caching
            assert result1 == mock_client
            assert result2 == mock_client
            assert result1 is result2


class TestGetEventContainer:
    """Test get_event_container dependency function."""

    @pytest.mark.asyncio
    async def test_get_event_container_creates_new_container(self):
        """Test container creation when container doesn't exist."""
        event_code = "TestEvent123"
        mock_blob_service = Mock(spec=BlobServiceClient)
        mock_container = AsyncMock(spec=ContainerClient)
        mock_blob_service.get_container_client.return_value = mock_container
        
        result = await get_event_container(event_code, mock_blob_service)
        
        # Container name should be lowercase
        mock_blob_service.get_container_client.assert_called_once_with("testevent123")
        mock_container.create_container.assert_called_once_with(public_access="blob")
        assert result == mock_container

    @pytest.mark.asyncio
    async def test_get_event_container_existing_container(self):
        """Test behavior when container already exists."""
        event_code = "existing_event"
        mock_blob_service = Mock(spec=BlobServiceClient)
        mock_container = AsyncMock(spec=ContainerClient)
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.create_container.side_effect = ResourceExistsError("Container already exists")
        
        result = await get_event_container(event_code, mock_blob_service)
        
        mock_blob_service.get_container_client.assert_called_once_with("existing_event")
        mock_container.create_container.assert_called_once_with(public_access="blob")
        assert result == mock_container

    @pytest.mark.asyncio
    async def test_get_event_container_normalizes_case(self):
        """Test that event code is normalized to lowercase for container name."""
        event_code = "UPPERCASE_EVENT"
        mock_blob_service = Mock(spec=BlobServiceClient)
        mock_container = AsyncMock(spec=ContainerClient)
        mock_blob_service.get_container_client.return_value = mock_container
        
        await get_event_container(event_code, mock_blob_service)
        
        mock_blob_service.get_container_client.assert_called_once_with("uppercase_event")

    @pytest.mark.asyncio
    async def test_get_event_container_with_mixed_case(self):
        """Test container creation with mixed case event code."""
        event_code = "MiXeD_CaSe_Event"
        mock_blob_service = Mock(spec=BlobServiceClient)
        mock_container = AsyncMock(spec=ContainerClient)
        mock_blob_service.get_container_client.return_value = mock_container
        
        result = await get_event_container(event_code, mock_blob_service)
        
        mock_blob_service.get_container_client.assert_called_once_with("mixed_case_event")
        assert result == mock_container

    @pytest.mark.asyncio
    async def test_get_event_container_propagates_other_exceptions(self):
        """Test that non-ResourceExistsError exceptions are propagated."""
        event_code = "test_event"
        mock_blob_service = Mock(spec=BlobServiceClient)
        mock_container = AsyncMock(spec=ContainerClient)
        mock_blob_service.get_container_client.return_value = mock_container
        mock_container.create_container.side_effect = Exception("Other error")
        
        with pytest.raises(Exception, match="Other error"):
            await get_event_container(event_code, mock_blob_service)


class TestGlobalBlobClientInitialization:
    """Test global blob client initialization."""

    def test_global_client_initialization(self):
        """Test that global blob client is initialized."""
        # Import the module to check initialization
        from app.core.azure_blob import _blob_client
        
        # The global client should exist and be a BlobServiceClient instance
        assert _blob_client is not None
        assert hasattr(_blob_client, 'get_container_client')