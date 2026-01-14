"""
Tests for the configuration module.
"""

import pytest
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from onprem_automation.core.config import (
    Config, VMwareConfig, NetworkConfig, PatchingConfig,
    BackupConfig, CapacityConfig, RemediationConfig
)


class TestVMwareConfig:
    """Tests for VMwareConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VMwareConfig()
        assert config.host == ""
        assert config.username == ""
        assert config.password == ""
        assert config.port == 443
        assert config.verify_ssl is True
        assert config.datacenter == ""
        assert config.cluster == ""
        assert config.datastore == ""
        assert config.template_folder == "Templates"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = VMwareConfig(
            host="vcenter.example.com",
            username="admin",
            password="secret",
            port=8443,
            verify_ssl=False,
            datacenter="DC1",
            cluster="Cluster1",
            datastore="DataStore1"
        )
        assert config.host == "vcenter.example.com"
        assert config.port == 8443
        assert config.verify_ssl is False


class TestNetworkConfig:
    """Tests for NetworkConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = NetworkConfig()
        assert config.switches == []
        assert config.firewalls == []
        assert config.default_vlan_range == (100, 4094)
        assert config.backup_before_change is True


class TestPatchingConfig:
    """Tests for PatchingConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PatchingConfig()
        assert config.wsus_server == ""
        assert config.linux_repos == []
        assert config.maintenance_window_start == "02:00"
        assert config.maintenance_window_end == "06:00"
        assert config.reboot_timeout == 600
        assert config.max_concurrent_patches == 5


class TestBackupConfig:
    """Tests for BackupConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = BackupConfig()
        assert config.backup_server == ""
        assert config.backup_type == "veeam"
        assert config.validation_vm_prefix == "restore-test-"
        assert config.retention_days == 30
        assert config.test_frequency_days == 7


class TestCapacityConfig:
    """Tests for CapacityConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CapacityConfig()
        assert config.storage_threshold_warning == 75
        assert config.storage_threshold_critical == 90
        assert config.compute_threshold_warning == 70
        assert config.compute_threshold_critical == 85
        assert config.forecast_days == 90
        assert config.data_retention_days == 365


class TestRemediationConfig:
    """Tests for RemediationConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RemediationConfig()
        assert config.monitored_services == []
        assert config.max_restart_attempts == 3
        assert config.restart_delay_seconds == 30
        assert config.escalation_email == ""
        assert config.auto_remediate is True


class TestConfig:
    """Tests for main Config class."""

    def test_default_initialization(self):
        """Test default configuration initialization."""
        config = Config()
        assert isinstance(config.vmware, VMwareConfig)
        assert isinstance(config.network, NetworkConfig)
        assert isinstance(config.patching, PatchingConfig)
        assert isinstance(config.backup, BackupConfig)
        assert isinstance(config.capacity, CapacityConfig)
        assert isinstance(config.remediation, RemediationConfig)

    def test_load_yaml_config(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
vmware:
  host: vcenter.test.com
  username: testuser
  password: testpass
  port: 443
  datacenter: TestDC
backup:
  backup_type: commvault
  retention_days: 60
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = Config(config_path=f.name)
                assert config.vmware.host == "vcenter.test.com"
                assert config.vmware.username == "testuser"
                assert config.vmware.datacenter == "TestDC"
                assert config.backup.backup_type == "commvault"
                assert config.backup.retention_days == 60
            finally:
                os.unlink(f.name)

    def test_get_method(self):
        """Test get method with dot notation."""
        yaml_content = """
vmware:
  host: vcenter.test.com
capacity:
  forecast_days: 120
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = Config(config_path=f.name)
                assert config.get("vmware.host") == "vcenter.test.com"
                assert config.get("capacity.forecast_days") == 120
                assert config.get("nonexistent.key", "default") == "default"
            finally:
                os.unlink(f.name)

    def test_save_config(self):
        """Test saving configuration to file."""
        config = Config()
        config.vmware.host = "saved.vcenter.com"
        config.backup.retention_days = 45

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            try:
                config.save(f.name)

                # Reload and verify
                loaded = Config(config_path=f.name)
                assert loaded.vmware.host == "saved.vcenter.com"
                assert loaded.backup.retention_days == 45
            finally:
                os.unlink(f.name)

    def test_from_env(self):
        """Test creating configuration from environment variables."""
        os.environ['VMWARE_HOST'] = 'env.vcenter.com'
        os.environ['VMWARE_USERNAME'] = 'envuser'
        os.environ['VMWARE_PASSWORD'] = 'envpass'

        try:
            config = Config.from_env()
            assert config.vmware.host == 'env.vcenter.com'
            assert config.vmware.username == 'envuser'
            assert config.vmware.password == 'envpass'
        finally:
            del os.environ['VMWARE_HOST']
            del os.environ['VMWARE_USERNAME']
            del os.environ['VMWARE_PASSWORD']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
