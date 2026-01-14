"""Automation modules for on-premises infrastructure."""

from .vmware_provisioning import VMwareProvisioningModule
from .network_automation import NetworkAutomationModule
from .patching import PatchingModule
from .backup_validation import BackupValidationModule
from .capacity_management import CapacityManagementModule
from .incident_remediation import IncidentRemediationModule

__all__ = [
    "VMwareProvisioningModule",
    "NetworkAutomationModule",
    "PatchingModule",
    "BackupValidationModule",
    "CapacityManagementModule",
    "IncidentRemediationModule",
]
