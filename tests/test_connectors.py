"""
Tests for infrastructure connectors.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from onprem_automation.connectors.base import (
    BaseConnector,
    ConnectionPool,
    ConnectionError,
    AuthenticationError,
    CommandExecutionError,
    ConnectionConfig
)


class TestBaseConnector:
    """Tests for BaseConnector."""

    def test_abstract_methods(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            BaseConnector(ConnectionConfig(
                host="test",
                username="user",
                password="pass"
            ))

    def test_connection_error_exists(self):
        """Test ConnectionError is defined."""
        assert ConnectionError is not None
        assert issubclass(ConnectionError, Exception)

    def test_authentication_error_exists(self):
        """Test AuthenticationError is defined."""
        assert AuthenticationError is not None
        assert issubclass(AuthenticationError, Exception)

    def test_command_execution_error_exists(self):
        """Test CommandExecutionError is defined."""
        assert CommandExecutionError is not None
        assert issubclass(CommandExecutionError, Exception)

    def test_connection_config_creation(self):
        """Test ConnectionConfig dataclass."""
        config = ConnectionConfig(
            host="server.example.com",
            username="admin",
            password="secret"
        )
        assert config.host == "server.example.com"
        assert config.timeout == 30
        assert config.retry_count == 3


class TestConnectionPool:
    """Tests for ConnectionPool."""

    def test_pool_initialization(self):
        """Test pool initialization."""
        # ConnectionPool requires a connector_class
        pool = ConnectionPool(connector_class=BaseConnector, max_connections=5)
        assert pool.max_connections == 5

    def test_pool_default_max_connections(self):
        """Test pool default max_connections."""
        pool = ConnectionPool(connector_class=BaseConnector)
        assert pool.max_connections == 10

    def test_pool_stores_connector_class(self):
        """Test pool stores connector class."""
        pool = ConnectionPool(connector_class=BaseConnector)
        assert pool.connector_class == BaseConnector


class TestVMwareConnector:
    """Tests for VMware connector."""

    def test_vmware_config_creation(self):
        """Test VMware config dataclass."""
        from onprem_automation.connectors.vmware_connector import VMwareConnectionConfig

        config = VMwareConnectionConfig(
            host="vcenter.example.com",
            username="admin",
            password="secret"
        )
        assert config.host == "vcenter.example.com"
        assert config.port == 443
        # Default is False for self-signed certs
        assert config.verify_ssl is False

    def test_vmware_config_custom_port(self):
        """Test VMware config with custom port."""
        from onprem_automation.connectors.vmware_connector import VMwareConnectionConfig

        config = VMwareConnectionConfig(
            host="vcenter.example.com",
            username="admin",
            password="secret",
            port=8443,
            verify_ssl=True
        )
        assert config.port == 8443
        assert config.verify_ssl is True

    def test_vmware_connector_class_exists(self):
        """Test VMware connector class exists."""
        from onprem_automation.connectors.vmware_connector import VMwareConnector
        assert VMwareConnector is not None


class TestNetworkConnector:
    """Tests for Network connector."""

    def test_network_device_config(self):
        """Test NetworkDeviceConfig dataclass."""
        from onprem_automation.connectors.network_connector import NetworkDeviceConfig

        config = NetworkDeviceConfig(
            host="10.0.0.1",
            username="admin",
            password="secret",
            device_type="cisco_ios"
        )
        assert config.host == "10.0.0.1"
        assert config.device_type == "cisco_ios"
        assert config.port == 22

    def test_network_config_default_device_type(self):
        """Test NetworkDeviceConfig with defaults."""
        from onprem_automation.connectors.network_connector import NetworkDeviceConfig

        config = NetworkDeviceConfig(
            host="10.0.0.1",
            username="admin",
            password="secret"
        )
        # device_type has a default
        assert config.host == "10.0.0.1"

    def test_supported_device_types(self):
        """Test supported device type constants."""
        from onprem_automation.connectors.network_connector import (
            CISCO_IOS, CISCO_NXOS, CISCO_ASA, JUNIPER_JUNOS, ARISTA_EOS
        )

        assert CISCO_IOS == "cisco_ios"
        assert CISCO_NXOS == "cisco_nxos"
        assert CISCO_ASA == "cisco_asa"
        assert JUNIPER_JUNOS == "juniper_junos"
        assert ARISTA_EOS == "arista_eos"


class TestServerConnector:
    """Tests for Server (SSH/WinRM) connectors."""

    def test_ssh_config_creation(self):
        """Test SSHConnectionConfig dataclass."""
        from onprem_automation.connectors.server_connector import SSHConnectionConfig

        config = SSHConnectionConfig(
            host="server.example.com",
            username="admin",
            password="secret"
        )
        assert config.host == "server.example.com"
        assert config.port == 22
        assert config.timeout == 30

    def test_ssh_config_with_key(self):
        """Test SSHConnectionConfig with key file."""
        from onprem_automation.connectors.server_connector import SSHConnectionConfig

        config = SSHConnectionConfig(
            host="server.example.com",
            username="admin",
            password="",  # Empty password when using key
            key_filename="/home/user/.ssh/id_rsa"
        )
        assert config.key_filename == "/home/user/.ssh/id_rsa"

    def test_winrm_config_creation(self):
        """Test WinRMConnectionConfig dataclass."""
        from onprem_automation.connectors.server_connector import WinRMConnectionConfig

        config = WinRMConnectionConfig(
            host="windows.example.com",
            username="Administrator",
            password="secret"
        )
        assert config.host == "windows.example.com"
        # Default is HTTP (5985), use port=5986 and use_ssl=True for HTTPS
        assert config.port == 5985
        assert config.use_ssl is False

    def test_winrm_config_http(self):
        """Test WinRMConnectionConfig with HTTP."""
        from onprem_automation.connectors.server_connector import WinRMConnectionConfig

        config = WinRMConnectionConfig(
            host="windows.example.com",
            username="admin",
            password="secret",
            port=5985,
            use_ssl=False
        )
        assert config.port == 5985
        assert config.use_ssl is False


class TestBackupConnectors:
    """Tests for Backup connectors."""

    def test_veeam_config_creation(self):
        """Test VeeamConnectionConfig dataclass."""
        from onprem_automation.connectors.backup_connectors import VeeamConnectionConfig

        config = VeeamConnectionConfig(
            host="veeam.example.com",
            username="admin",
            password="secret"
        )
        assert config.host == "veeam.example.com"
        assert config.port == 9419
        # Default is False for Veeam
        assert config.verify_ssl is False

    def test_commvault_config_creation(self):
        """Test CommvaultConnectionConfig dataclass."""
        from onprem_automation.connectors.backup_connectors import CommvaultConnectionConfig

        config = CommvaultConnectionConfig(
            host="commvault.example.com",
            username="admin",
            password="secret"
        )
        assert config.host == "commvault.example.com"
        assert config.port == 81
        assert config.verify_ssl is True

    def test_veeam_config_custom_port(self):
        """Test VeeamConnectionConfig with custom port."""
        from onprem_automation.connectors.backup_connectors import VeeamConnectionConfig

        config = VeeamConnectionConfig(
            host="veeam.example.com",
            username="admin",
            password="secret",
            port=9999,
            verify_ssl=True
        )
        assert config.port == 9999
        assert config.verify_ssl is True


class TestConnectorImports:
    """Tests for connector module imports."""

    def test_connectors_package_imports(self):
        """Test that connectors package exports correct symbols."""
        from onprem_automation.connectors import (
            BaseConnector,
            ConnectionPool,
            ConnectionError,
            AuthenticationError,
            CommandExecutionError,
            ConnectionConfig,
            VMwareConfig,
            NetworkDeviceConfig,
            SSHConfig,
            WinRMConfig,
            VeeamConfig,
            CommvaultConfig
        )

        # All should be importable
        assert BaseConnector is not None
        assert ConnectionPool is not None
        assert VMwareConfig is not None
        assert ConnectionError is not None

    def test_vmware_connector_exports(self):
        """Test VMware connector module exports."""
        from onprem_automation.connectors.vmware_connector import (
            VMwareConnectionConfig,
            VMwareConnector
        )
        assert VMwareConnectionConfig is not None
        assert VMwareConnector is not None

    def test_network_connector_exports(self):
        """Test Network connector module exports."""
        from onprem_automation.connectors.network_connector import (
            NetworkDeviceConfig,
            NetworkDeviceConnector,
            NapalmConnector,
            CISCO_IOS,
            CISCO_NXOS
        )
        assert NetworkDeviceConfig is not None
        assert NetworkDeviceConnector is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
