# On-Premises Automation System

A comprehensive Python framework for automating on-premises infrastructure operations including VM provisioning, network configuration, patching, backup validation, capacity management, and incident remediation.

## Features

### 1. VMware VM Provisioning
- Automated VM creation from templates
- VM cloning and lifecycle management
- Snapshot management
- Hardware reconfiguration (CPU, memory, disk)
- PowerCLI integration for bulk operations

### 2. Network Automation
- VLAN creation and management
- Firewall rule configuration
- Interface configuration
- Static routing
- Configuration backup and restore
- Multi-vendor support (Cisco, Juniper, Palo Alto, Fortinet)

### 3. Automated Patching
- Windows patching via WSUS/Windows Update
- Linux patching (RHEL, CentOS, Ubuntu, SUSE)
- Network device firmware updates
- Maintenance window scheduling
- Pre-patch snapshots and rollback capability

### 4. Backup Validation
- Automated recovery testing (SureBackup-style)
- Instant VM recovery validation
- File-level recovery testing
- Backup chain verification
- Compliance reporting
- Multi-vendor support (Veeam, Commvault, NetBackup)

### 5. Capacity Management
- Real-time capacity monitoring
- Storage and compute forecasting
- Threshold alerting
- VM rightsizing recommendations
- Orphaned resource identification
- Capacity reports and trends

### 6. Incident Remediation
- Automated service restarts
- VM restart and recovery
- Service failover
- Traffic rerouting
- Runbook execution
- Incident tracking and escalation

## Installation

```bash
# Clone the repository
git clone https://github.com/example/onprem-automation.git
cd onprem-automation

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .

# For full installation with all optional dependencies
pip install -e ".[full,api,dev]"
```

## Configuration

1. Copy the example configuration:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your environment settings:
```yaml
vmware:
  host: "vcenter.example.com"
  username: "automation@vsphere.local"
  datacenter: "DC01"
  cluster: "Production-Cluster"
```

3. Set sensitive credentials via environment variables:
```bash
export VMWARE_PASSWORD="your-password"
export NETWORK_PASSWORD="your-password"
```

## Usage

### CLI Usage

```bash
# List available modules
onprem-auto list

# Run health checks
onprem-auto health

# VMware operations
onprem-auto vmware provision my-new-vm -t rhel8-template --cpus 4 --memory 8
onprem-auto vmware list --templates

# Network operations
onprem-auto network vlan core-sw-01 100 -n "Production" -d "Production VLAN"
onprem-auto network firewall fw-01 -n "Allow-Web" -a permit -s 10.0.0.0/8 -d any -p tcp --port 443

# Patching
onprem-auto patch scan server01.example.com
onprem-auto patch install server01.example.com
onprem-auto patch server server01.example.com  # Full workflow

# Backup validation
onprem-auto backup status -j "Production-VMs-Daily"
onprem-auto backup test my-critical-vm -t application_test
onprem-auto backup compliance

# Capacity management
onprem-auto capacity status -t storage
onprem-auto capacity forecast "Production-Datastore-01" --days 90
onprem-auto capacity report -t detailed

# Incident remediation
onprem-auto remediate restart server01.example.com httpd
onprem-auto remediate failover web-service --primary server01 --secondary server02
onprem-auto remediate incidents --status open
```

### Generic Action Execution

```bash
# Run any module action with parameters
onprem-auto run vmware provision_vm name=test-vm template=rhel8-template num_cpus=4
onprem-auto run network create_vlan device=switch01 vlan_id=200 name=Development
onprem-auto run capacity get_recommendations
```

### Workflow Execution

Create a workflow file (workflow.json):
```json
[
  {
    "module": "vmware",
    "action": "provision_vm",
    "params": {
      "name": "app-server-01",
      "template": "rhel8-template",
      "num_cpus": 4,
      "memory_gb": 8
    }
  },
  {
    "module": "network",
    "action": "configure_interface",
    "params": {
      "device": "switch01",
      "interface": "Gi1/0/24",
      "vlan": 100
    }
  },
  {
    "module": "patching",
    "action": "patch_server",
    "params": {
      "hostname": "app-server-01"
    }
  }
]
```

