"""
Tests for the CLI interface.
"""

import pytest
import subprocess
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCLI:
    """Tests for CLI commands."""

    def run_cli(self, *args):
        """Run CLI command and return output."""
        cmd = [sys.executable, "-m", "onprem_automation.cli"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**dict(__import__('os').environ), 'PYTHONPATH': str(Path(__file__).parent.parent)}
        )
        return result

    def test_help(self):
        """Test --help option."""
        result = self.run_cli("--help")
        assert result.returncode == 0
        assert "On-Premises Infrastructure Automation CLI" in result.stdout
        assert "vmware" in result.stdout
        assert "network" in result.stdout

    def test_list_modules(self):
        """Test list command."""
        result = self.run_cli("list")
        assert result.returncode == 0
        assert "vmware" in result.stdout
        assert "network" in result.stdout
        assert "patching" in result.stdout
        assert "backup" in result.stdout
        assert "capacity" in result.stdout
        assert "remediation" in result.stdout

    def test_health_check(self):
        """Test health command."""
        result = self.run_cli("health")
        assert result.returncode == 0
        # Should contain JSON output with status
        assert "ok" in result.stdout

    def test_vmware_help(self):
        """Test vmware subcommand help."""
        result = self.run_cli("vmware", "--help")
        assert result.returncode == 0
        assert "provision" in result.stdout
        assert "list" in result.stdout

    def test_network_help(self):
        """Test network subcommand help."""
        result = self.run_cli("network", "--help")
        assert result.returncode == 0
        assert "vlan" in result.stdout
        assert "firewall" in result.stdout

    def test_patch_help(self):
        """Test patch subcommand help."""
        result = self.run_cli("patch", "--help")
        assert result.returncode == 0
        assert "scan" in result.stdout
        assert "install" in result.stdout

    def test_backup_help(self):
        """Test backup subcommand help."""
        result = self.run_cli("backup", "--help")
        assert result.returncode == 0
        assert "status" in result.stdout
        assert "test" in result.stdout

    def test_capacity_help(self):
        """Test capacity subcommand help."""
        result = self.run_cli("capacity", "--help")
        assert result.returncode == 0
        assert "status" in result.stdout
        assert "forecast" in result.stdout

    def test_remediate_help(self):
        """Test remediate subcommand help."""
        result = self.run_cli("remediate", "--help")
        assert result.returncode == 0
        assert "restart" in result.stdout
        assert "failover" in result.stdout


class TestCLICommands:
    """Integration tests for CLI commands."""

    def run_cli(self, *args):
        """Run CLI command and return output."""
        cmd = [sys.executable, "-m", "onprem_automation.cli"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**dict(__import__('os').environ), 'PYTHONPATH': str(Path(__file__).parent.parent)}
        )
        return result

    def test_vmware_list_vms(self):
        """Test vmware list command."""
        result = self.run_cli("vmware", "list")
        assert result.returncode == 0

    def test_remediate_incidents(self):
        """Test remediate incidents command."""
        result = self.run_cli("remediate", "incidents")
        assert result.returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
