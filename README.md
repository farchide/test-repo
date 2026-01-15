# On-Premises Automation Platform

A comprehensive enterprise-grade Python framework for automating on-premises infrastructure operations. Comparable to Ansible Tower, Rundeck, and StackStorm.

## Key Features

### Core Automation Modules
- **VMware VM Provisioning** - Automated VM creation, cloning, snapshots, lifecycle management
- **Network Automation** - VLAN management, firewall rules, multi-vendor support (Cisco, Juniper, Palo Alto, Fortinet)
- **Automated Patching** - Windows/Linux patching, maintenance windows, rollback capability
- **Backup Validation** - Automated recovery testing, compliance reporting, multi-vendor support
- **Capacity Management** - Real-time monitoring, forecasting, rightsizing recommendations
- **Incident Remediation** - Auto-remediation, service failover, runbook execution

### Enterprise Platform Features

| Feature | Description |
|---------|-------------|
| **REST API** | FastAPI-based API with OpenAPI/Swagger documentation |
| **Database Layer** | SQLAlchemy ORM with PostgreSQL/SQLite support |
| **Workflow Engine** | YAML-based DSL with parallel execution, conditions, loops |
| **Plugin System** | Hot-loadable plugins with dependency resolution |
| **Event Bus** | Pub/sub messaging with async processing |
| **Secret Management** | HashiCorp Vault, AWS Secrets Manager, Azure Key Vault |
| **Job Scheduling** | Cron, interval, and one-time job scheduling |
| **ChatOps** | Slack, Microsoft Teams, Discord integrations |
| **ITSM Integration** | ServiceNow, Jira, PagerDuty connectors |
| **Metrics & Monitoring** | Prometheus-compatible metrics export |

## Architecture

```
onprem_automation/
├── core/                    # Core engine, config, logging
├── modules/                 # Automation modules (VMware, Network, etc.)
├── connectors/              # Infrastructure connectors
│   ├── vmware_connector.py
│   ├── network_connector.py
│   ├── server_connector.py
│   └── backup_connectors.py
├── integrations/            # ITSM integrations
│   ├── servicenow.py
│   ├── jira.py
│   └── pagerduty.py
├── api/                     # REST API (FastAPI)
│   ├── main.py
│   └── auth.py
├── database/                # SQLAlchemy models
│   ├── models.py
│   └── session.py
├── workflows/               # Workflow engine
│   ├── dsl.py
│   └── engine.py
├── plugins/                 # Plugin system
│   ├── base.py
│   └── manager.py
├── events/                  # Event bus
│   ├── bus.py
│   ├── types.py
│   └── handlers.py
├── secrets/                 # Secret management
│   ├── manager.py
│   └── providers.py
├── scheduler/               # Job scheduling
│   ├── scheduler.py
│   └── job.py
├── chatops/                 # Chat integrations
│   ├── slack.py
│   ├── teams.py
│   └── discord_bot.py
├── metrics/                 # Prometheus metrics
└── cli.py                   # Command-line interface
```

## Installation

```bash
# Clone the repository
git clone https://github.com/example/onprem-automation.git
cd onprem-automation

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Basic installation
pip install -e .

# Full installation with all optional dependencies
pip install -e ".[full,api,dev]"
```

### Optional Dependencies

```bash
# For REST API
pip install fastapi uvicorn python-jose

# For database
pip install sqlalchemy psycopg2-binary

# For ChatOps
pip install slack-sdk botbuilder-core discord.py

# For secret management
pip install hvac boto3 azure-keyvault-secrets
```

## Quick Start

### CLI Usage

```bash
# List available modules
onprem-auto list

# Run health checks
onprem-auto health

# VMware operations
onprem-auto vmware provision my-vm -t rhel8-template --cpus 4 --memory 8
onprem-auto vmware list --templates

# Network operations
onprem-auto network vlan switch01 100 -n "Production"
onprem-auto network firewall fw-01 -n "Allow-HTTPS" -a permit -p tcp --port 443

# Patching
onprem-auto patch scan server01.example.com
onprem-auto patch install server01.example.com

# Backup validation
onprem-auto backup status -j "Production-VMs-Daily"
onprem-auto backup test my-vm -t application_test

# Capacity management
onprem-auto capacity status -t storage
onprem-auto capacity forecast "Datastore-01" --days 90

# Incident remediation
onprem-auto remediate restart server01 httpd
onprem-auto remediate failover web-service --primary srv01 --secondary srv02
```

### REST API