Run the workflow:
```bash
onprem-auto workflow workflow.json
```

### Python API Usage

```python
import asyncio
from onprem_automation import AutomationEngine, Config
from onprem_automation.modules import (
    VMwareProvisioningModule,
    NetworkAutomationModule,
    PatchingModule,
)

async def main():
    # Initialize engine
    config = Config("config.yaml")
    engine = AutomationEngine(config)

    # Register modules
    engine.register_module(VMwareProvisioningModule)
    engine.register_module(NetworkAutomationModule)
    engine.register_module(PatchingModule)

    # Provision a VM
    result = await engine.run_action(
        module_name="vmware",
        action="provision_vm",
        name="new-server",
        template="rhel8-template",
        num_cpus=4,
        memory_gb=8
    )
    print(result)

    # Create a VLAN
    result = await engine.run_action(
        module_name="network",
        action="create_vlan",
        device="core-switch-01",
        vlan_id=150,
        name="Application"
    )
    print(result)

    # Run capacity forecast
    result = await engine.run_action(
        module_name="capacity",
        action="forecast_capacity",
        resource_name="Production-Datastore-01",
        forecast_days=90
    )
    print(result)

asyncio.run(main())
```

## Architecture

```
onprem_automation/
├── __init__.py
├── cli.py                    # Command-line interface
├── core/
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── engine.py            # Core automation engine
│   └── logger.py            # Logging utilities
└── modules/
    ├── __init__.py
    ├── vmware_provisioning.py    # VMware automation
    ├── network_automation.py     # Network device automation
    ├── patching.py               # Server patching
    ├── backup_validation.py      # Backup testing
    ├── capacity_management.py    # Capacity forecasting
    └── incident_remediation.py   # Incident response
```

## Module Actions Reference

### VMware Module (`vmware`)
| Action | Description |
|--------|-------------|
| `provision_vm` | Create VM from template |
| `clone_vm` | Clone existing VM |
| `delete_vm` | Delete a VM |
| `power_on` | Power on VM |
| `power_off` | Power off VM |
| `snapshot` | Create snapshot |
| `reconfigure` | Modify VM hardware |
| `list_templates` | List available templates |
| `list_vms` | List virtual machines |

### Network Module (`network`)
| Action | Description |
|--------|-------------|
| `create_vlan` | Create VLAN |
| `delete_vlan` | Delete VLAN |
| `list_vlans` | List VLANs |
| `add_firewall_rule` | Add firewall rule |
| `remove_firewall_rule` | Remove firewall rule |
| `configure_interface` | Configure interface |
| `backup_config` | Backup device config |
| `restore_config` | Restore config |

### Patching Module (`patching`)
| Action | Description |
|--------|-------------|
| `scan_updates` | Scan for available updates |
| `install_updates` | Install updates |
| `patch_server` | Full patching workflow |
| `patch_group` | Patch server group |
| `reboot_server` | Reboot server |
| `rollback_patch` | Rollback patch |

### Backup Module (`backup`)
| Action | Description |
|--------|-------------|
| `list_backup_jobs` | List backup jobs |
| `get_backup_status` | Get backup status |
| `validate_backup` | Validate backup integrity |
| `run_recovery_test` | Run recovery test |
| `check_backup_compliance` | Check compliance |
| `generate_backup_report` | Generate report |

### Capacity Module (`capacity`)
| Action | Description |
|--------|-------------|
| `get_current_capacity` | Get current utilization |
| `get_capacity_trend` | Get historical trend |
| `forecast_capacity` | Forecast future usage |
| `check_thresholds` | Check against thresholds |
| `get_recommendations` | Get recommendations |
| `analyze_vm_rightsizing` | Find oversized VMs |

### Remediation Module (`remediation`)
| Action | Description |
|--------|-------------|
| `restart_service` | Restart a service |
| `restart_vm` | Restart VM |
| `failover_service` | Failover to standby |
| `reroute_traffic` | Reroute traffic |
| `scale_service` | Scale service up/down |
| `execute_runbook` | Execute runbook |
| `create_incident` | Create incident |
| `list_incidents` | List incidents |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
