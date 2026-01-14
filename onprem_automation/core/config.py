"""
Configuration management for the automation system.
Handles loading, validation, and access to configuration settings.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class VMwareConfig:
    """VMware vCenter configuration."""
    host: str = ""
    username: str = ""
    password: str = ""
    port: int = 443
    verify_ssl: bool = True
    datacenter: str = ""
    cluster: str = ""
    datastore: str = ""
    template_folder: str = "Templates"


@dataclass
class NetworkConfig:
    """Network device configuration."""
    switches: list = field(default_factory=list)
    firewalls: list = field(default_factory=list)
    default_vlan_range: tuple = (100, 4094)
    backup_before_change: bool = True


@dataclass
class PatchingConfig:
    """Patching configuration."""
    wsus_server: str = ""
    linux_repos: list = field(default_factory=list)
    maintenance_window_start: str = "02:00"
    maintenance_window_end: str = "06:00"
    reboot_timeout: int = 600
    max_concurrent_patches: int = 5


@dataclass
class BackupConfig:
    """Backup validation configuration."""
    backup_server: str = ""
    backup_type: str = "veeam"  # veeam, commvault, netbackup
    validation_vm_prefix: str = "restore-test-"
    retention_days: int = 30
    test_frequency_days: int = 7


@dataclass
class CapacityConfig:
    """Capacity management configuration."""
    storage_threshold_warning: int = 75
    storage_threshold_critical: int = 90
    compute_threshold_warning: int = 70
    compute_threshold_critical: int = 85
    forecast_days: int = 90
    data_retention_days: int = 365


@dataclass
class RemediationConfig:
    """Incident remediation configuration."""
    monitored_services: list = field(default_factory=list)
    max_restart_attempts: int = 3
    restart_delay_seconds: int = 30
    escalation_email: str = ""
    auto_remediate: bool = True


@dataclass
class ServiceNowConfig:
    """ServiceNow integration configuration."""
    instance: str = ""  # e.g., 'dev12345' for dev12345.service-now.com
    username: str = ""
    password: str = ""
    enabled: bool = False
    default_assignment_group: str = ""
    auto_create_incidents: bool = False


@dataclass
class JiraConfig:
    """Jira integration configuration."""
    url: str = ""  # e.g., 'https://yourcompany.atlassian.net'
    username: str = ""  # Email for Cloud
    api_token: str = ""
    enabled: bool = False
    is_cloud: bool = True
    default_project: str = ""


@dataclass
class PagerDutyConfig:
    """PagerDuty integration configuration."""
    api_key: str = ""
    integration_key: str = ""  # For events API
    enabled: bool = False
    region: str = "us"  # 'us' or 'eu'
    default_service_id: str = ""


@dataclass
class MetricsConfig:
    """Prometheus metrics configuration."""
    enabled: bool = True
    port: int = 9090
    address: str = ""  # Empty for all interfaces
    prefix: str = "onprem_automation"


class Config:
    """Main configuration class that loads and manages all settings."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self._raw_config: Dict[str, Any] = {}

        # Initialize sub-configurations
        self.vmware = VMwareConfig()
        self.network = NetworkConfig()
        self.patching = PatchingConfig()
        self.backup = BackupConfig()
        self.capacity = CapacityConfig()
        self.remediation = RemediationConfig()

        # ITSM integrations
        self.servicenow = ServiceNowConfig()
        self.jira = JiraConfig()
        self.pagerduty = PagerDutyConfig()

        # Metrics
        self.metrics = MetricsConfig()

        if self.config_path and Path(self.config_path).exists():
            self.load()

    def _find_config_file(self) -> Optional[str]:
        """Search for configuration file in standard locations."""
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path.home() / ".onprem_automation" / "config.yaml",
            Path("/etc/onprem_automation/config.yaml"),
        ]

        for path in search_paths:
            if path.exists():
                return str(path)
        return None

    def load(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path:
            return

        with open(self.config_path, 'r') as f:
            self._raw_config = yaml.safe_load(f) or {}

        self._apply_config()

    def _apply_config(self) -> None:
        """Apply loaded configuration to dataclass instances."""
        if 'vmware' in self._raw_config:
            self.vmware = VMwareConfig(**self._raw_config['vmware'])

        if 'network' in self._raw_config:
            self.network = NetworkConfig(**self._raw_config['network'])

        if 'patching' in self._raw_config:
            self.patching = PatchingConfig(**self._raw_config['patching'])

        if 'backup' in self._raw_config:
            self.backup = BackupConfig(**self._raw_config['backup'])

        if 'capacity' in self._raw_config:
            self.capacity = CapacityConfig(**self._raw_config['capacity'])

        if 'remediation' in self._raw_config:
            self.remediation = RemediationConfig(**self._raw_config['remediation'])

        # ITSM integrations
        if 'servicenow' in self._raw_config:
            self.servicenow = ServiceNowConfig(**self._raw_config['servicenow'])

        if 'jira' in self._raw_config:
            self.jira = JiraConfig(**self._raw_config['jira'])

        if 'pagerduty' in self._raw_config:
            self.pagerduty = PagerDutyConfig(**self._raw_config['pagerduty'])

        # Metrics
        if 'metrics' in self._raw_config:
            self.metrics = MetricsConfig(**self._raw_config['metrics'])

    def save(self, path: Optional[str] = None) -> None:
        """Save current configuration to YAML file."""
        save_path = path or self.config_path
        if not save_path:
            raise ValueError("No configuration path specified")

        config_dict = {
            'vmware': self.vmware.__dict__,
            'network': self.network.__dict__,
            'patching': self.patching.__dict__,
            'backup': self.backup.__dict__,
            'capacity': self.capacity.__dict__,
            'remediation': self.remediation.__dict__,
            'servicenow': self.servicenow.__dict__,
            'jira': self.jira.__dict__,
            'pagerduty': self.pagerduty.__dict__,
            'metrics': self.metrics.__dict__,
        }

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key."""
        keys = key.split('.')
        value = self._raw_config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables."""
        config = cls()

        # VMware settings from environment
        config.vmware.host = os.getenv('VMWARE_HOST', '')
        config.vmware.username = os.getenv('VMWARE_USERNAME', '')
        config.vmware.password = os.getenv('VMWARE_PASSWORD', '')

        return config