```bash
# Start the API server
uvicorn onprem_automation.api.main:app --host 0.0.0.0 --port 8000

# API endpoints available at http://localhost:8000/docs
```

**Example API calls:**

```bash
# Get auth token
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# List jobs
curl -X GET "http://localhost:8000/api/v1/jobs" \
  -H "Authorization: Bearer <token>"

# Execute a job
curl -X POST "http://localhost:8000/api/v1/jobs/job-id/execute" \
  -H "Authorization: Bearer <token>"

# Get workflow status
curl -X GET "http://localhost:8000/api/v1/workflows/workflow-id" \
  -H "Authorization: Bearer <token>"
```

### Python API

```python
import asyncio
from onprem_automation.core import Config
from onprem_automation.core.engine import AutomationEngine
from onprem_automation.modules import VMwareProvisioningModule, NetworkAutomationModule

async def main():
    config = Config("config.yaml")
    engine = AutomationEngine(config)

    engine.register_module(VMwareProvisioningModule)
    engine.register_module(NetworkAutomationModule)

    # Provision a VM
    result = await engine.run_action(
        "vmware", "provision_vm",
        name="app-server",
        template="rhel8-template",
        num_cpus=4, memory_gb=8
    )
    print(result)

asyncio.run(main())
```

## Workflow Engine

Create workflows using YAML DSL:

```yaml
name: deploy-application
version: "1.0"
description: Deploy application to production

inputs:
  - name: app_name
    type: string
    required: true
  - name: environment
    type: string
    default: production

steps:
  - name: provision-vm
    type: action
    module: vmware
    action: provision_vm
    params:
      name: "{{ inputs.app_name }}-server"
      template: rhel8-template
      num_cpus: 4

  - name: configure-network
    type: action
    module: network
    action: configure_interface
    params:
      device: switch01
      vlan: 100
    depends_on: [provision-vm]

  - name: approval-gate
    type: approval
    approvers: [ops-team]
    timeout: 3600
    depends_on: [configure-network]

  - name: deploy-parallel
    type: parallel
    depends_on: [approval-gate]
    steps:
      - name: install-packages
        type: action
        module: patching
        action: install_updates
      - name: configure-backup
        type: action
        module: backup
        action: create_backup_job

outputs:
  - name: server_ip
    value: "{{ steps.provision-vm.result.ip_address }}"
```

Execute workflows:

```python
from onprem_automation.workflows import WorkflowEngine, WorkflowDSL

# Load and execute workflow
workflow = WorkflowDSL.parse("deploy.yaml")
engine = WorkflowEngine()
result = await engine.execute(workflow, inputs={"app_name": "myapp"})
```

## Plugin System

Create custom plugins:

```python
from onprem_automation.plugins import PluginBase, PluginMetadata, PluginType

class MyCustomPlugin(PluginBase):
    metadata = PluginMetadata(
        name="my-plugin",
        version="1.0.0",
        description="Custom automation plugin",
        plugin_type=PluginType.MODULE
    )

    def initialize(self, config):
        self.config = config
        return True

    async def execute(self, action, **params):
        if action == "custom_action":
            return await self.custom_action(**params)

    async def custom_action(self, **params):
        # Implementation
        return {"status": "success"}
```

Load plugins:

```python
from onprem_automation.plugins import get_plugin_manager

manager = get_plugin_manager()
manager.add_plugin_directory("/path/to/plugins")
manager.load_all()

# Get and use plugin
plugin = manager.get_plugin("my-plugin")
result = await plugin.instance.execute("custom_action", param1="value")
```

## Event-Driven Architecture

Subscribe to events:

```python
from onprem_automation.events import get_event_bus, Event, EventType, event_handler

bus = get_event_bus()

@event_handler(EventType.JOB_COMPLETED, EventType.JOB_FAILED)
async def on_job_finish(event: Event):
    print(f"Job {event.data['job_id']} finished: {event.event_type}")

bus.subscribe("my-handler", on_job_finish)
await bus.start()

# Publish events
await bus.publish(Event(
    event_type=EventType.JOB_COMPLETED,
    source="job_executor",
    data={"job_id": "123", "status": "success"}
))
```

## Secret Management

```python
from onprem_automation.secrets import get_secret_manager, VaultProvider

manager = get_secret_manager()

# Add HashiCorp Vault provider
manager.add_provider("vault", VaultProvider(
    url="https://vault.example.com",
    token="my-token"
))

await manager.connect_all()

# Get secrets
db_password = await manager.get_secret("vault://database/credentials#password")

# Resolve secrets in config
config = await manager.resolve_secrets({
    "database": {
        "password": "${vault://database/credentials#password}"
    }
})
```

