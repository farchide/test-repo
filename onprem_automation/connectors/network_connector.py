"""
Network Device Connectors

Provides real connections to network devices using:
- Netmiko: SSH-based CLI automation
- NAPALM: Multi-vendor network abstraction
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import time

from .base import (
    BaseConnector, ConnectionConfig, ConnectionError,
    AuthenticationError, CommandExecutionError
)

# Import Netmiko
try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import (
        NetmikoTimeoutException,
        NetmikoAuthenticationException,
    )
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False
    ConnectHandler = None

# Import NAPALM
try:
    from napalm import get_network_driver
    NAPALM_AVAILABLE = True
except ImportError:
    NAPALM_AVAILABLE = False
    get_network_driver = None


# Supported device type constants (for Netmiko)
CISCO_IOS = "cisco_ios"
CISCO_NXOS = "cisco_nxos"
CISCO_ASA = "cisco_asa"
CISCO_XR = "cisco_xr"
JUNIPER_JUNOS = "juniper_junos"
ARISTA_EOS = "arista_eos"
HP_PROCURVE = "hp_procurve"
HP_COMWARE = "hp_comware"
FORTINET = "fortinet"
PALOALTO_PANOS = "paloalto_panos"


@dataclass
class NetworkDeviceConfig(ConnectionConfig):
    """Network device connection configuration."""
    device_type: str = "cisco_ios"  # netmiko device type
    port: int = 22
    secret: str = ""  # Enable password
    timeout: int = 30
    session_timeout: int = 60
    global_delay_factor: float = 1.0


class NetworkDeviceConnector(BaseConnector):
    """
    Network device connector using Netmiko.

    Supports multiple vendor platforms:
    - Cisco IOS/IOS-XE/NX-OS/ASA
    - Juniper Junos
    - Arista EOS
    - HP/Aruba
    - And many more via Netmiko
    """

    # Mapping of friendly names to netmiko device types
    DEVICE_TYPE_MAP = {
        "cisco_ios": "cisco_ios",
        "cisco_nxos": "cisco_nxos",
        "cisco_asa": "cisco_asa",
        "cisco_xe": "cisco_xe",
        "juniper": "juniper_junos",
        "juniper_junos": "juniper_junos",
        "arista": "arista_eos",
        "arista_eos": "arista_eos",
        "paloalto": "paloalto_panos",
        "fortinet": "fortinet",
        "hp_procurve": "hp_procurve",
        "linux": "linux",
    }

    def __init__(self, config: NetworkDeviceConfig, logger=None):
        super().__init__(config, logger)
        self.config: NetworkDeviceConfig = config
        self._session = None

    def connect(self) -> bool:
        """
        Establish SSH connection to network device.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        if not NETMIKO_AVAILABLE:
            raise ConnectionError(
                "Netmiko is not installed. Install with: pip install netmiko"
            )

        device_type = self.DEVICE_TYPE_MAP.get(
            self.config.device_type, self.config.device_type
        )

        device_params = {
            "device_type": device_type,
            "host": self.config.host,
            "username": self.config.username,
            "password": self.config.password,
            "port": self.config.port,
            "timeout": self.config.timeout,
            "session_timeout": self.config.session_timeout,
            "global_delay_factor": self.config.global_delay_factor,
        }

        if self.config.secret:
            device_params["secret"] = self.config.secret

        try:
            self.logger.info(f"Connecting to network device: {self.config.host}")
            self._session = ConnectHandler(**device_params)
            self._connected = True
            self._connection_time = time.time()
            self.logger.info(f"Successfully connected to: {self.config.host}")
            return True

        except NetmikoAuthenticationException as e:
            raise AuthenticationError(f"Authentication failed: {str(e)}")
        except NetmikoTimeoutException as e:
            raise ConnectionError(f"Connection timeout: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Disconnect from network device."""
        if self._session:
            try:
                self._session.disconnect()
                self.logger.info(f"Disconnected from: {self.config.host}")
            except Exception as e:
                self.logger.warning(f"Error during disconnect: {e}")
            finally:
                self._session = None
                self._connected = False

    def health_check(self) -> Dict[str, Any]:
        """Check device connection health."""
        if not self._connected or not self._session:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            # Send a simple command to verify connection
            self._session.send_command("", expect_string=r"[>#$]", read_timeout=5)
            latency = time.time() - start

            return {
                "status": "healthy",
                "host": self.config.host,
                "device_type": self.config.device_type,
                "latency_ms": round(latency * 1000, 2),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "host": self.config.host,
                "error": str(e)
            }

    def send_command(
        self,
        command: str,
        expect_string: str = None,
        read_timeout: int = 30,
        strip_prompt: bool = True,
        strip_command: bool = True
    ) -> str:
        """
        Send a command and return output.

        Args:
            command: Command to execute
            expect_string: Expected prompt pattern
            read_timeout: Timeout for command
            strip_prompt: Remove prompt from output
            strip_command: Remove command from output

        Returns:
            Command output as string
        """
        if not self._connected:
            raise ConnectionError("Not connected to device")

        try:
            output = self._session.send_command(
                command,
                expect_string=expect_string,
                read_timeout=read_timeout,
                strip_prompt=strip_prompt,
                strip_command=strip_command,
            )
            return output
        except Exception as e:
            raise CommandExecutionError(f"Command execution failed: {str(e)}")

    def send_config_set(
        self,
        config_commands: Union[str, List[str]],
        exit_config_mode: bool = True,
        read_timeout: int = 30
    ) -> str:
        """
        Send configuration commands.

        Args:
            config_commands: Single command or list of commands
            exit_config_mode: Exit config mode after commands
            read_timeout: Timeout for commands

        Returns:
            Configuration output
        """
        if not self._connected:
            raise ConnectionError("Not connected to device")

        if isinstance(config_commands, str):
            config_commands = [config_commands]

        try:
            output = self._session.send_config_set(
                config_commands,
                exit_config_mode=exit_config_mode,
                read_timeout=read_timeout,
            )
            return output
        except Exception as e:
            raise CommandExecutionError(f"Configuration failed: {str(e)}")

    def enable(self) -> None:
        """Enter enable mode."""
        if not self._connected:
            raise ConnectionError("Not connected to device")
        self._session.enable()

    def save_config(self) -> str:
        """Save running configuration to startup."""
        if not self._connected:
            raise ConnectionError("Not connected to device")
        return self._session.save_config()

    def get_running_config(self) -> str:
        """Get running configuration."""
        return self.send_command("show running-config")

    def get_version(self) -> str:
        """Get device version information."""
        device_type = self.config.device_type.lower()
        if "cisco" in device_type:
            return self.send_command("show version")
        elif "juniper" in device_type:
            return self.send_command("show version")
        elif "arista" in device_type:
            return self.send_command("show version")
        else:
            return self.send_command("show version")

    # ==================== VLAN Operations ====================

    def create_vlan(self, vlan_id: int, name: str, description: str = "") -> Dict[str, Any]:
        """Create a VLAN on the device."""
        commands = [
            f"vlan {vlan_id}",
            f"name {name}",
        ]
        if description:
            commands.append(f"description {description}")

        try:
            output = self.send_config_set(commands)
            self.save_config()
            return {
                "status": "success",
                "message": f"VLAN {vlan_id} created",
                "output": output
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_vlan(self, vlan_id: int) -> Dict[str, Any]:
        """Delete a VLAN from the device."""
        try:
            output = self.send_config_set([f"no vlan {vlan_id}"])
            self.save_config()
            return {
                "status": "success",
                "message": f"VLAN {vlan_id} deleted",
                "output": output
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_vlans(self) -> Dict[str, Any]:
        """Get VLAN information from device."""
        try:
            output = self.send_command("show vlan brief")
            return {
                "status": "success",
                "output": output,
                "vlans": self._parse_vlans(output)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _parse_vlans(self, output: str) -> List[Dict[str, Any]]:
        """Parse VLAN output (basic parser for Cisco)."""
        vlans = []
        for line in output.split('\n'):
            parts = line.split()
            if parts and parts[0].isdigit():
                vlans.append({
                    "id": int(parts[0]),
                    "name": parts[1] if len(parts) > 1 else "",
                    "status": parts[2] if len(parts) > 2 else "",
                })
        return vlans

    # ==================== Interface Operations ====================

    def configure_interface(
        self,
        interface: str,
        description: str = None,
        vlan: int = None,
        mode: str = None,  # access or trunk
        shutdown: bool = None
    ) -> Dict[str, Any]:
        """Configure an interface."""
        commands = [f"interface {interface}"]

        if description is not None:
            commands.append(f"description {description}")
        if vlan is not None and mode == "access":
            commands.append("switchport mode access")
            commands.append(f"switchport access vlan {vlan}")
        if mode == "trunk":
            commands.append("switchport mode trunk")
        if shutdown is not None:
            commands.append("shutdown" if shutdown else "no shutdown")

        try:
            output = self.send_config_set(commands)
            self.save_config()
            return {
                "status": "success",
                "message": f"Interface {interface} configured",
                "output": output
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_interfaces(self) -> Dict[str, Any]:
        """Get interface status."""
        try:
            output = self.send_command("show interface status")
            return {"status": "success", "output": output}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==================== ACL/Firewall Operations ====================

    def add_acl_entry(
        self,
        acl_name: str,
        action: str,
        protocol: str,
        source: str,
        destination: str,
        port: str = None
    ) -> Dict[str, Any]:
        """Add an ACL entry."""
        acl_entry = f"{action} {protocol} {source} {destination}"
        if port:
            acl_entry += f" eq {port}"

        commands = [
            f"ip access-list extended {acl_name}",
            acl_entry
        ]

        try:
            output = self.send_config_set(commands)
            self.save_config()
            return {
                "status": "success",
                "message": f"ACL entry added to {acl_name}",
                "output": output
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def backup_config(self, filename: str = None) -> Dict[str, Any]:
        """Backup running configuration."""
        try:
            config = self.get_running_config()
            return {
                "status": "success",
                "config": config,
                "host": self.config.host,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


class NapalmConnector(BaseConnector):
    """
    Network device connector using NAPALM.

    Provides vendor-agnostic operations:
    - Configuration management
    - Operational data retrieval
    - Configuration diff and commit
    """

    DRIVER_MAP = {
        "cisco_ios": "ios",
        "cisco_nxos": "nxos",
        "juniper": "junos",
        "arista": "eos",
        "eos": "eos",
    }

    def __init__(self, config: NetworkDeviceConfig, logger=None):
        super().__init__(config, logger)
        self.config: NetworkDeviceConfig = config
        self._driver = None
        self._device = None

    def connect(self) -> bool:
        """Establish connection using NAPALM."""
        if not NAPALM_AVAILABLE:
            raise ConnectionError(
                "NAPALM is not installed. Install with: pip install napalm"
            )

        driver_name = self.DRIVER_MAP.get(
            self.config.device_type, self.config.device_type
        )

        try:
            self.logger.info(f"Connecting via NAPALM to: {self.config.host}")

            self._driver = get_network_driver(driver_name)
            self._device = self._driver(
                hostname=self.config.host,
                username=self.config.username,
                password=self.config.password,
                optional_args={
                    "port": self.config.port,
                    "secret": self.config.secret,
                }
            )
            self._device.open()
            self._connected = True
            self._connection_time = time.time()

            self.logger.info(f"NAPALM connected to: {self.config.host}")
            return True

        except Exception as e:
            raise ConnectionError(f"NAPALM connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Close NAPALM connection."""
        if self._device:
            try:
                self._device.close()
                self.logger.info(f"NAPALM disconnected from: {self.config.host}")
            except Exception as e:
                self.logger.warning(f"Error during NAPALM disconnect: {e}")
            finally:
                self._device = None
                self._connected = False

    def health_check(self) -> Dict[str, Any]:
        """Check NAPALM connection health."""
        if not self._connected or not self._device:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            facts = self._device.get_facts()
            latency = time.time() - start

            return {
                "status": "healthy",
                "host": self.config.host,
                "latency_ms": round(latency * 1000, 2),
                "vendor": facts.get("vendor"),
                "model": facts.get("model"),
                "os_version": facts.get("os_version"),
                "serial_number": facts.get("serial_number"),
                "hostname": facts.get("hostname"),
            }
        except Exception as e:
            return {"status": "unhealthy", "host": self.config.host, "error": str(e)}

    # ==================== NAPALM Getters ====================

    def get_facts(self) -> Dict[str, Any]:
        """Get device facts."""
        return self._device.get_facts()

    def get_interfaces(self) -> Dict[str, Any]:
        """Get interface information."""
        return self._device.get_interfaces()

    def get_interfaces_ip(self) -> Dict[str, Any]:
        """Get interface IP addresses."""
        return self._device.get_interfaces_ip()

    def get_lldp_neighbors(self) -> Dict[str, Any]:
        """Get LLDP neighbor information."""
        return self._device.get_lldp_neighbors()

    def get_bgp_neighbors(self) -> Dict[str, Any]:
        """Get BGP neighbor information."""
        return self._device.get_bgp_neighbors()

    def get_arp_table(self) -> List[Dict[str, Any]]:
        """Get ARP table."""
        return self._device.get_arp_table()

    def get_mac_address_table(self) -> List[Dict[str, Any]]:
        """Get MAC address table."""
        return self._device.get_mac_address_table()

    def get_config(self, retrieve: str = "all") -> Dict[str, str]:
        """
        Get device configuration.

        Args:
            retrieve: 'all', 'running', 'startup', or 'candidate'
        """
        return self._device.get_config(retrieve=retrieve)

    # ==================== Configuration Management ====================

    def load_merge_candidate(self, config: str) -> None:
        """Load configuration to merge with existing."""
        self._device.load_merge_candidate(config=config)

    def load_replace_candidate(self, config: str) -> None:
        """Load configuration to replace existing."""
        self._device.load_replace_candidate(config=config)

    def compare_config(self) -> str:
        """Compare candidate config with running config."""
        return self._device.compare_config()

    def commit_config(self) -> None:
        """Commit candidate configuration."""
        self._device.commit_config()

    def discard_config(self) -> None:
        """Discard candidate configuration."""
        self._device.discard_config()

    def rollback(self) -> None:
        """Rollback to previous configuration."""
        self._device.rollback()
