"""
ServiceNow Integration

Provides integration with ServiceNow ITSM:
- Incident management
- Change request management
- CMDB operations
- Service catalog
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import json

try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None


@dataclass
class ServiceNowConfig:
    """ServiceNow connection configuration."""
    instance: str  # e.g., 'dev12345' for dev12345.service-now.com
    username: str
    password: str
    timeout: int = 30
    verify_ssl: bool = True


class ServiceNowClient:
    """
    ServiceNow REST API client.

    Supports Table API operations for:
    - Incidents (incident)
    - Change Requests (change_request)
    - Problems (problem)
    - Configuration Items (cmdb_ci)
    - Users (sys_user)
    - Groups (sys_user_group)
    """

    # Common ServiceNow tables
    TABLES = {
        "incident": "incident",
        "change": "change_request",
        "problem": "problem",
        "ci": "cmdb_ci",
        "server": "cmdb_ci_server",
        "vm": "cmdb_ci_vm_instance",
        "user": "sys_user",
        "group": "sys_user_group",
        "task": "task",
    }

    # Incident states
    INCIDENT_STATES = {
        "new": 1,
        "in_progress": 2,
        "on_hold": 3,
        "resolved": 6,
        "closed": 7,
        "cancelled": 8
    }

    # Priority levels
    PRIORITIES = {
        "critical": 1,
        "high": 2,
        "moderate": 3,
        "low": 4,
        "planning": 5
    }

    def __init__(self, config: ServiceNowConfig, logger: logging.Logger = None):
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required. Install with: pip install requests")

        self.config = config
        self.logger = logger or logging.getLogger("servicenow")
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(config.username, config.password)
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self._session.verify = config.verify_ssl
        self._base_url = f"https://{config.instance}.service-now.com/api/now"

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict[str, Any]:
        """Make an API request to ServiceNow."""
        url = f"{self._base_url}/{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.config.timeout
            )

            if response.status_code in [200, 201]:
                return {"status": "success", "data": response.json().get("result", {})}
            elif response.status_code == 204:
                return {"status": "success", "data": {}}
            elif response.status_code == 401:
                return {"status": "error", "message": "Authentication failed"}
            elif response.status_code == 403:
                return {"status": "error", "message": "Permission denied"}
            elif response.status_code == 404:
                return {"status": "error", "message": "Resource not found"}
            else:
                error_msg = response.json().get("error", {}).get("message", response.text)
                return {"status": "error", "code": response.status_code, "message": error_msg}

        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Request timed out"}
        except requests.exceptions.ConnectionError as e:
            return {"status": "error", "message": f"Connection error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check ServiceNow connectivity."""
        result = self._api_request("GET", "table/sys_properties", params={"sysparm_limit": 1})
        if result["status"] == "success":
            return {
                "status": "healthy",
                "instance": self.config.instance,
            }
        return {
            "status": "unhealthy",
            "instance": self.config.instance,
            "error": result.get("message")
        }

    # ==================== Generic Table Operations ====================

    def get_record(self, table: str, sys_id: str) -> Dict[str, Any]:
        """Get a single record by sys_id."""
        table_name = self.TABLES.get(table, table)
        return self._api_request("GET", f"table/{table_name}/{sys_id}")

    def query_records(
        self,
        table: str,
        query: str = None,
        fields: List[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = None,
        order_desc: bool = False
    ) -> Dict[str, Any]:
        """
        Query records from a table.

        Args:
            table: Table name or alias
            query: Encoded query string (e.g., "active=true^state=1")
            fields: List of fields to return
            limit: Maximum records to return
            offset: Offset for pagination
            order_by: Field to order by
            order_desc: Order descending if True
        """
        table_name = self.TABLES.get(table, table)
        params = {
            "sysparm_limit": limit,
            "sysparm_offset": offset
        }

        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        if order_by:
            order_prefix = "ORDERBYDESC" if order_desc else "ORDERBY"
            existing_query = params.get("sysparm_query", "")
            params["sysparm_query"] = f"{existing_query}^{order_prefix}{order_by}"

        return self._api_request("GET", f"table/{table_name}", params=params)

    def create_record(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record."""
        table_name = self.TABLES.get(table, table)
        return self._api_request("POST", f"table/{table_name}", data=data)

    def update_record(self, table: str, sys_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing record."""
        table_name = self.TABLES.get(table, table)
        return self._api_request("PATCH", f"table/{table_name}/{sys_id}", data=data)

    def delete_record(self, table: str, sys_id: str) -> Dict[str, Any]:
        """Delete a record."""
        table_name = self.TABLES.get(table, table)
        return self._api_request("DELETE", f"table/{table_name}/{sys_id}")

    # ==================== Incident Management ====================

    def create_incident(
        self,
        short_description: str,
        description: str = None,
        caller_id: str = None,
        category: str = None,
        subcategory: str = None,
        impact: int = 3,
        urgency: int = 3,
        assignment_group: str = None,
        assigned_to: str = None,
        ci: str = None,
        additional_fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Create a new incident.

        Args:
            short_description: Brief incident description
            description: Detailed description
            caller_id: User sys_id who reported the incident
            category: Incident category
            subcategory: Incident subcategory
            impact: Impact level (1-3)
            urgency: Urgency level (1-3)
            assignment_group: Group sys_id to assign to
            assigned_to: User sys_id to assign to
            ci: Configuration item sys_id
            additional_fields: Any additional fields

        Returns:
            Created incident data
        """
        data = {
            "short_description": short_description,
            "impact": impact,
            "urgency": urgency,
        }

        if description:
            data["description"] = description
        if caller_id:
            data["caller_id"] = caller_id
        if category:
            data["category"] = category
        if subcategory:
            data["subcategory"] = subcategory
        if assignment_group:
            data["assignment_group"] = assignment_group
        if assigned_to:
            data["assigned_to"] = assigned_to
        if ci:
            data["cmdb_ci"] = ci
        if additional_fields:
            data.update(additional_fields)

        self.logger.info(f"Creating incident: {short_description}")
        return self.create_record("incident", data)

    def get_incident(self, incident_number: str = None, sys_id: str = None) -> Dict[str, Any]:
        """Get incident by number or sys_id."""
        if sys_id:
            return self.get_record("incident", sys_id)
        elif incident_number:
            return self.query_records("incident", query=f"number={incident_number}", limit=1)
        else:
            return {"status": "error", "message": "Either incident_number or sys_id required"}

    def update_incident(
        self,
        sys_id: str,
        state: str = None,
        work_notes: str = None,
        close_notes: str = None,
        close_code: str = None,
        additional_fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Update an incident.

        Args:
            sys_id: Incident sys_id
            state: New state (new, in_progress, on_hold, resolved, closed)
            work_notes: Work notes to add
            close_notes: Close notes (required for resolution)
            close_code: Close code (required for resolution)
            additional_fields: Any additional fields to update
        """
        data = {}

        if state:
            data["state"] = self.INCIDENT_STATES.get(state, state)
        if work_notes:
            data["work_notes"] = work_notes
        if close_notes:
            data["close_notes"] = close_notes
        if close_code:
            data["close_code"] = close_code
        if additional_fields:
            data.update(additional_fields)

        return self.update_record("incident", sys_id, data)

    def resolve_incident(
        self,
        sys_id: str,
        close_notes: str,
        close_code: str = "Solved (Permanently)"
    ) -> Dict[str, Any]:
        """Resolve an incident."""
        return self.update_incident(
            sys_id,
            state="resolved",
            close_notes=close_notes,
            close_code=close_code
        )

    def add_work_notes(self, sys_id: str, notes: str) -> Dict[str, Any]:
        """Add work notes to an incident."""
        return self.update_record("incident", sys_id, {"work_notes": notes})

    def list_open_incidents(
        self,
        assignment_group: str = None,
        assigned_to: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List open incidents."""
        query_parts = ["active=true", "state!=6", "state!=7"]

        if assignment_group:
            query_parts.append(f"assignment_group={assignment_group}")
        if assigned_to:
            query_parts.append(f"assigned_to={assigned_to}")

        query = "^".join(query_parts)
        return self.query_records(
            "incident",
            query=query,
            limit=limit,
            order_by="sys_created_on",
            order_desc=True
        )

    # ==================== Change Request Management ====================

    def create_change_request(
        self,
        short_description: str,
        description: str = None,
        type: str = "normal",  # normal, standard, emergency
        category: str = None,
        assignment_group: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        ci: str = None,
        additional_fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Create a change request.

        Args:
            short_description: Brief change description
            description: Detailed description
            type: Change type (normal, standard, emergency)
            category: Change category
            assignment_group: Group to assign to
            start_date: Planned start date
            end_date: Planned end date
            ci: Configuration item sys_id
            additional_fields: Any additional fields
        """
        data = {
            "short_description": short_description,
            "type": type,
        }

        if description:
            data["description"] = description
        if category:
            data["category"] = category
        if assignment_group:
            data["assignment_group"] = assignment_group
        if start_date:
            data["start_date"] = start_date.strftime("%Y-%m-%d %H:%M:%S")
        if end_date:
            data["end_date"] = end_date.strftime("%Y-%m-%d %H:%M:%S")
        if ci:
            data["cmdb_ci"] = ci
        if additional_fields:
            data.update(additional_fields)

        self.logger.info(f"Creating change request: {short_description}")
        return self.create_record("change", data)

    def get_change_request(self, change_number: str = None, sys_id: str = None) -> Dict[str, Any]:
        """Get change request by number or sys_id."""
        if sys_id:
            return self.get_record("change", sys_id)
        elif change_number:
            return self.query_records("change", query=f"number={change_number}", limit=1)
        else:
            return {"status": "error", "message": "Either change_number or sys_id required"}

    def update_change_request(self, sys_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a change request."""
        return self.update_record("change", sys_id, data)

    # ==================== CMDB Operations ====================

    def get_ci(self, name: str = None, sys_id: str = None) -> Dict[str, Any]:
        """Get a configuration item."""
        if sys_id:
            return self.get_record("ci", sys_id)
        elif name:
            return self.query_records("ci", query=f"name={name}", limit=1)
        else:
            return {"status": "error", "message": "Either name or sys_id required"}

    def query_servers(self, query: str = None, limit: int = 100) -> Dict[str, Any]:
        """Query server CIs."""
        return self.query_records("server", query=query, limit=limit)

    def query_vms(self, query: str = None, limit: int = 100) -> Dict[str, Any]:
        """Query virtual machine CIs."""
        return self.query_records("vm", query=query, limit=limit)

    def update_ci(self, sys_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a configuration item."""
        return self.update_record("ci", sys_id, data)

    # ==================== User/Group Operations ====================

    def get_user(self, username: str = None, sys_id: str = None) -> Dict[str, Any]:
        """Get a user."""
        if sys_id:
            return self.get_record("user", sys_id)
        elif username:
            return self.query_records("user", query=f"user_name={username}", limit=1)
        else:
            return {"status": "error", "message": "Either username or sys_id required"}

    def get_group(self, name: str = None, sys_id: str = None) -> Dict[str, Any]:
        """Get a group."""
        if sys_id:
            return self.get_record("group", sys_id)
        elif name:
            return self.query_records("group", query=f"name={name}", limit=1)
        else:
            return {"status": "error", "message": "Either name or sys_id required"}

    # ==================== Automation Helper Methods ====================

    def create_incident_from_alert(
        self,
        alert_name: str,
        alert_message: str,
        severity: str,
        source_host: str = None,
        assignment_group: str = None,
        auto_assign: bool = True
    ) -> Dict[str, Any]:
        """
        Create an incident from an automated alert.

        This is a helper method for automation workflows.

        Args:
            alert_name: Name/title of the alert
            alert_message: Alert details
            severity: Alert severity (critical, high, medium, low)
            source_host: Hostname that generated the alert
            assignment_group: Group to assign to
            auto_assign: Auto-assign based on CI if True
        """
        # Map severity to impact/urgency
        severity_map = {
            "critical": (1, 1),
            "high": (2, 2),
            "medium": (2, 3),
            "low": (3, 3),
        }
        impact, urgency = severity_map.get(severity.lower(), (3, 3))

        # Build description
        description = f"""
Automated Incident from Monitoring

Alert: {alert_name}
Severity: {severity}
Source: {source_host or 'Unknown'}
Time: {datetime.now().isoformat()}

Details:
{alert_message}
"""

        # Look up CI if source host provided
        ci_sys_id = None
        if source_host:
            ci_result = self.query_records("ci", query=f"name={source_host}", limit=1)
            if ci_result["status"] == "success" and ci_result["data"]:
                ci_data = ci_result["data"]
                if isinstance(ci_data, list) and len(ci_data) > 0:
                    ci_sys_id = ci_data[0].get("sys_id")

        return self.create_incident(
            short_description=f"[ALERT] {alert_name}",
            description=description,
            impact=impact,
            urgency=urgency,
            assignment_group=assignment_group,
            ci=ci_sys_id,
            additional_fields={
                "category": "Software",
                "subcategory": "Monitoring Alert"
            }
        )

    def log_automation_activity(
        self,
        incident_sys_id: str,
        action: str,
        result: str,
        details: str = None
    ) -> Dict[str, Any]:
        """
        Log automation activity as work notes on an incident.

        Args:
            incident_sys_id: Incident to update
            action: Action that was performed
            result: Result (success/failure)
            details: Additional details
        """
        timestamp = datetime.now().isoformat()
        work_notes = f"""
[AUTOMATION LOG]
Time: {timestamp}
Action: {action}
Result: {result}
{f"Details: {details}" if details else ""}
"""
        return self.add_work_notes(incident_sys_id, work_notes)
