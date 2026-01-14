"""
PagerDuty Integration

Provides integration with PagerDuty:
- Incident management
- Event triggering
- On-call scheduling
- Escalation policies
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import json
import hashlib

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None


@dataclass
class PagerDutyConfig:
    """PagerDuty connection configuration."""
    api_key: str  # REST API key (v2)
    integration_key: str = None  # Events API integration key (for triggering)
    timeout: int = 30
    region: str = "us"  # 'us' or 'eu'


class PagerDutyClient:
    """
    PagerDuty REST API client.

    Provides access to:
    - Incidents (create, update, resolve)
    - Events (trigger, acknowledge, resolve)
    - Services
    - Escalation policies
    - On-call schedules
    - Users
    """

    def __init__(self, config: PagerDutyConfig, logger: logging.Logger = None):
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required. Install with: pip install requests")

        self.config = config
        self.logger = logger or logging.getLogger("pagerduty")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token token={config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2"
        })

        # Set URLs based on region
        if config.region == "eu":
            self._api_url = "https://api.eu.pagerduty.com"
            self._events_url = "https://events.eu.pagerduty.com/v2/enqueue"
        else:
            self._api_url = "https://api.pagerduty.com"
            self._events_url = "https://events.pagerduty.com/v2/enqueue"

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict[str, Any]:
        """Make an API request to PagerDuty REST API."""
        url = f"{self._api_url}/{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.config.timeout
            )

            if response.status_code in [200, 201, 204]:
                if response.text:
                    return {"status": "success", "data": response.json()}
                return {"status": "success", "data": {}}
            elif response.status_code == 400:
                error = response.json().get("error", {})
                return {
                    "status": "error",
                    "message": error.get("message", "Bad request"),
                    "errors": error.get("errors", [])
                }
            elif response.status_code == 401:
                return {"status": "error", "message": "Invalid API key"}
            elif response.status_code == 403:
                return {"status": "error", "message": "Permission denied"}
            elif response.status_code == 404:
                return {"status": "error", "message": "Resource not found"}
            elif response.status_code == 429:
                return {"status": "error", "message": "Rate limited"}
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "message": response.text
                }

        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Request timed out"}
        except requests.exceptions.ConnectionError as e:
            return {"status": "error", "message": f"Connection error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _send_event(self, payload: Dict) -> Dict[str, Any]:
        """Send an event to the Events API."""
        try:
            response = requests.post(
                self._events_url,
                json=payload,
                timeout=self.config.timeout
            )

            if response.status_code in [200, 201, 202]:
                return {"status": "success", "data": response.json()}
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "message": response.text
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check PagerDuty connectivity."""
        result = self._api_request("GET", "abilities")
        if result["status"] == "success":
            return {
                "status": "healthy",
                "region": self.config.region,
                "abilities": result["data"].get("abilities", [])
            }
        return {
            "status": "unhealthy",
            "error": result.get("message")
        }

    # ==================== Events API (Triggering Alerts) ====================

    def trigger_event(
        self,
        routing_key: str,
        summary: str,
        source: str,
        severity: str = "error",
        dedup_key: str = None,
        component: str = None,
        group: str = None,
        class_type: str = None,
        custom_details: Dict = None,
        links: List[Dict] = None,
        images: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Trigger an alert event.

        Args:
            routing_key: Integration key for the service
            summary: Alert summary (max 1024 chars)
            source: Source of the alert
            severity: critical, error, warning, or info
            dedup_key: Deduplication key (auto-generated if not provided)
            component: Component that's affected
            group: Logical grouping
            class_type: Type/category of the event
            custom_details: Additional details
            links: Related links
            images: Related images

        Returns:
            Response with dedup_key for future reference
        """
        routing_key = routing_key or self.config.integration_key
        if not routing_key:
            return {"status": "error", "message": "No routing key provided"}

        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": summary[:1024],
                "source": source,
                "severity": severity.lower(),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }

        if dedup_key:
            payload["dedup_key"] = dedup_key

        if component:
            payload["payload"]["component"] = component
        if group:
            payload["payload"]["group"] = group
        if class_type:
            payload["payload"]["class"] = class_type
        if custom_details:
            payload["payload"]["custom_details"] = custom_details
        if links:
            payload["links"] = links
        if images:
            payload["images"] = images

        self.logger.info(f"Triggering PagerDuty event: {summary}")
        return self._send_event(payload)

    def acknowledge_event(
        self,
        routing_key: str,
        dedup_key: str
    ) -> Dict[str, Any]:
        """
        Acknowledge an alert.

        Args:
            routing_key: Integration key
            dedup_key: Deduplication key from trigger response
        """
        routing_key = routing_key or self.config.integration_key

        payload = {
            "routing_key": routing_key,
            "event_action": "acknowledge",
            "dedup_key": dedup_key
        }

        return self._send_event(payload)

    def resolve_event(
        self,
        routing_key: str,
        dedup_key: str
    ) -> Dict[str, Any]:
        """
        Resolve an alert.

        Args:
            routing_key: Integration key
            dedup_key: Deduplication key from trigger response
        """
        routing_key = routing_key or self.config.integration_key

        payload = {
            "routing_key": routing_key,
            "event_action": "resolve",
            "dedup_key": dedup_key
        }

        return self._send_event(payload)

    # ==================== Incidents API ====================

    def list_incidents(
        self,
        statuses: List[str] = None,
        service_ids: List[str] = None,
        urgencies: List[str] = None,
        since: datetime = None,
        until: datetime = None,
        limit: int = 25
    ) -> Dict[str, Any]:
        """
        List incidents.

        Args:
            statuses: Filter by status (triggered, acknowledged, resolved)
            service_ids: Filter by service IDs
            urgencies: Filter by urgency (high, low)
            since: Start of date range
            until: End of date range
            limit: Maximum results
        """
        params = {"limit": limit}

        if statuses:
            params["statuses[]"] = statuses
        if service_ids:
            params["service_ids[]"] = service_ids
        if urgencies:
            params["urgencies[]"] = urgencies
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        return self._api_request("GET", "incidents", params=params)

    def get_incident(self, incident_id: str) -> Dict[str, Any]:
        """Get incident details."""
        return self._api_request("GET", f"incidents/{incident_id}")

    def create_incident(
        self,
        title: str,
        service_id: str,
        urgency: str = "high",
        body: str = None,
        escalation_policy_id: str = None,
        incident_key: str = None
    ) -> Dict[str, Any]:
        """
        Create an incident via REST API.

        Args:
            title: Incident title
            service_id: Service ID
            urgency: high or low
            body: Incident body/description
            escalation_policy_id: Override escalation policy
            incident_key: Deduplication key
        """
        data = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {
                    "id": service_id,
                    "type": "service_reference"
                },
                "urgency": urgency.lower()
            }
        }

        if body:
            data["incident"]["body"] = {"type": "incident_body", "details": body}
        if escalation_policy_id:
            data["incident"]["escalation_policy"] = {
                "id": escalation_policy_id,
                "type": "escalation_policy_reference"
            }
        if incident_key:
            data["incident"]["incident_key"] = incident_key

        self.logger.info(f"Creating PagerDuty incident: {title}")
        return self._api_request("POST", "incidents", data=data)

    def update_incident(
        self,
        incident_id: str,
        status: str = None,
        resolution: str = None,
        title: str = None,
        urgency: str = None,
        escalation_level: int = None,
        assignments: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Update an incident.

        Args:
            incident_id: Incident ID
            status: New status (acknowledged, resolved)
            resolution: Resolution notes
            title: New title
            urgency: New urgency
            escalation_level: Escalation level
            assignments: New assignments
        """
        incident_data = {"type": "incident"}

        if status:
            incident_data["status"] = status.lower()
        if resolution:
            incident_data["resolution"] = resolution
        if title:
            incident_data["title"] = title
        if urgency:
            incident_data["urgency"] = urgency.lower()
        if escalation_level is not None:
            incident_data["escalation_level"] = escalation_level
        if assignments:
            incident_data["assignments"] = assignments

        return self._api_request(
            "PUT",
            f"incidents/{incident_id}",
            data={"incident": incident_data}
        )

    def acknowledge_incident(self, incident_id: str) -> Dict[str, Any]:
        """Acknowledge an incident."""
        return self.update_incident(incident_id, status="acknowledged")

    def resolve_incident(self, incident_id: str, resolution: str = None) -> Dict[str, Any]:
        """Resolve an incident."""
        return self.update_incident(incident_id, status="resolved", resolution=resolution)

    def add_incident_note(self, incident_id: str, content: str) -> Dict[str, Any]:
        """Add a note to an incident."""
        data = {
            "note": {
                "content": content
            }
        }
        return self._api_request("POST", f"incidents/{incident_id}/notes", data=data)

    def get_incident_notes(self, incident_id: str) -> Dict[str, Any]:
        """Get notes for an incident."""
        return self._api_request("GET", f"incidents/{incident_id}/notes")

    # ==================== Services ====================

    def list_services(self, limit: int = 25) -> Dict[str, Any]:
        """List all services."""
        return self._api_request("GET", "services", params={"limit": limit})

    def get_service(self, service_id: str) -> Dict[str, Any]:
        """Get service details."""
        return self._api_request("GET", f"services/{service_id}")

    # ==================== Escalation Policies ====================

    def list_escalation_policies(self, limit: int = 25) -> Dict[str, Any]:
        """List escalation policies."""
        return self._api_request("GET", "escalation_policies", params={"limit": limit})

    def get_escalation_policy(self, policy_id: str) -> Dict[str, Any]:
        """Get escalation policy details."""
        return self._api_request("GET", f"escalation_policies/{policy_id}")

    # ==================== Schedules ====================

    def list_schedules(self, limit: int = 25) -> Dict[str, Any]:
        """List on-call schedules."""
        return self._api_request("GET", "schedules", params={"limit": limit})

    def get_schedule(self, schedule_id: str) -> Dict[str, Any]:
        """Get schedule details."""
        return self._api_request("GET", f"schedules/{schedule_id}")

    def get_on_call_users(
        self,
        schedule_ids: List[str] = None,
        escalation_policy_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get users currently on call.

        Args:
            schedule_ids: Filter by schedule IDs
            escalation_policy_ids: Filter by escalation policy IDs
        """
        params = {}
        if schedule_ids:
            params["schedule_ids[]"] = schedule_ids
        if escalation_policy_ids:
            params["escalation_policy_ids[]"] = escalation_policy_ids

        return self._api_request("GET", "oncalls", params=params)

    # ==================== Users ====================

    def list_users(self, limit: int = 25) -> Dict[str, Any]:
        """List users."""
        return self._api_request("GET", "users", params={"limit": limit})

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user details."""
        return self._api_request("GET", f"users/{user_id}")

    def get_current_user(self) -> Dict[str, Any]:
        """Get current authenticated user."""
        return self._api_request("GET", "users/me")

    # ==================== Automation Helper Methods ====================

    def trigger_alert(
        self,
        title: str,
        description: str,
        severity: str,
        source: str,
        component: str = None,
        routing_key: str = None,
        custom_details: Dict = None
    ) -> Dict[str, Any]:
        """
        Convenience method to trigger an alert.

        Args:
            title: Alert title
            description: Alert description
            severity: critical, error, warning, info
            source: Source system/host
            component: Affected component
            routing_key: Integration key (uses default if not provided)
            custom_details: Additional details

        Returns:
            Response with dedup_key for tracking
        """
        # Generate dedup key from title and source for idempotency
        dedup_key = hashlib.md5(f"{title}:{source}".encode()).hexdigest()

        details = {
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if custom_details:
            details.update(custom_details)

        return self.trigger_event(
            routing_key=routing_key,
            summary=title,
            source=source,
            severity=severity,
            dedup_key=dedup_key,
            component=component,
            custom_details=details
        )

    def auto_resolve_if_healthy(
        self,
        dedup_key: str,
        health_status: bool,
        routing_key: str = None
    ) -> Dict[str, Any]:
        """
        Automatically resolve an alert if health check passes.

        Args:
            dedup_key: Deduplication key from original trigger
            health_status: True if healthy, False if still unhealthy
            routing_key: Integration key

        Returns:
            Resolution result or no-op message
        """
        if health_status:
            return self.resolve_event(routing_key, dedup_key)
        return {"status": "no_action", "message": "System still unhealthy"}

    def escalate_incident(
        self,
        incident_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Escalate an incident to the next level.

        Args:
            incident_id: Incident ID
            reason: Reason for escalation
        """
        # Get current incident
        incident_result = self.get_incident(incident_id)
        if incident_result["status"] != "success":
            return incident_result

        incident = incident_result["data"].get("incident", {})
        current_level = incident.get("escalation_level", 0)

        # Update with next level
        result = self.update_incident(
            incident_id,
            escalation_level=current_level + 1
        )

        # Add note about escalation
        if result["status"] == "success":
            self.add_incident_note(
                incident_id,
                f"Incident escalated from level {current_level} to {current_level + 1}. Reason: {reason}"
            )

        return result
