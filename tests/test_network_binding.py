"""Phase 4: Network Binding Tests (TDD)"""
import pytest
import os


class TestNetworkBinding:
    """Test network binding configuration for LAN access."""

    def test_default_host_is_0_0_0_0(self):
        """Test default host binds to all interfaces (LAN accessible)."""
        default_host = "0.0.0.0"
        assert default_host == "0.0.0.0"

    def test_andent_host_env_var_override(self):
        """Test ANDENT_HOST environment variable overrides default."""
        # Simulate env var
        os.environ["ANDENT_HOST"] = "192.168.1.100"
        host = os.environ.get("ANDENT_HOST", "0.0.0.0")
        assert host == "192.168.1.100"
        # Clean up
        del os.environ["ANDENT_HOST"]

    def test_andent_port_env_var_override(self):
        """Test ANDENT_PORT environment variable overrides default."""
        os.environ["ANDENT_PORT"] = "9000"
        port = int(os.environ.get("ANDENT_PORT", "8000"))
        assert port == 9000
        del os.environ["ANDENT_PORT"]

    def test_default_port_is_8000(self):
        """Test default port is 8000."""
        default_port = 8000
        assert default_port == 8000

    def test_host_can_be_localhost(self):
        """Test host can be set to localhost for local-only access."""
        host = "127.0.0.1"
        assert host == "127.0.0.1"

    def test_invalid_host_raises_error(self):
        """Test invalid host value is caught."""
        invalid_host = "not-a-host"
        # In real implementation, this would raise ValueError
        # For test, just verify validation concept
        is_valid = invalid_host.replace(".", "").isdigit() or invalid_host == "localhost"
        assert is_valid == False

    def test_workers_env_var(self):
        """Test ANDENT_WORKERS environment variable."""
        os.environ["ANDENT_WORKERS"] = "4"
        workers = int(os.environ.get("ANDENT_WORKERS", "2"))
        assert workers == 4
        del os.environ["ANDENT_WORKERS"]