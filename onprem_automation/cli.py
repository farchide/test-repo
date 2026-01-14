#!/usr/bin/env python3
"""
On-Premises Automation CLI
Command-line interface for the automation system.
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

from .core.engine import AutomationEngine
from .core.config import Config
from .core.logger import get_logger
from .modules import (
    VMwareProvisioningModule,
    NetworkAutomationModule,
    PatchingModule,
    BackupValidationModule,
    CapacityManagementModule,
    IncidentRemediationModule,
)


def create_engine(config_path: Optional[str] = None) -> AutomationEngine:
    """Create and configure the automation engine."""
    config = Config(config_path)
    engine = AutomationEngine(config)

    # Register all modules
    engine.register_module(VMwareProvisioningModule)
    engine.register_module(NetworkAutomationModule)
    engine.register_module(PatchingModule)
    engine.register_module(BackupValidationModule)
    engine.register_module(CapacityManagementModule)
    engine.register_module(IncidentRemediationModule)

    return engine


def format_output(data: dict, format_type: str = "json") -> str:
    """Format output for display."""
    if format_type == "json":
        return json.dumps(data, indent=2, default=str)
    elif format_type == "table":
        # Simple table format
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"  - {item}")
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    return str(data)


async def run_action(
    engine: AutomationEngine,
    module: str,
    action: str,
    params: dict,
    output_format: str = "json"
) -> int:
    """Run an automation action and display results."""
    try:
        result = await engine.run_action(module, action, **params)
        print(format_output(result, output_format))
        return 0 if result.get("status") == "success" else 1
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=2))
        return 1


def parse_params(param_list: list) -> dict:
    """Parse command-line parameters into a dictionary."""
    params = {}
    if not param_list:
        return params

    for param in param_list:
        if "=" in param:
            key, value = param.split("=", 1)
            # Try to parse as JSON for complex values
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                # Handle boolean strings
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                # Handle numeric strings
                elif value.isdigit():
                    value = int(value)
            params[key] = value
    return params


def cmd_list_modules(engine: AutomationEngine, args):
    """List all available modules."""
    modules = engine.list_modules()
    print("\nAvailable Modules:")
    print("-" * 50)
    for module in modules:
        print(f"  {module['name']:<20} - {module['description']}")
    print()
    return 0


def cmd_health_check(engine: AutomationEngine, args):
    """Run health checks on all modules."""
    results = engine.health_check_all()
    print(format_output(results, args.format))
    return 0


async def cmd_run(engine: AutomationEngine, args):
    """Run a specific action on a module."""
    params = parse_params(args.params)
    return await run_action(engine, args.module, args.action, params, args.format)


async def cmd_workflow(engine: AutomationEngine, args):
    """Run a workflow from a file."""
    with open(args.workflow_file, 'r') as f:
        workflow = json.load(f)

    results = await engine.run_workflow(workflow, user=args.user or "cli")
    print(format_output({"results": results}, args.format))
    return 0 if all(r["result"].get("status") == "success" for r in results) else 1


# VMware subcommands
async def cmd_vmware_provision(engine: AutomationEngine, args):
    """Provision a new VM."""
    params = {
        "name": args.name,
        "template": args.template,
        "num_cpus": args.cpus,
        "memory_gb": args.memory,
        "network": args.network,
        "datastore": args.datastore,
        "power_on": not args.no_power_on
    }
    return await run_action(engine, "vmware", "provision_vm", params, args.format)


async def cmd_vmware_list(engine: AutomationEngine, args):
    """List VMs or templates."""
    if args.templates:
        return await run_action(engine, "vmware", "list_templates", {}, args.format)
    return await run_action(engine, "vmware", "list_vms", {}, args.format)


# Network subcommands
async def cmd_network_vlan(engine: AutomationEngine, args):
    """Manage VLANs."""
    if args.delete:
        params = {"device": args.device, "vlan_id": args.vlan_id}
        return await run_action(engine, "network", "delete_vlan", params, args.format)
    else:
        params = {
            "device": args.device,
            "vlan_id": args.vlan_id,
            "name": args.name,
            "description": args.description or "",
            "ip_address": args.ip,
            "subnet_mask": args.mask
        }
        return await run_action(engine, "network", "create_vlan", params, args.format)


async def cmd_network_firewall(engine: AutomationEngine, args):
    """Manage firewall rules."""
    params = {
        "device": args.device,
        "rule_name": args.name,
        "action": args.rule_action,
        "source": args.source,
        "destination": args.destination,
        "protocol": args.protocol,
        "destination_port": args.port
    }
    return await run_action(engine, "network", "add_firewall_rule", params, args.format)


# Patching subcommands
async def cmd_patch_scan(engine: AutomationEngine, args):
    """Scan for available updates."""
    params = {"hostname": args.hostname}
    return await run_action(engine, "patching", "scan_updates", params, args.format)


async def cmd_patch_install(engine: AutomationEngine, args):
    """Install updates."""
    params = {
        "hostname": args.hostname,
        "reboot": not args.no_reboot
    }
    return await run_action(engine, "patching", "install_updates", params, args.format)


async def cmd_patch_server(engine: AutomationEngine, args):
    """Full patching workflow for a server."""
    params = {"hostname": args.hostname}
    return await run_action(engine, "patching", "patch_server", params, args.format)


# Backup subcommands
async def cmd_backup_status(engine: AutomationEngine, args):
    """Get backup status."""
    params = {"job_name": args.job, "days": args.days}
    return await run_action(engine, "backup", "get_backup_status", params, args.format)


async def cmd_backup_test(engine: AutomationEngine, args):
    """Run recovery test."""
    params = {
        "vm_name": args.vm,
        "test_type": args.test_type,
        "auto_cleanup": not args.no_cleanup
    }
    return await run_action(engine, "backup", "run_recovery_test", params, args.format)


async def cmd_backup_compliance(engine: AutomationEngine, args):
    """Check backup compliance."""
    return await run_action(engine, "backup", "check_backup_compliance", {}, args.format)


# Capacity subcommands
async def cmd_capacity_status(engine: AutomationEngine, args):
    """Get current capacity status."""
    params = {"resource_type": args.type}
    return await run_action(engine, "capacity", "get_current_capacity", params, args.format)


async def cmd_capacity_forecast(engine: AutomationEngine, args):
    """Forecast capacity."""
    params = {
        "resource_name": args.resource,
        "forecast_days": args.days
    }
    return await run_action(engine, "capacity", "forecast_capacity", params, args.format)


async def cmd_capacity_report(engine: AutomationEngine, args):
    """Generate capacity report."""
    params = {"report_type": args.type, "include_forecast": True}
    return await run_action(engine, "capacity", "generate_capacity_report", params, args.format)


# Remediation subcommands
async def cmd_remediation_restart(engine: AutomationEngine, args):
    """Restart a service."""
    params = {
        "server": args.server,
        "service_name": args.service
    }
    return await run_action(engine, "remediation", "restart_service", params, args.format)


async def cmd_remediation_failover(engine: AutomationEngine, args):
    """Failover a service."""
    params = {
        "service_name": args.service,
        "primary": args.primary,
        "secondary": args.secondary
    }
    return await run_action(engine, "remediation", "failover_service", params, args.format)


async def cmd_remediation_incidents(engine: AutomationEngine, args):
    """List incidents."""
    params = {"status": args.status, "severity": args.severity}
    return await run_action(engine, "remediation", "list_incidents", params, args.format)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="onprem-auto",
        description="On-Premises Infrastructure Automation CLI"
    )

    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List modules command
    list_parser = subparsers.add_parser("list", help="List available modules")
    list_parser.set_defaults(func=cmd_list_modules)

    # Health check command
    health_parser = subparsers.add_parser("health", help="Run health checks")
    health_parser.set_defaults(func=cmd_health_check)

    # Generic run command
    run_parser = subparsers.add_parser("run", help="Run a specific action")
    run_parser.add_argument("module", help="Module name")
    run_parser.add_argument("action", help="Action to execute")
    run_parser.add_argument("params", nargs="*", help="Parameters as key=value pairs")
    run_parser.set_defaults(func=cmd_run, is_async=True)

    # Workflow command
    workflow_parser = subparsers.add_parser("workflow", help="Run a workflow")
    workflow_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    workflow_parser.add_argument("-u", "--user", help="User executing the workflow")
    workflow_parser.set_defaults(func=cmd_workflow, is_async=True)

    # VMware commands
    vmware_parser = subparsers.add_parser("vmware", help="VMware operations")
    vmware_sub = vmware_parser.add_subparsers(dest="vmware_command")

    # vmware provision
    vm_provision = vmware_sub.add_parser("provision", help="Provision a new VM")
    vm_provision.add_argument("name", help="VM name")
    vm_provision.add_argument("-t", "--template", required=True, help="Template name")
    vm_provision.add_argument("--cpus", type=int, default=2, help="Number of vCPUs")
    vm_provision.add_argument("--memory", type=int, default=4, help="Memory in GB")
    vm_provision.add_argument("--network", default="VM Network", help="Network name")
    vm_provision.add_argument("--datastore", help="Datastore name")
    vm_provision.add_argument("--no-power-on", action="store_true", help="Don't power on after creation")
    vm_provision.set_defaults(func=cmd_vmware_provision, is_async=True)

    # vmware list
    vm_list = vmware_sub.add_parser("list", help="List VMs or templates")
    vm_list.add_argument("--templates", action="store_true", help="List templates instead of VMs")
    vm_list.set_defaults(func=cmd_vmware_list, is_async=True)

    # Network commands
    network_parser = subparsers.add_parser("network", help="Network operations")
    network_sub = network_parser.add_subparsers(dest="network_command")

    # network vlan
    net_vlan = network_sub.add_parser("vlan", help="Manage VLANs")
    net_vlan.add_argument("device", help="Switch hostname")
    net_vlan.add_argument("vlan_id", type=int, help="VLAN ID")
    net_vlan.add_argument("-n", "--name", help="VLAN name")
    net_vlan.add_argument("-d", "--description", help="VLAN description")
    net_vlan.add_argument("--ip", help="SVI IP address")
    net_vlan.add_argument("--mask", help="Subnet mask")
    net_vlan.add_argument("--delete", action="store_true", help="Delete VLAN")
    net_vlan.set_defaults(func=cmd_network_vlan, is_async=True)

    # network firewall
    net_fw = network_sub.add_parser("firewall", help="Manage firewall rules")
    net_fw.add_argument("device", help="Firewall hostname")
    net_fw.add_argument("-n", "--name", required=True, help="Rule name")
    net_fw.add_argument("-a", "--rule-action", choices=["permit", "deny"], required=True)
    net_fw.add_argument("-s", "--source", required=True, help="Source IP/network")
    net_fw.add_argument("-d", "--destination", required=True, help="Destination IP/network")
    net_fw.add_argument("-p", "--protocol", default="tcp", help="Protocol")
    net_fw.add_argument("--port", help="Destination port")
    net_fw.set_defaults(func=cmd_network_firewall, is_async=True)

    # Patching commands
    patch_parser = subparsers.add_parser("patch", help="Patching operations")
    patch_sub = patch_parser.add_subparsers(dest="patch_command")

    # patch scan
    patch_scan = patch_sub.add_parser("scan", help="Scan for updates")
    patch_scan.add_argument("hostname", help="Server hostname")
    patch_scan.set_defaults(func=cmd_patch_scan, is_async=True)

    # patch install
    patch_install = patch_sub.add_parser("install", help="Install updates")
    patch_install.add_argument("hostname", help="Server hostname")
    patch_install.add_argument("--no-reboot", action="store_true", help="Don't reboot after patching")
    patch_install.set_defaults(func=cmd_patch_install, is_async=True)

    # patch server
    patch_server = patch_sub.add_parser("server", help="Full patching workflow")
    patch_server.add_argument("hostname", help="Server hostname")
    patch_server.set_defaults(func=cmd_patch_server, is_async=True)

    # Backup commands
    backup_parser = subparsers.add_parser("backup", help="Backup operations")
    backup_sub = backup_parser.add_subparsers(dest="backup_command")

    # backup status
    backup_status = backup_sub.add_parser("status", help="Get backup status")
    backup_status.add_argument("-j", "--job", help="Job name")
    backup_status.add_argument("--days", type=int, default=7, help="Number of days")
    backup_status.set_defaults(func=cmd_backup_status, is_async=True)

    # backup test
    backup_test = backup_sub.add_parser("test", help="Run recovery test")
    backup_test.add_argument("vm", help="VM name")
    backup_test.add_argument("-t", "--test-type", default="boot_test",
                             choices=["boot_test", "application_test", "full_test"])
    backup_test.add_argument("--no-cleanup", action="store_true", help="Don't cleanup test VM")
    backup_test.set_defaults(func=cmd_backup_test, is_async=True)

    # backup compliance
    backup_compliance = backup_sub.add_parser("compliance", help="Check backup compliance")
    backup_compliance.set_defaults(func=cmd_backup_compliance, is_async=True)

    # Capacity commands
    capacity_parser = subparsers.add_parser("capacity", help="Capacity management")
    capacity_sub = capacity_parser.add_subparsers(dest="capacity_command")

    # capacity status
    cap_status = capacity_sub.add_parser("status", help="Get capacity status")
    cap_status.add_argument("-t", "--type", choices=["storage", "compute", "memory"],
                            help="Resource type filter")
    cap_status.set_defaults(func=cmd_capacity_status, is_async=True)

    # capacity forecast
    cap_forecast = capacity_sub.add_parser("forecast", help="Forecast capacity")
    cap_forecast.add_argument("resource", help="Resource name")
    cap_forecast.add_argument("--days", type=int, default=90, help="Forecast days")
    cap_forecast.set_defaults(func=cmd_capacity_forecast, is_async=True)

    # capacity report
    cap_report = capacity_sub.add_parser("report", help="Generate capacity report")
    cap_report.add_argument("-t", "--type", default="summary",
                            choices=["summary", "detailed"])
    cap_report.set_defaults(func=cmd_capacity_report, is_async=True)

    # Remediation commands
    remed_parser = subparsers.add_parser("remediate", help="Incident remediation")
    remed_sub = remed_parser.add_subparsers(dest="remed_command")

    # remediate restart
    remed_restart = remed_sub.add_parser("restart", help="Restart a service")
    remed_restart.add_argument("server", help="Server hostname")
    remed_restart.add_argument("service", help="Service name")
    remed_restart.set_defaults(func=cmd_remediation_restart, is_async=True)

    # remediate failover
    remed_failover = remed_sub.add_parser("failover", help="Failover a service")
    remed_failover.add_argument("service", help="Service name")
    remed_failover.add_argument("--primary", required=True, help="Primary server")
    remed_failover.add_argument("--secondary", required=True, help="Secondary server")
    remed_failover.set_defaults(func=cmd_remediation_failover, is_async=True)

    # remediate incidents
    remed_incidents = remed_sub.add_parser("incidents", help="List incidents")
    remed_incidents.add_argument("--status", help="Filter by status")
    remed_incidents.add_argument("--severity", help="Filter by severity")
    remed_incidents.set_defaults(func=cmd_remediation_incidents, is_async=True)

    return parser


def main():
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create engine
    engine = create_engine(args.config)

    # Run command
    if hasattr(args, 'func'):
        if getattr(args, 'is_async', False):
            return asyncio.run(args.func(engine, args))
        else:
            return args.func(engine, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
