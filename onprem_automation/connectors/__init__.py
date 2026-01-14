"""
Infrastructure Connectors Package

Provides real connections to infrastructure components:
- VMware vSphere (pyVmomi)
- Network devices (Netmiko/NAPALM)
- Linux servers (Paramiko SSH)
- Windows servers (pywinrm)
- Backup solutions (REST APIs)
"""

from .base import (
    BaseConnector,
    ConnectionPool,
    ConnectionError,
    AuthenticationError,
    CommandExecutionError,
    ConnectionConfig
)
from .vmware_connector import VMwareConnector, VMwareConnectionConfig
from .network_connector import NetworkDeviceConnector, NapalmConnector, NetworkDeviceConfig
from .server_connector import SSHConnector, WinRMConnector, SSHConnectionConfig, WinRMConnectionConfig
from .backup_connectors import VeeamConnector, CommvaultConnector, VeeamConnectionConfig, CommvaultConnectionConfig

# Create aliases for cleaner naming
VMwareConfig = VMwareConnectionConfig
SSHConfig = SSHConnectionConfig
WinRMConfig = WinRMConnectionConfig
VeeamConfig = VeeamConnectionConfig
CommvaultConfig = CommvaultConnectionConfig

__all__ = [
    # Base classes and exceptions
    "BaseConnector",
    "ConnectionPool",
    "ConnectionError",
    "AuthenticationError",
    "CommandExecutionError",
    "ConnectionConfig",
    # VMware
    "VMwareConnector",
    "VMwareConnectionConfig",
    "VMwareConfig",  # alias
    # Network
    "NetworkDeviceConnector",
    "NapalmConnector",
    "NetworkDeviceConfig",
    # Server
    "SSHConnector",
    "WinRMConnector",
    "SSHConnectionConfig",
    "WinRMConnectionConfig",
    "SSHConfig",  # alias
    "WinRMConfig",  # alias
    # Backup
    "VeeamConnector",
    "CommvaultConnector",
    "VeeamConnectionConfig",
    "CommvaultConnectionConfig",
    "VeeamConfig",  # alias
    "CommvaultConfig",  # alias
]
