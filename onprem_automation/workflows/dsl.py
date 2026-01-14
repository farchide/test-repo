"""
Workflow DSL (Domain Specific Language)

Defines the YAML-based workflow definition format:

```yaml
name: VM Provisioning Workflow
description: Provisions and configures a new VM
version: 1

inputs:
  vm_name:
    type: string
    required: true
  cpu_count:
    type: integer
    default: 2

steps:
  - name: provision_vm
    module: vmware
    action: provision_vm
    parameters:
      name: "{{ inputs.vm_name }}"
      cpu: "{{ inputs.cpu_count }}"
    on_error: fail

  - name: configure_network
    module: network
    action: create_vlan
    depends_on: [provision_vm]
    condition: "{{ steps.provision_vm.status == 'success' }}"
    parameters:
      vm_id: "{{ steps.provision_vm.result.vm_id }}"

  - name: parallel_config
    parallel:
      - name: install_agent
        module: vmware
        action: run_script
        parameters:
          vm_id: "{{ steps.provision_vm.result.vm_id }}"
          script: install_monitoring_agent.sh

      - name: configure_backup
        module: backup
        action: add_to_backup_job
        parameters:
          vm_id: "{{ steps.provision_vm.result.vm_id }}"

  - name: notify
    module: itsm
    action: create_ticket
    condition: "{{ steps.provision_vm.status == 'success' }}"
    parameters:
      title: "VM {{ inputs.vm_name }} provisioned"

outputs:
  vm_id: "{{ steps.provision_vm.result.vm_id }}"
  ip_address: "{{ steps.provision_vm.result.ip_address }}"
```
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import re
import yaml
import logging

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    ACTION = "action"
    PARALLEL = "parallel"
    APPROVAL = "approval"
    CONDITION = "condition"
    LOOP = "loop"
    WAIT = "wait"
    SCRIPT = "script"


class OnErrorAction(str, Enum):
    FAIL = "fail"
    CONTINUE = "continue"
    RETRY = "retry"
    ROLLBACK = "rollback"


@dataclass
class InputDefinition:
    """Workflow input parameter definition."""
    name: str
    type: str = "string"  # string, integer, float, boolean, list, object
    required: bool = False
    default: Any = None
    description: str = ""
    choices: List[Any] = field(default_factory=list)
    validation: str = ""  # Regex pattern for string validation


@dataclass
class OutputDefinition:
    """Workflow output definition."""
    name: str
    value: str  # Template expression


@dataclass
class Condition:
    """Conditional expression for workflow logic."""
    expression: str  # Jinja2-style expression

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition against context."""
        from .executor import TemplateEngine
        result = TemplateEngine.render(self.expression, context)
        return result.lower() in ("true", "1", "yes")


@dataclass
class RetryPolicy:
    """Retry policy for step execution."""
    max_attempts: int = 3
    delay_seconds: int = 10
    backoff_multiplier: float = 2.0
    max_delay_seconds: int = 300
    retry_on: List[str] = field(default_factory=list)  # Error types to retry


@dataclass
class Step:
    """Workflow step definition."""
    name: str
    step_type: StepType = StepType.ACTION

    # For action steps
    module: Optional[str] = None
    action: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    # For parallel steps
    parallel_steps: List["Step"] = field(default_factory=list)

    # For loop steps
    loop_items: str = ""  # Expression that evaluates to list
    loop_variable: str = "item"

    # Control flow
    depends_on: List[str] = field(default_factory=list)
    condition: Optional[str] = None
    on_error: OnErrorAction = OnErrorAction.FAIL
    retry: Optional[RetryPolicy] = None
    timeout: int = 600  # seconds

    # Approval steps
    approvers: List[str] = field(default_factory=list)
    approval_timeout: int = 86400  # 24 hours

    # Wait steps
    wait_seconds: int = 0
    wait_until: str = ""  # Condition to wait for

    # Script steps
    script: str = ""
    script_type: str = "bash"  # bash, python, powershell

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""
    name: str
    description: str = ""
    version: int = 1

    # Input/Output
    inputs: Dict[str, InputDefinition] = field(default_factory=dict)
    outputs: Dict[str, OutputDefinition] = field(default_factory=dict)

    # Steps
    steps: List[Step] = field(default_factory=list)

    # Settings
    timeout: int = 7200
    max_parallel: int = 5
    require_approval: bool = False
    on_error: OnErrorAction = OnErrorAction.FAIL

    # Metadata
    author: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)


