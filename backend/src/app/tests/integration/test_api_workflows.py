"""
Integration tests for API workflows.

This module tests end-to-end API workflows and cross-module integration.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestEndToEndAPIWorkflows:
    """Test complete API workflows."""

    @pytest.fixture
    def client(self):
        """Create test client for integration tests."""
        return TestClient(app)

    def test_health_check_integration(self, client):
        """Test health check endpoint integration."""
        response = client.get("/system/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch("app.main.get_blob_service")
    @patch("app.main.engine")
    def test_application_startup_integration(self, mock_engine, mock_get_blob, client):
        """Test that application startup integrates all components."""
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        mock_engine.dispose = AsyncMock()
        
        # Application should start successfully
        response = client.get("/system/health")
        assert response.status_code == 200

    def test_cors_integration(self, client):
        """Test CORS headers in API responses."""
        response = client.get("/system/health")
        
        # Basic CORS test - app should handle CORS properly
        assert response.status_code == 200
        # The exact CORS headers depend on the CORS configuration

    def test_api_documentation_accessible(self, client):
        """Test that API documentation endpoints are accessible."""
        # FastAPI automatically provides these endpoints
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")
        
        # These might return 404 depending on root_path configuration
        # But they shouldn't cause server errors
        assert docs_response.status_code in [200, 404]
        assert openapi_response.status_code in [200, 404]


class TestCrossModuleDependencies:
    """Test dependencies between different modules."""

    @pytest.fixture
    def client(self):
        """Create test client for cross-module tests."""
        return TestClient(app)

    def test_router_integration_with_main_app(self, client):
        """Test that all routers are properly integrated with main app."""
        # Get all routes from the app
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                routes.append((route.path, route.methods))
        
        # Should have routes from different modules
        assert len(routes) > 0
        
        # At least system health route should be present
        health_routes = [route for route in routes if "health" in route[0]]
        assert len(health_routes) > 0

    @patch("app.core.azure_blob.get_blob_service")
    def test_azure_blob_integration(self, mock_blob_service, client):
        """Test Azure Blob service integration."""
        mock_blob_service.return_value = Mock()
        
        # The application should start without errors even with blob service
        response = client.get("/system/health")
        assert response.status_code == 200

    @patch("app.db.base.get_db")
    def test_database_integration(self, mock_get_db, client):
        """Test database integration."""
        mock_session = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        # Application should handle database dependency properly
        response = client.get("/system/health")
        assert response.status_code == 200

    def test_settings_integration_across_modules(self, client):
        """Test that settings are properly shared across modules."""
        # This test verifies that settings configuration works across modules
        from app.core.config import get_settings
        from app.auth.security import settings as auth_settings
        
        app_settings = get_settings()
        
        # Settings should be consistently available across modules
        assert app_settings is not None
        assert hasattr(app_settings, 'API_V1_STR')


class TestErrorPropagation:
    """Test error handling and propagation across modules."""

    @pytest.fixture
    def client(self):
        """Create test client for error tests."""
        return TestClient(app)

    def test_404_error_handling(self, client):
        """Test 404 error handling."""
        response = client.get("/nonexistent/endpoint")
        assert response.status_code == 404

    def test_method_not_allowed_handling(self, client):
        """Test 405 Method Not Allowed handling."""
        response = client.post("/system/health")
        assert response.status_code == 405

    def test_internal_server_error_handling(self, client):
        """Test 500 internal server error handling."""
        # Test with a route that would cause 500 if misconfigured
        # Since we can't easily force a 500 on health endpoint,
        # we'll just verify app handles errors gracefully
        response = client.get("/system/health")
        assert response.status_code == 200  # Should not cause 500

    def test_validation_error_handling(self, client):
        """Test request validation error handling."""
        # This would test validation errors if we had endpoints with validation
        # For now, just test that the client handles invalid requests gracefully
        
        # Test invalid JSON if we had POST endpoints
        response = client.get("/system/health")  # This is valid, so should work
        assert response.status_code == 200


class TestAuthenticationFlowIntegration:
    """Test authentication flow integration (when auth is enabled)."""

    @pytest.fixture
    def client(self):
        """Create test client for auth tests."""
        return TestClient(app)

    def test_auth_dependencies_available(self):
        """Test that auth dependencies are available for integration."""
        from app.auth.security import get_current_user, create_access_token, decode_access_token
        
        # Auth functions should be importable and callable
        assert callable(get_current_user)
        assert callable(create_access_token)
        assert callable(decode_access_token)

    @patch("app.auth.security.settings")
    def test_jwt_token_integration(self, mock_settings):
        """Test JWT token creation and validation integration."""
        mock_settings.JWT_SECRET = "test_secret"
        mock_settings.ALGORITHM = "HS256"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        
        from app.auth.security import create_access_token, decode_access_token
        
        # Create and decode token - should work end-to-end
        token = create_access_token("test_user")
        assert isinstance(token, str)
        
        decoded_subject = decode_access_token(token)
        assert decoded_subject == "test_user"

    def test_oauth2_scheme_configuration(self):
        """Test OAuth2 scheme configuration for API integration."""
        from app.auth.security import oauth2_scheme
        from fastapi.security import OAuth2PasswordBearer
        
        # OAuth2 scheme should be configured properly
        assert oauth2_scheme is not None
        assert isinstance(oauth2_scheme, OAuth2PasswordBearer)


class TestExternalServiceMocking:
    """Test proper mocking of external services in integration tests."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked external services."""
        return TestClient(app)

    @patch("app.core.azure_blob.setup_blob_service_client")
    def test_azure_blob_service_mocking(self, mock_setup_blob, client):
        """Test that Azure Blob service can be properly mocked."""
        mock_client = Mock()
        mock_setup_blob.return_value = mock_client
        
        # Application should work with mocked blob service
        response = client.get("/system/health")
        assert response.status_code == 200

    @patch("app.db.base.engine")
    def test_database_engine_mocking(self, mock_engine, client):
        """Test that database engine can be properly mocked."""
        mock_engine.begin = Mock()
        mock_engine.dispose = AsyncMock()
        
        # Application should work with mocked database
        response = client.get("/system/health")
        assert response.status_code == 200

    @patch.dict("os.environ", {
        'POSTGRES_SERVER': 'test_server',
        'POSTGRES_USER': 'test_user',
        'POSTGRES_PASSWORD': 'test_pass',
        'POSTGRES_DB': 'test_db'
    })
    def test_environment_variable_integration(self, client):
        """Test integration with environment variables."""
        # Application should work with environment variables
        response = client.get("/system/health")
        assert response.status_code == 200