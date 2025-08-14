"""
Tests for system.router module.

This module tests the system health check endpoint and router configuration.
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.system.router import router


class TestSystemRouter:
    """Test system router configuration."""

    def test_router_has_correct_tags(self):
        """Test that router has correct tags."""
        assert "system" in router.tags

    def test_router_has_correct_prefix(self):
        """Test that router has correct prefix."""
        assert router.prefix == "/system"


class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with system router."""
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_health_endpoint_returns_ok_status(self, client):
        """Test that health endpoint returns OK status."""
        response = client.get("/system/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_endpoint_content_type(self, client):
        """Test that health endpoint returns JSON content."""
        response = client.get("/system/health")
        
        assert "application/json" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_health_endpoint_async_function(self):
        """Test that health endpoint is an async function."""
        from app.system.router import get_health_status
        
        # Test that the function is async
        import asyncio
        assert asyncio.iscoroutinefunction(get_health_status)
        
        # Test direct function call
        result = await get_health_status()
        assert result == {"status": "ok"}

    def test_health_endpoint_path(self, client):
        """Test that health endpoint is accessible at correct path."""
        response = client.get("/system/health")
        assert response.status_code == 200
        
        # Test that wrong paths return 404
        response = client.get("/system/healthcheck")
        assert response.status_code == 404
        
        response = client.get("/health")
        assert response.status_code == 404

    def test_health_endpoint_methods(self, client):
        """Test that health endpoint only accepts GET requests."""
        # GET should work
        response = client.get("/system/health")
        assert response.status_code == 200
        
        # Other methods should not be allowed
        response = client.post("/system/health")
        assert response.status_code == 405  # Method Not Allowed
        
        response = client.put("/system/health")
        assert response.status_code == 405
        
        response = client.delete("/system/health")
        assert response.status_code == 405

    def test_health_endpoint_response_structure(self, client):
        """Test that health endpoint returns properly structured response."""
        response = client.get("/system/health")
        
        assert response.status_code == 200
        
        json_response = response.json()
        assert isinstance(json_response, dict)
        assert "status" in json_response
        assert json_response["status"] == "ok"
        assert len(json_response) == 1  # Should only have 'status' field

    def test_multiple_health_requests(self, client):
        """Test multiple consecutive health check requests."""
        for _ in range(5):
            response = client.get("/system/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_health_endpoint_performance(self, client):
        """Test that health endpoint responds quickly."""
        import time
        
        start_time = time.time()
        response = client.get("/system/health")
        end_time = time.time()
        
        assert response.status_code == 200
        # Health check should be very fast (less than 1 second)
        assert (end_time - start_time) < 1.0


class TestSystemRouterIntegration:
    """Test system router integration with FastAPI."""

    def test_router_can_be_included_in_app(self):
        """Test that system router can be included in FastAPI app."""
        app = FastAPI()
        app.include_router(router)
        
        # Check that route is properly registered
        routes = [route.path for route in app.routes]
        assert any("/system/health" in route for route in routes)

    def test_router_with_custom_prefix(self):
        """Test system router with custom prefix."""
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        
        client = TestClient(app)
        response = client.get("/api/v1/system/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_router_with_dependencies(self):
        """Test that system router works with FastAPI dependencies."""
        from fastapi import Depends
        
        def dummy_dependency():
            return "dependency_value"
        
        app = FastAPI()
        app.include_router(router, dependencies=[Depends(dummy_dependency)])
        
        client = TestClient(app)
        response = client.get("/system/health")
        
        # Should still work despite the dependency
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}