class WorkflowDSL:
    """
    Workflow DSL parser and validator.

    Parses YAML workflow definitions into WorkflowDefinition objects.
    """

    @classmethod
    def parse(cls, yaml_content: str) -> WorkflowDefinition:
        """Parse YAML content into WorkflowDefinition."""
        data = yaml.safe_load(yaml_content)
        return cls.from_dict(data)

    @classmethod
    def parse_file(cls, file_path: str) -> WorkflowDefinition:
        """Parse workflow from YAML file."""
        with open(file_path, 'r') as f:
            return cls.parse(f.read())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowDefinition:
        """Create WorkflowDefinition from dictionary."""
        # Parse inputs
        inputs = {}
        for name, input_def in data.get("inputs", {}).items():
            if isinstance(input_def, dict):
                inputs[name] = InputDefinition(
                    name=name,
                    type=input_def.get("type", "string"),
                    required=input_def.get("required", False),
                    default=input_def.get("default"),
                    description=input_def.get("description", ""),
                    choices=input_def.get("choices", []),
                    validation=input_def.get("validation", ""),
                )
            else:
                # Simple default value
                inputs[name] = InputDefinition(name=name, default=input_def)

        # Parse outputs
        outputs = {}
        for name, value in data.get("outputs", {}).items():
            outputs[name] = OutputDefinition(name=name, value=value)

        # Parse steps
        steps = [cls._parse_step(s) for s in data.get("steps", [])]

        return WorkflowDefinition(
            name=data.get("name", "Unnamed Workflow"),
            description=data.get("description", ""),
            version=data.get("version", 1),
            inputs=inputs,
            outputs=outputs,
            steps=steps,
            timeout=data.get("timeout", 7200),
            max_parallel=data.get("max_parallel", 5),
            require_approval=data.get("require_approval", False),
            on_error=OnErrorAction(data.get("on_error", "fail")),
            author=data.get("author", ""),
            category=data.get("category", ""),
            tags=data.get("tags", []),
        )

    @classmethod
    def _parse_step(cls, data: Dict[str, Any]) -> Step:
        """Parse a single step definition."""
        name = data.get("name", "unnamed_step")

        # Determine step type
        if "parallel" in data:
            step_type = StepType.PARALLEL
            parallel_steps = [cls._parse_step(s) for s in data["parallel"]]
        elif "approval" in data or data.get("type") == "approval":
            step_type = StepType.APPROVAL
            parallel_steps = []
        elif "loop" in data:
            step_type = StepType.LOOP
            parallel_steps = []
        elif "wait" in data or "wait_seconds" in data:
            step_type = StepType.WAIT
            parallel_steps = []
        elif "script" in data:
            step_type = StepType.SCRIPT
            parallel_steps = []
        else:
            step_type = StepType.ACTION
            parallel_steps = []

        # Parse retry policy
        retry = None
        if "retry" in data:
            retry_data = data["retry"]
            retry = RetryPolicy(
                max_attempts=retry_data.get("max_attempts", 3),
                delay_seconds=retry_data.get("delay_seconds", 10),
                backoff_multiplier=retry_data.get("backoff_multiplier", 2.0),
                max_delay_seconds=retry_data.get("max_delay_seconds", 300),
                retry_on=retry_data.get("retry_on", []),
            )

        return Step(
            name=name,
            step_type=step_type,
            module=data.get("module"),
            action=data.get("action"),
            parameters=data.get("parameters", {}),
            parallel_steps=parallel_steps,
            loop_items=data.get("loop", ""),
            loop_variable=data.get("loop_variable", "item"),
            depends_on=data.get("depends_on", []),
            condition=data.get("condition"),
            on_error=OnErrorAction(data.get("on_error", "fail")),
            retry=retry,
            timeout=data.get("timeout", 600),
            approvers=data.get("approvers", []),
            approval_timeout=data.get("approval_timeout", 86400),
            wait_seconds=data.get("wait_seconds", 0),
            wait_until=data.get("wait_until", ""),
            script=data.get("script", ""),
            script_type=data.get("script_type", "bash"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )

    @classmethod
    def to_dict(cls, workflow: WorkflowDefinition) -> Dict[str, Any]:
        """Convert WorkflowDefinition to dictionary."""
        return {
            "name": workflow.name,
            "description": workflow.description,
            "version": workflow.version,
            "inputs": {
                name: {
                    "type": inp.type,
                    "required": inp.required,
                    "default": inp.default,
                    "description": inp.description,
                }
                for name, inp in workflow.inputs.items()
            },
            "outputs": {
                name: out.value for name, out in workflow.outputs.items()
            },
            "steps": [cls._step_to_dict(s) for s in workflow.steps],
            "timeout": workflow.timeout,
            "max_parallel": workflow.max_parallel,
            "require_approval": workflow.require_approval,
            "on_error": workflow.on_error.value,
            "author": workflow.author,
            "category": workflow.category,
            "tags": workflow.tags,
        }

    @classmethod
    def _step_to_dict(cls, step: Step) -> Dict[str, Any]:
        """Convert Step to dictionary."""
        data = {
            "name": step.name,
        }

        if step.step_type == StepType.PARALLEL:
            data["parallel"] = [cls._step_to_dict(s) for s in step.parallel_steps]
        elif step.step_type == StepType.APPROVAL:
            data["type"] = "approval"
            data["approvers"] = step.approvers
            data["approval_timeout"] = step.approval_timeout
        elif step.step_type == StepType.LOOP:
            data["loop"] = step.loop_items
            data["loop_variable"] = step.loop_variable
            data["module"] = step.module
            data["action"] = step.action
            data["parameters"] = step.parameters
        elif step.step_type == StepType.WAIT:
            data["wait_seconds"] = step.wait_seconds
            if step.wait_until:
                data["wait_until"] = step.wait_until
        elif step.step_type == StepType.SCRIPT:
            data["script"] = step.script
            data["script_type"] = step.script_type
        else:
            data["module"] = step.module
            data["action"] = step.action
            data["parameters"] = step.parameters

        if step.depends_on:
            data["depends_on"] = step.depends_on
        if step.condition:
            data["condition"] = step.condition
        if step.on_error != OnErrorAction.FAIL:
            data["on_error"] = step.on_error.value
        if step.retry:
            data["retry"] = {
                "max_attempts": step.retry.max_attempts,
                "delay_seconds": step.retry.delay_seconds,
            }
        if step.timeout != 600:
            data["timeout"] = step.timeout
        if step.description:
            data["description"] = step.description

        return data

    @classmethod
    def to_yaml(cls, workflow: WorkflowDefinition) -> str:
        """Convert WorkflowDefinition to YAML string."""
        return yaml.dump(cls.to_dict(workflow), default_flow_style=False, sort_keys=False)

    @classmethod
    def validate(cls, workflow: WorkflowDefinition) -> List[str]:
        """
        Validate workflow definition.

        Returns list of validation errors (empty if valid).
        """
        errors = []

        if not workflow.name:
            errors.append("Workflow name is required")

        if not workflow.steps:
            errors.append("Workflow must have at least one step")

        step_names = set()
        for step in workflow.steps:
            # Check for duplicate names
            if step.name in step_names:
                errors.append(f"Duplicate step name: {step.name}")
            step_names.add(step.name)

            # Validate action steps
            if step.step_type == StepType.ACTION:
                if not step.module:
                    errors.append(f"Step '{step.name}' missing module")
                if not step.action:
                    errors.append(f"Step '{step.name}' missing action")

            # Validate dependencies
            for dep in step.depends_on:
                if dep not in step_names and dep != step.name:
                    # Check if it's defined earlier
                    found = False
                    for s in workflow.steps:
                        if s.name == dep:
                            found = True
                            break
                        if s.name == step.name:
                            break
                    if not found:
                        errors.append(f"Step '{step.name}' depends on unknown step '{dep}'")

        return errors