## Job Scheduling

```python
from onprem_automation.scheduler import get_scheduler, ScheduledJob, CronTrigger

scheduler = get_scheduler()

# Register job handlers
scheduler.register_handler("backup", "run_backup", backup_handler)

# Schedule jobs
scheduler.add_job(ScheduledJob(
    name="nightly-backup",
    trigger=CronTrigger("0 2 * * *"),  # 2 AM daily
    action="run_backup",
    module="backup",
    params={"target": "all"}
))

await scheduler.start()
```

## ChatOps Integration

### Slack

```python
from onprem_automation.chatops import SlackBot, SlackConfig

config = SlackConfig(
    bot_token="xoxb-...",
    app_token="xapp-...",
    notification_channel="#ops"
)

bot = SlackBot(config)

@bot.handler.command("deploy", permission=PermissionLevel.OPERATOR)
async def deploy_cmd(ctx):
    env = ctx.args[0] if ctx.args else "staging"
    return f"Deploying to {env}..."

await bot.connect()
```

### Microsoft Teams

```python
from onprem_automation.chatops import TeamsBot, TeamsConfig

config = TeamsConfig(
    app_id="...",
    app_password="...",
    tenant_id="..."
)

bot = TeamsBot(config)
await bot.start_server(port=3978)
```

## ITSM Integrations

### ServiceNow

```python
from onprem_automation.integrations import ServiceNowConfig, ServiceNowClient

config = ServiceNowConfig(
    instance="company.service-now.com",
    username="integration_user",
    password="password"
)

client = ServiceNowClient(config)

# Create incident
incident = await client.create_incident(
    short_description="Server disk full",
    description="Production server /var partition at 95%",
    urgency=2,
    impact=2
)
```

### PagerDuty

```python
from onprem_automation.integrations import PagerDutyConfig, PagerDutyClient

config = PagerDutyConfig(
    api_key="your-api-key",
    integration_key="your-integration-key"
)

client = PagerDutyClient(config)

# Trigger alert
await client.trigger_event(
    summary="High CPU usage on prod-web-01",
    severity="warning",
    source="monitoring"
)
```

## Configuration

```yaml
# config.yaml
vmware:
  host: "vcenter.example.com"
  username: "automation@vsphere.local"
  datacenter: "DC01"
  cluster: "Production"

network:
  devices:
    core-switch:
      host: "10.0.0.1"
      device_type: "cisco_ios"

patching:
  wsus_server: "wsus.example.com"
  maintenance_window:
    start: "02:00"
    duration_hours: 4

backup:
  provider: "veeam"
  server: "veeam.example.com"

capacity:
  thresholds:
    storage_warning: 75
    storage_critical: 90

# Secrets via environment variables
# VMWARE_PASSWORD, SERVICENOW_PASSWORD, etc.
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=onprem_automation

# Run specific test file
pytest tests/test_modules.py -v
```

## Module Actions Reference

### VMware Module
| Action | Description |
|--------|-------------|
| `provision_vm` | Create VM from template |
| `clone_vm` | Clone existing VM |
| `delete_vm` | Delete a VM |
| `power_on/off` | Power operations |
| `snapshot` | Create snapshot |
| `list_templates` | List templates |

### Network Module
| Action | Description |
|--------|-------------|
| `create_vlan` | Create VLAN |
| `add_firewall_rule` | Add firewall rule |
| `configure_interface` | Configure interface |
| `backup_config` | Backup device config |

### Patching Module
| Action | Description |
|--------|-------------|
| `scan_updates` | Scan for updates |
| `install_updates` | Install updates |
| `patch_server` | Full patching workflow |
| `rollback_patch` | Rollback patch |

### Backup Module
| Action | Description |
|--------|-------------|
| `list_backup_jobs` | List backup jobs |
| `validate_backup` | Validate integrity |
| `run_recovery_test` | Test recovery |
| `check_compliance` | Check compliance |

### Capacity Module
| Action | Description |
|--------|-------------|
| `get_current_capacity` | Get utilization |
| `forecast_capacity` | Forecast usage |
| `get_recommendations` | Get recommendations |

### Remediation Module
| Action | Description |
|--------|-------------|
| `restart_service` | Restart service |
| `failover_service` | Failover to standby |
| `execute_runbook` | Run automation |
| `create_incident` | Create incident |

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the detailed enhancement roadmap including:
- AI-powered recommendations
- Multi-tenancy support
- High availability clustering
- Enhanced security features
- Terraform/Ansible integration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Run tests: `pytest`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
