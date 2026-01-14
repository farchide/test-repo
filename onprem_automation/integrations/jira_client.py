"""
Jira Integration

Provides integration with Atlassian Jira:
- Issue management
- Project operations
- Comment and attachment handling
- Workflow transitions
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import base64

try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None


@dataclass
class JiraConfig:
    """Jira connection configuration."""
    url: str  # e.g., 'https://yourcompany.atlassian.net' or 'https://jira.yourcompany.com'
    username: str  # Email for Cloud, username for Server
    api_token: str  # API token for Cloud, password for Server
    timeout: int = 30
    verify_ssl: bool = True
    is_cloud: bool = True  # True for Jira Cloud, False for Server/Data Center


class JiraClient:
    """
    Jira REST API client.

    Supports both Jira Cloud and Jira Server/Data Center.
    Provides operations for:
    - Issues (create, update, search, transition)
    - Projects
    - Comments
    - Attachments
    - Users and groups
    """

    def __init__(self, config: JiraConfig, logger: logging.Logger = None):
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required. Install with: pip install requests")

        self.config = config
        self.logger = logger or logging.getLogger("jira")
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(config.username, config.api_token)
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self._session.verify = config.verify_ssl

        # Set base URL based on Jira type
        base = config.url.rstrip("/")
        self._api_version = "3" if config.is_cloud else "2"
        self._base_url = f"{base}/rest/api/{self._api_version}"

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None,
        files: Dict = None
    ) -> Dict[str, Any]:
        """Make an API request to Jira."""
        url = f"{self._base_url}/{endpoint}"

        try:
            # Handle file uploads differently
            if files:
                headers = {"X-Atlassian-Token": "no-check"}
                response = self._session.request(
                    method=method,
                    url=url,
                    files=files,
                    headers=headers,
                    timeout=self.config.timeout
                )
            else:
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
                errors = response.json().get("errors", response.json())
                return {"status": "error", "message": "Bad request", "errors": errors}
            elif response.status_code == 401:
                return {"status": "error", "message": "Authentication failed"}
            elif response.status_code == 403:
                return {"status": "error", "message": "Permission denied"}
            elif response.status_code == 404:
                return {"status": "error", "message": "Resource not found"}
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

    def health_check(self) -> Dict[str, Any]:
        """Check Jira connectivity."""
        result = self._api_request("GET", "myself")
        if result["status"] == "success":
            return {
                "status": "healthy",
                "url": self.config.url,
                "user": result["data"].get("displayName", result["data"].get("name")),
            }
        return {
            "status": "unhealthy",
            "url": self.config.url,
            "error": result.get("message")
        }

    # ==================== Issue Operations ====================

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str = None,
        priority: str = None,
        assignee: str = None,
        labels: List[str] = None,
        components: List[str] = None,
        custom_fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Create a new issue.

        Args:
            project_key: Project key (e.g., 'INFRA')
            summary: Issue summary/title
            issue_type: Issue type (Task, Bug, Story, etc.)
            description: Detailed description
            priority: Priority name (Highest, High, Medium, Low, Lowest)
            assignee: Assignee account ID (Cloud) or username (Server)
            labels: List of labels
            components: List of component names
            custom_fields: Dictionary of custom field IDs to values

        Returns:
            Created issue data including key
        """
        # Build fields
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            if self.config.is_cloud:
                # Jira Cloud uses ADF (Atlassian Document Format)
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}]
                        }
                    ]
                }
            else:
                # Jira Server uses plain text or wiki markup
                fields["description"] = description

        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            if self.config.is_cloud:
                fields["assignee"] = {"accountId": assignee}
            else:
                fields["assignee"] = {"name": assignee}
        if labels:
            fields["labels"] = labels
        if components:
            fields["components"] = [{"name": c} for c in components]
        if custom_fields:
            fields.update(custom_fields)

        self.logger.info(f"Creating issue in {project_key}: {summary}")
        return self._api_request("POST", "issue", data={"fields": fields})

    def get_issue(self, issue_key: str, fields: List[str] = None) -> Dict[str, Any]:
        """
        Get issue details.

        Args:
            issue_key: Issue key (e.g., 'INFRA-123')
            fields: List of fields to return (None for all)
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self._api_request("GET", f"issue/{issue_key}", params=params)

    def update_issue(
        self,
        issue_key: str,
        summary: str = None,
        description: str = None,
        priority: str = None,
        assignee: str = None,
        labels: List[str] = None,
        custom_fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Update an issue.

        Args:
            issue_key: Issue key
            summary: New summary
            description: New description
            priority: New priority
            assignee: New assignee
            labels: New labels (replaces existing)
            custom_fields: Custom fields to update
        """
        fields = {}

        if summary:
            fields["summary"] = summary
        if description:
            if self.config.is_cloud:
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}]
                        }
                    ]
                }
            else:
                fields["description"] = description
        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            if self.config.is_cloud:
                fields["assignee"] = {"accountId": assignee}
            else:
                fields["assignee"] = {"name": assignee}
        if labels is not None:
            fields["labels"] = labels
        if custom_fields:
            fields.update(custom_fields)

        return self._api_request("PUT", f"issue/{issue_key}", data={"fields": fields})

    def delete_issue(self, issue_key: str) -> Dict[str, Any]:
        """Delete an issue."""
        return self._api_request("DELETE", f"issue/{issue_key}")

    def search_issues(
        self,
        jql: str,
        fields: List[str] = None,
        max_results: int = 50,
        start_at: int = 0
    ) -> Dict[str, Any]:
        """
        Search issues using JQL.

        Args:
            jql: JQL query string
            fields: Fields to return
            max_results: Maximum results to return
            start_at: Offset for pagination

        Example JQL:
            "project = INFRA AND status = Open ORDER BY created DESC"
        """
        data = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at
        }
        if fields:
            data["fields"] = fields

        return self._api_request("POST", "search", data=data)

    # ==================== Transitions ====================

    def get_transitions(self, issue_key: str) -> Dict[str, Any]:
        """Get available transitions for an issue."""
        return self._api_request("GET", f"issue/{issue_key}/transitions")

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: str = None,
        fields: Dict = None
    ) -> Dict[str, Any]:
        """
        Transition an issue to a new status.

        Args:
            issue_key: Issue key
            transition_id: Transition ID (get from get_transitions)
            comment: Optional comment to add
            fields: Fields to update during transition
        """
        data = {"transition": {"id": transition_id}}

        if fields:
            data["fields"] = fields

        if comment:
            if self.config.is_cloud:
                data["update"] = {
                    "comment": [{
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}]
                                    }
                                ]
                            }
                        }
                    }]
                }
            else:
                data["update"] = {"comment": [{"add": {"body": comment}}]}

        return self._api_request("POST", f"issue/{issue_key}/transitions", data=data)

    def close_issue(self, issue_key: str, comment: str = None) -> Dict[str, Any]:
        """
        Close an issue (convenience method).

        Note: This finds the "Done" or "Closed" transition automatically.
        """
        transitions_result = self.get_transitions(issue_key)
        if transitions_result["status"] != "success":
            return transitions_result

        transitions = transitions_result["data"].get("transitions", [])
        close_transition = None

        for t in transitions:
            name = t.get("name", "").lower()
            if name in ["done", "closed", "close", "resolve"]:
                close_transition = t
                break

        if not close_transition:
            return {
                "status": "error",
                "message": "No close/done transition found",
                "available_transitions": [t["name"] for t in transitions]
            }

        return self.transition_issue(issue_key, close_transition["id"], comment=comment)

    # ==================== Comments ====================

    def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        """Add a comment to an issue."""
        if self.config.is_cloud:
            data = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": comment}]
                        }
                    ]
                }
            }
        else:
            data = {"body": comment}

        return self._api_request("POST", f"issue/{issue_key}/comment", data=data)

    def get_comments(self, issue_key: str) -> Dict[str, Any]:
        """Get all comments on an issue."""
        return self._api_request("GET", f"issue/{issue_key}/comment")

    # ==================== Attachments ====================

    def add_attachment(self, issue_key: str, file_path: str, filename: str = None) -> Dict[str, Any]:
        """
        Add an attachment to an issue.

        Args:
            issue_key: Issue key
            file_path: Local path to file
            filename: Name for the attachment (uses file basename if not provided)
        """
        import os
        if not filename:
            filename = os.path.basename(file_path)

        with open(file_path, 'rb') as f:
            files = {"file": (filename, f)}
            return self._api_request(
                "POST",
                f"issue/{issue_key}/attachments",
                files=files
            )

    # ==================== Projects ====================

    def get_projects(self) -> Dict[str, Any]:
        """Get all projects."""
        return self._api_request("GET", "project")

    def get_project(self, project_key: str) -> Dict[str, Any]:
        """Get project details."""
        return self._api_request("GET", f"project/{project_key}")

    # ==================== Users ====================

    def get_current_user(self) -> Dict[str, Any]:
        """Get current authenticated user."""
        return self._api_request("GET", "myself")

    def search_users(self, query: str, max_results: int = 50) -> Dict[str, Any]:
        """Search for users."""
        if self.config.is_cloud:
            return self._api_request(
                "GET",
                "user/search",
                params={"query": query, "maxResults": max_results}
            )
        else:
            return self._api_request(
                "GET",
                "user/search",
                params={"username": query, "maxResults": max_results}
            )

    # ==================== Automation Helper Methods ====================

    def create_incident_issue(
        self,
        project_key: str,
        title: str,
        description: str,
        severity: str,
        source: str = None,
        labels: List[str] = None
    ) -> Dict[str, Any]:
        """
        Create an issue from an automated incident.

        Args:
            project_key: Target project
            title: Incident title
            description: Incident details
            severity: Severity level (critical, high, medium, low)
            source: Source system/host
            labels: Additional labels
        """
        # Map severity to priority
        priority_map = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low"
        }
        priority = priority_map.get(severity.lower(), "Medium")

        # Build description
        full_description = f"""
*Automated Incident Report*

*Severity:* {severity}
*Source:* {source or 'Unknown'}
*Time:* {datetime.now().isoformat()}

----

{description}
"""

        # Build labels
        issue_labels = ["automated", "incident", severity.lower()]
        if labels:
            issue_labels.extend(labels)

        return self.create_issue(
            project_key=project_key,
            summary=f"[{severity.upper()}] {title}",
            issue_type="Bug",  # Or custom incident type
            description=full_description,
            priority=priority,
            labels=issue_labels
        )

    def log_automation_action(
        self,
        issue_key: str,
        action: str,
        result: str,
        details: str = None
    ) -> Dict[str, Any]:
        """
        Log an automation action as a comment.

        Args:
            issue_key: Issue to update
            action: Action performed
            result: Result (success/failure)
            details: Additional details
        """
        comment = f"""
*Automation Log*

| Field | Value |
|-------|-------|
| Time | {datetime.now().isoformat()} |
| Action | {action} |
| Result | {result} |
{f"| Details | {details} |" if details else ""}
"""
        return self.add_comment(issue_key, comment)
