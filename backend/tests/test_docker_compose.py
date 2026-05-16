"""Tests for docker-compose infrastructure definitions.

Validates that the redis service, volume, and healthcheck are present
without requiring a running Docker daemon.
"""

import pathlib


class TestDockerCompose:
    """docker-compose.yml must contain the expected Redis configuration."""

    def test_redis_service_present(self) -> None:
        content = pathlib.Path("docker-compose.yml").read_text()
        assert "  redis:" in content
        assert "image: redis:7-alpine" in content
        assert '"6379:6379"' in content
        assert "redis_data:/data" in content

    def test_redis_healthcheck_present(self) -> None:
        content = pathlib.Path("docker-compose.yml").read_text()
        assert '["CMD", "redis-cli", "ping"]' in content

    def test_backend_depends_on_redis(self) -> None:
        content = pathlib.Path("docker-compose.yml").read_text()
        assert "depends_on:" in content
        assert "redis:" in content
        assert "condition: service_healthy" in content

    def test_redis_volume_declared(self) -> None:
        content = pathlib.Path("docker-compose.yml").read_text()
        assert "volumes:" in content
        assert "  redis_data:" in content
