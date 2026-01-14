"""
VMware vSphere Connector

Provides real connections to VMware vCenter/ESXi using pyVmomi.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import ssl
import atexit
import time

from .base import BaseConnector, ConnectionConfig, ConnectionError, AuthenticationError

# Import pyVmomi - will be available when pyvmomi is installed
try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
    PYVMOMI_AVAILABLE = True
except ImportError:
    PYVMOMI_AVAILABLE = False
    SmartConnect = None
    Disconnect = None
    vim = None
    vmodl = None


@dataclass
class VMwareConnectionConfig(ConnectionConfig):
    """VMware-specific connection configuration."""
    port: int = 443
    datacenter: str = ""
    cluster: str = ""
    verify_ssl: bool = False  # Often disabled for self-signed certs


class VMwareConnector(BaseConnector):
    """
    Real VMware vSphere connector using pyVmomi.

    Provides full vSphere API access for:
    - VM lifecycle management
    - Template operations
    - Snapshot management
    - Resource pool management
    - Datastore operations
    """

    def __init__(self, config: VMwareConnectionConfig, logger=None):
        super().__init__(config, logger)
        self.config: VMwareConnectionConfig = config
        self._service_instance = None
        self._content = None

    def connect(self) -> bool:
        """
        Establish connection to vCenter/ESXi.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If credentials are invalid
        """
        if not PYVMOMI_AVAILABLE:
            raise ConnectionError(
                "pyVmomi is not installed. Install with: pip install pyvmomi"
            )

        try:
            # Create SSL context
            if not self.config.verify_ssl:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                ssl_context = ssl.create_default_context()

            self.logger.info(f"Connecting to vCenter: {self.config.host}")

            # Connect to vCenter
            self._service_instance = SmartConnect(
                host=self.config.host,
                user=self.config.username,
                pwd=self.config.password,
                port=self.config.port,
                sslContext=ssl_context
            )

            if not self._service_instance:
                raise ConnectionError("Failed to connect to vCenter")

            # Register disconnect on exit
            atexit.register(Disconnect, self._service_instance)

            # Get content object for API calls
            self._content = self._service_instance.RetrieveContent()
            self._connected = True
            self._connection_time = time.time()

            self.logger.info(f"Successfully connected to vCenter: {self.config.host}")
            return True

        except vim.fault.InvalidLogin as e:
            raise AuthenticationError(f"Invalid credentials for vCenter: {e.msg}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to vCenter: {str(e)}")

    def disconnect(self) -> None:
        """Disconnect from vCenter."""
        if self._service_instance:
            try:
                Disconnect(self._service_instance)
                self.logger.info("Disconnected from vCenter")
            except Exception as e:
                self.logger.warning(f"Error during disconnect: {e}")
            finally:
                self._service_instance = None
                self._content = None
                self._connected = False

    def health_check(self) -> Dict[str, Any]:
        """Check vCenter connection health."""
        if not self._connected:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            # Simple API call to verify connection
            about = self._content.about
            latency = time.time() - start

            return {
                "status": "healthy",
                "host": self.config.host,
                "latency_ms": round(latency * 1000, 2),
                "vcenter_version": about.version,
                "vcenter_build": about.build,
                "api_version": about.apiVersion,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "host": self.config.host,
                "error": str(e)
            }

    # ==================== VM Operations ====================

    def get_vm_by_name(self, name: str) -> Optional[Any]:
        """
        Find a VM by name.

        Args:
            name: VM name to search for

        Returns:
            vim.VirtualMachine object or None
        """
        container = self._content.viewManager.CreateContainerView(
            self._content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm in container.view:
                if vm.name == name:
                    return vm
            return None
        finally:
            container.Destroy()

    def list_vms(self, folder: str = None) -> List[Dict[str, Any]]:
        """
        List all VMs in the environment.

        Args:
            folder: Optional folder path to filter

        Returns:
            List of VM information dictionaries
        """
        vms = []
        container = self._content.viewManager.CreateContainerView(
            self._content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm in container.view:
                vm_info = {
                    "name": vm.name,
                    "power_state": str(vm.runtime.powerState),
                    "num_cpu": vm.config.hardware.numCPU if vm.config else 0,
                    "memory_mb": vm.config.hardware.memoryMB if vm.config else 0,
                    "guest_os": vm.config.guestFullName if vm.config else "",
                    "ip_address": vm.guest.ipAddress if vm.guest else None,
                    "tools_status": str(vm.guest.toolsStatus) if vm.guest else None,
                    "uuid": vm.config.uuid if vm.config else None,
                }
                vms.append(vm_info)
            return vms
        finally:
            container.Destroy()

    def list_templates(self) -> List[Dict[str, Any]]:
        """List all VM templates."""
        templates = []
        container = self._content.viewManager.CreateContainerView(
            self._content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm in container.view:
                if vm.config and vm.config.template:
                    templates.append({
                        "name": vm.name,
                        "guest_os": vm.config.guestFullName,
                        "num_cpu": vm.config.hardware.numCPU,
                        "memory_mb": vm.config.hardware.memoryMB,
                    })
            return templates
        finally:
            container.Destroy()

    def get_datacenter(self, name: str = None) -> Optional[Any]:
        """Get datacenter by name or return first available."""
        for dc in self._content.rootFolder.childEntity:
            if isinstance(dc, vim.Datacenter):
                if name is None or dc.name == name:
                    return dc
        return None

    def get_cluster(self, datacenter, name: str) -> Optional[Any]:
        """Get compute cluster by name."""
        for cluster in datacenter.hostFolder.childEntity:
            if isinstance(cluster, vim.ClusterComputeResource):
                if cluster.name == name:
                    return cluster
        return None

    def get_datastore(self, datacenter, name: str) -> Optional[Any]:
        """Get datastore by name."""
        for ds in datacenter.datastoreFolder.childEntity:
            if ds.name == name:
                return ds
        return None

    def get_network(self, datacenter, name: str) -> Optional[Any]:
        """Get network/portgroup by name."""
        for network in datacenter.networkFolder.childEntity:
            if network.name == name:
                return network
        return None

    def get_resource_pool(self, cluster) -> Any:
        """Get default resource pool for cluster."""
        return cluster.resourcePool

    def clone_vm(
        self,
        template_name: str,
        vm_name: str,
        datacenter_name: str = None,
        cluster_name: str = None,
        datastore_name: str = None,
        num_cpus: int = None,
        memory_mb: int = None,
        network_name: str = None,
        power_on: bool = True
    ) -> Dict[str, Any]:
        """
        Clone a VM from a template.

        Args:
            template_name: Source template name
            vm_name: Name for new VM
            datacenter_name: Target datacenter
            cluster_name: Target cluster
            datastore_name: Target datastore
            num_cpus: Number of CPUs (optional)
            memory_mb: Memory in MB (optional)
            network_name: Network to attach (optional)
            power_on: Power on after creation

        Returns:
            Dict with clone operation results
        """
        # Find template
        template = self.get_vm_by_name(template_name)
        if not template:
            return {"status": "error", "message": f"Template '{template_name}' not found"}

        # Get datacenter
        datacenter = self.get_datacenter(datacenter_name or self.config.datacenter)
        if not datacenter:
            return {"status": "error", "message": "Datacenter not found"}

        # Get cluster
        cluster = None
        if cluster_name or self.config.cluster:
            cluster = self.get_cluster(datacenter, cluster_name or self.config.cluster)

        # Get destination folder
        dest_folder = datacenter.vmFolder

        # Build relocation spec
        relocate_spec = vim.vm.RelocateSpec()

        if datastore_name:
            datastore = self.get_datastore(datacenter, datastore_name)
            if datastore:
                relocate_spec.datastore = datastore

        if cluster:
            relocate_spec.pool = self.get_resource_pool(cluster)

        # Build config spec for customization
        config_spec = vim.vm.ConfigSpec()
        if num_cpus:
            config_spec.numCPUs = num_cpus
        if memory_mb:
            config_spec.memoryMB = memory_mb

        # Build clone spec
        clone_spec = vim.vm.CloneSpec()
        clone_spec.location = relocate_spec
        clone_spec.config = config_spec
        clone_spec.powerOn = power_on
        clone_spec.template = False

        try:
            self.logger.info(f"Cloning template '{template_name}' to '{vm_name}'")
            task = template.Clone(folder=dest_folder, name=vm_name, spec=clone_spec)
            self._wait_for_task(task)

            return {
                "status": "success",
                "message": f"VM '{vm_name}' created successfully",
                "vm_name": vm_name,
                "power_state": "poweredOn" if power_on else "poweredOff"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def power_on_vm(self, vm_name: str) -> Dict[str, Any]:
        """Power on a VM."""
        vm = self.get_vm_by_name(vm_name)
        if not vm:
            return {"status": "error", "message": f"VM '{vm_name}' not found"}

        if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
            return {"status": "success", "message": "VM already powered on"}

        try:
            task = vm.PowerOnVM_Task()
            self._wait_for_task(task)
            return {"status": "success", "message": f"VM '{vm_name}' powered on"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def power_off_vm(self, vm_name: str, force: bool = False) -> Dict[str, Any]:
        """Power off a VM."""
        vm = self.get_vm_by_name(vm_name)
        if not vm:
            return {"status": "error", "message": f"VM '{vm_name}' not found"}

        if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOff:
            return {"status": "success", "message": "VM already powered off"}

        try:
            if force:
                task = vm.PowerOffVM_Task()
            else:
                vm.ShutdownGuest()
                return {"status": "success", "message": f"Guest shutdown initiated for '{vm_name}'"}

            self._wait_for_task(task)
            return {"status": "success", "message": f"VM '{vm_name}' powered off"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def create_snapshot(
        self,
        vm_name: str,
        snapshot_name: str,
        description: str = "",
        memory: bool = False,
        quiesce: bool = True
    ) -> Dict[str, Any]:
        """Create a VM snapshot."""
        vm = self.get_vm_by_name(vm_name)
        if not vm:
            return {"status": "error", "message": f"VM '{vm_name}' not found"}

        try:
            task = vm.CreateSnapshot_Task(
                name=snapshot_name,
                description=description,
                memory=memory,
                quiesce=quiesce
            )
            self._wait_for_task(task)
            return {
                "status": "success",
                "message": f"Snapshot '{snapshot_name}' created for '{vm_name}'"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_vm(self, vm_name: str) -> Dict[str, Any]:
        """Delete a VM."""
        vm = self.get_vm_by_name(vm_name)
        if not vm:
            return {"status": "error", "message": f"VM '{vm_name}' not found"}

        try:
            # Power off first if running
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                power_task = vm.PowerOffVM_Task()
                self._wait_for_task(power_task)

            task = vm.Destroy_Task()
            self._wait_for_task(task)
            return {"status": "success", "message": f"VM '{vm_name}' deleted"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_vm_info(self, vm_name: str) -> Dict[str, Any]:
        """Get detailed VM information."""
        vm = self.get_vm_by_name(vm_name)
        if not vm:
            return {"status": "error", "message": f"VM '{vm_name}' not found"}

        try:
            return {
                "status": "success",
                "vm": {
                    "name": vm.name,
                    "uuid": vm.config.uuid,
                    "power_state": str(vm.runtime.powerState),
                    "num_cpu": vm.config.hardware.numCPU,
                    "memory_mb": vm.config.hardware.memoryMB,
                    "guest_os": vm.config.guestFullName,
                    "guest_id": vm.config.guestId,
                    "ip_address": vm.guest.ipAddress if vm.guest else None,
                    "hostname": vm.guest.hostName if vm.guest else None,
                    "tools_status": str(vm.guest.toolsStatus) if vm.guest else None,
                    "tools_version": vm.guest.toolsVersion if vm.guest else None,
                    "annotation": vm.config.annotation,
                    "disks": self._get_vm_disks(vm),
                    "networks": self._get_vm_networks(vm),
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_vm_disks(self, vm) -> List[Dict[str, Any]]:
        """Get VM disk information."""
        disks = []
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualDisk):
                disks.append({
                    "label": device.deviceInfo.label,
                    "size_gb": device.capacityInKB / 1024 / 1024,
                    "thin_provisioned": getattr(device.backing, 'thinProvisioned', None),
                    "datastore": device.backing.datastore.name if device.backing.datastore else None,
                })
        return disks

    def _get_vm_networks(self, vm) -> List[Dict[str, Any]]:
        """Get VM network information."""
        networks = []
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                networks.append({
                    "label": device.deviceInfo.label,
                    "mac_address": device.macAddress,
                    "connected": device.connectable.connected if device.connectable else None,
                    "network": device.backing.deviceName if hasattr(device.backing, 'deviceName') else None,
                })
        return networks

    def _wait_for_task(self, task, timeout: int = 600) -> Any:
        """Wait for a vSphere task to complete."""
        start_time = time.time()
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task timed out after {timeout} seconds")
            time.sleep(1)

        if task.info.state == vim.TaskInfo.State.error:
            raise Exception(task.info.error.msg)

        return task.info.result
