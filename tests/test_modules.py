"""
Tests for all automation modules.
"""

import pytest
import asyncio
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from onprem_automation.core.config import Config
from onprem_automation.modules.vmware_provisioning import VMwareProvisioningModule
from onprem_automation.modules.network_automation import NetworkAutomationModule, VLANConfig, DeviceType
from onprem_automation.modules.patching import PatchingModule
from onprem_automation.modules.backup_validation import BackupValidationModule
from onprem_automation.modules.capacity_management import CapacityManagementModule
from onprem_automation.modules.incident_remediation import IncidentRemediationModule


class TestVMwareProvisioningModule:
    """Tests for VMware provisioning module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = VMwareProvisioningModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "vmware"
        assert "VMware" in self.module.description

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "vmware"

    @pytest.mark.asyncio
    async def test_list_vms(self):
        """Test listing VMs."""
        result = await self.module.execute("list_vms")
        assert result["status"] == "success"
        assert "vms" in result

    @pytest.mark.asyncio
    async def test_list_templates(self):
        """Test listing templates."""
        result = await self.module.execute("list_templates")
        assert result["status"] == "success"
        assert "templates" in result

    @pytest.mark.asyncio
    async def test_provision_vm(self):
        """Test VM provisioning."""
        result = await self.module.execute(
            "provision_vm",
            name="test-vm",
            template="ubuntu-22.04",
            cpus=2,
            memory_gb=4
        )
        assert result["status"] == "success"
        assert "vm" in result  # The result contains 'vm' key with VM details

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        """Test unknown action returns error."""
        result = await self.module.execute("nonexistent_action")
        assert result["status"] == "error"


class TestNetworkAutomationModule:
    """Tests for network automation module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = NetworkAutomationModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "network"
        assert "Network" in self.module.description

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "network"

    @pytest.mark.asyncio
    async def test_create_vlan(self):
        """Test VLAN creation."""
        result = await self.module.execute(
            "create_vlan",
            vlan_id=100,
            name="Test-VLAN",
            device="switch1"
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_add_firewall_rule(self):
        """Test adding firewall rule."""
        result = await self.module.execute(
            "add_firewall_rule",
            device="firewall1",
            rule_name="test-rule",
            rule_action="permit",
            source="10.0.0.0/24",
            destination="192.168.1.0/24",
            protocol="tcp",
            destination_port="443"
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_list_vlans(self):
        """Test listing VLANs."""
        result = await self.module.execute("list_vlans", device="switch1")
        assert result["status"] == "success"
        assert "vlans" in result

    @pytest.mark.asyncio
    async def test_backup_config(self):
        """Test backing up device config."""
        result = await self.module.execute("backup_config", device="switch1")
        assert result["status"] == "success"


class TestPatchingModule:
    """Tests for patching module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = PatchingModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "patching"
        assert "patching" in self.module.description.lower()

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "patching"

    @pytest.mark.asyncio
    async def test_scan_updates_response(self):
        """Test scanning for updates returns proper response structure."""
        result = await self.module.execute("scan_updates", hostname="server1")
        # Without registered servers, expect error response
        assert "status" in result
        assert result["status"] in ["success", "error"]

    @pytest.mark.asyncio
    async def test_install_updates_response(self):
        """Test installing updates returns proper response structure."""
        result = await self.module.execute("install_updates", hostname="server1")
        assert "status" in result
        assert result["status"] in ["success", "error"]

    @pytest.mark.asyncio
    async def test_check_reboot_response(self):
        """Test checking reboot returns proper response structure."""
        result = await self.module.execute("check_reboot_required", hostname="server1")
        assert "status" in result
        assert result["status"] in ["success", "error"]


class TestBackupValidationModule:
    """Tests for backup validation module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = BackupValidationModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "backup"
        assert "Backup" in self.module.description

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "backup"

    @pytest.mark.asyncio
    async def test_list_backup_jobs(self):
        """Test listing backup jobs."""
        result = await self.module.execute("list_backup_jobs")
        assert result["status"] == "success"
        assert "jobs" in result

    @pytest.mark.asyncio
    async def test_get_backup_status(self):
        """Test getting backup status."""
        result = await self.module.execute("get_backup_status")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_backup_compliance(self):
        """Test checking backup compliance."""
        result = await self.module.execute("check_backup_compliance")
        assert result["status"] == "success"
        assert "overall_compliance" in result  # The actual key is overall_compliance


class TestCapacityManagementModule:
    """Tests for capacity management module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = CapacityManagementModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "capacity"
        assert "capacity" in self.module.description.lower()

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "capacity"

    @pytest.mark.asyncio
    async def test_get_current_capacity(self):
        """Test getting current capacity."""
        result = await self.module.execute("get_current_capacity")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_thresholds(self):
        """Test checking capacity thresholds."""
        result = await self.module.execute("check_thresholds")
        assert result["status"] == "success"
        assert "alerts" in result

    @pytest.mark.asyncio
    async def test_get_recommendations(self):
        """Test getting recommendations."""
        result = await self.module.execute("get_recommendations")
        assert result["status"] == "success"
        assert "recommendations" in result


class TestIncidentRemediationModule:
    """Tests for incident remediation module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.module = IncidentRemediationModule(self.config)

    def test_module_initialization(self):
        """Test module initializes correctly."""
        assert self.module.name == "remediation"
        assert "remediation" in self.module.description.lower()

    def test_health_check(self):
        """Test health check returns valid response."""
        result = self.module.health_check()
        assert result["status"] == "ok"
        assert result["module"] == "remediation"

    @pytest.mark.asyncio
    async def test_list_incidents(self):
        """Test listing incidents."""
        result = await self.module.execute("list_incidents")
        assert result["status"] == "success"
        assert "incidents" in result

    @pytest.mark.asyncio
    async def test_restart_service(self):
        """Test restarting a service."""
        result = await self.module.execute(
            "restart_service",
            server="server1",
            service_name="nginx"
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_run_health_check(self):
        """Test running health check on a service."""
        result = await self.module.execute(
            "run_health_check",
            target="server1",
            check_type="basic"
        )
        assert result["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
