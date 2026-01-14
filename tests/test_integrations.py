"""
Tests for ITSM integrations.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestServiceNowIntegration:
    """Tests for ServiceNow integration."""

    def test_servicenow_config_creation(self):
        """Test ServiceNowConfig dataclass."""
        from onprem_automation.integrations.servicenow import ServiceNowConfig

        config = ServiceNowConfig(
            instance="dev12345",
            username="admin",
            password="secret"
        )
        assert config.instance == "dev12345"
        assert config.timeout == 30

    def test_servicenow_config_defaults(self):
        """Test ServiceNowConfig default values."""
        from onprem_automation.integrations.servicenow import ServiceNowConfig

        config = ServiceNowConfig(
            instance="test",
            username="user",
            password="pass"
        )
        assert config.timeout == 30

    @patch('onprem_automation.integrations.servicenow.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.servicenow.requests')
    def test_servicenow_client_init(self, mock_requests):
        """Test ServiceNow client initialization."""
        from onprem_automation.integrations.servicenow import (
            ServiceNowConfig,
            ServiceNowClient
        )

        config = ServiceNowConfig(
            instance="dev12345",
            username="admin",
            password="secret"
        )

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        client = ServiceNowClient(config)
        assert client.config == config
        assert "dev12345.service-now.com" in client._base_url

    @patch('onprem_automation.integrations.servicenow.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.servicenow.requests')
    def test_servicenow_connection_error(self, mock_requests):
        """Test ServiceNow handles connection errors."""
        from onprem_automation.integrations.servicenow import (
            ServiceNowConfig,
            ServiceNowClient
        )

        config = ServiceNowConfig(
            instance="dev12345",
            username="admin",
            password="secret"
        )

        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection refused")
        mock_requests.Session.return_value = mock_session

        client = ServiceNowClient(config)
        result = client.health_check()

        assert result["status"] == "unhealthy"


class TestJiraIntegration:
    """Tests for Jira integration."""

    def test_jira_config_creation(self):
        """Test JiraConfig dataclass."""
        from onprem_automation.integrations.jira_client import JiraConfig

        config = JiraConfig(
            url="https://myorg.atlassian.net",
            username="user@example.com",
            api_token="secret"
        )
        assert config.url == "https://myorg.atlassian.net"
        assert config.is_cloud is True

    def test_jira_config_server(self):
        """Test JiraConfig for Jira Server."""
        from onprem_automation.integrations.jira_client import JiraConfig

        config = JiraConfig(
            url="https://jira.mycompany.com",
            username="admin",
            api_token="password",
            is_cloud=False
        )
        assert config.is_cloud is False

    @patch('onprem_automation.integrations.jira_client.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.jira_client.requests')
    def test_jira_health_check(self, mock_requests):
        """Test Jira health check."""
        from onprem_automation.integrations.jira_client import (
            JiraConfig,
            JiraClient
        )

        config = JiraConfig(
            url="https://myorg.atlassian.net",
            username="user@example.com",
            api_token="secret"
        )

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "displayName": "Test User",
            "emailAddress": "test@example.com"
        }
        mock_session.request.return_value = mock_response
        mock_requests.Session.return_value = mock_session

        client = JiraClient(config)
        result = client.health_check()

        assert result["status"] == "healthy"


class TestPagerDutyIntegration:
    """Tests for PagerDuty integration."""

    def test_pagerduty_config_creation(self):
        """Test PagerDutyConfig dataclass."""
        from onprem_automation.integrations.pagerduty import PagerDutyConfig

        config = PagerDutyConfig(
            api_key="token123"
        )
        assert config.api_key == "token123"
        assert config.timeout == 30
        assert config.region == "us"

    def test_pagerduty_config_eu_region(self):
        """Test PagerDutyConfig for EU region."""
        from onprem_automation.integrations.pagerduty import PagerDutyConfig

        config = PagerDutyConfig(
            api_key="token123",
            region="eu"
        )
        assert config.region == "eu"

    def test_pagerduty_config_with_integration_key(self):
        """Test PagerDutyConfig with integration key."""
        from onprem_automation.integrations.pagerduty import PagerDutyConfig

        config = PagerDutyConfig(
            api_key="api_key_123",
            integration_key="routing_key_456"
        )
        assert config.api_key == "api_key_123"
        assert config.integration_key == "routing_key_456"

    @patch('onprem_automation.integrations.pagerduty.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.pagerduty.requests')
    def test_pagerduty_client_init(self, mock_requests):
        """Test PagerDuty client initialization."""
        from onprem_automation.integrations.pagerduty import (
            PagerDutyConfig,
            PagerDutyClient
        )

        config = PagerDutyConfig(api_key="token123")

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        client = PagerDutyClient(config)
        assert client.config == config
        assert "api.pagerduty.com" in client._api_url

    @patch('onprem_automation.integrations.pagerduty.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.pagerduty.requests')
    def test_pagerduty_eu_urls(self, mock_requests):
        """Test PagerDuty EU region URLs."""
        from onprem_automation.integrations.pagerduty import (
            PagerDutyConfig,
            PagerDutyClient
        )

        config = PagerDutyConfig(api_key="token123", region="eu")

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        client = PagerDutyClient(config)
        assert "api.eu.pagerduty.com" in client._api_url
        assert "events.eu.pagerduty.com" in client._events_url

    @patch('onprem_automation.integrations.pagerduty.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.pagerduty.requests')
    def test_pagerduty_health_check(self, mock_requests):
        """Test PagerDuty health check."""
        from onprem_automation.integrations.pagerduty import (
            PagerDutyConfig,
            PagerDutyClient
        )

        config = PagerDutyConfig(api_key="token123")

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"abilities": ["sso", "webhooks"]}'
        mock_response.json.return_value = {"abilities": ["sso", "webhooks"]}
        mock_session.request.return_value = mock_response
        mock_requests.Session.return_value = mock_session

        client = PagerDutyClient(config)
        result = client.health_check()

        assert result["status"] == "healthy"

    @patch('onprem_automation.integrations.pagerduty.REQUESTS_AVAILABLE', True)
    @patch('onprem_automation.integrations.pagerduty.requests')
    def test_pagerduty_rate_limit_handling(self, mock_requests):
        """Test PagerDuty handles rate limiting."""
        from onprem_automation.integrations.pagerduty import (
            PagerDutyConfig,
            PagerDutyClient
        )

        config = PagerDutyConfig(api_key="token123")

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_session.request.return_value = mock_response
        mock_requests.Session.return_value = mock_session

        client = PagerDutyClient(config)
        result = client._api_request("GET", "test")

        assert result["status"] == "error"
        assert "Rate limited" in result["message"]


class TestIntegrationImports:
    """Tests for integration module imports."""

    def test_integrations_package_imports(self):
        """Test that integrations package exports correct symbols."""
        from onprem_automation.integrations import (
            ServiceNowConfig,
            ServiceNowClient,
            JiraConfig,
            JiraClient,
            PagerDutyConfig,
            PagerDutyClient
        )

        # All should be importable
        assert ServiceNowConfig is not None
        assert ServiceNowClient is not None
        assert JiraConfig is not None
        assert JiraClient is not None
        assert PagerDutyConfig is not None
        assert PagerDutyClient is not None

    def test_servicenow_module_exports(self):
        """Test ServiceNow module exports."""
        from onprem_automation.integrations.servicenow import (
            ServiceNowConfig,
            ServiceNowClient
        )
        assert ServiceNowConfig is not None
        assert ServiceNowClient is not None

    def test_jira_module_exports(self):
        """Test Jira module exports."""
        from onprem_automation.integrations.jira_client import (
            JiraConfig,
            JiraClient
        )
        assert JiraConfig is not None
        assert JiraClient is not None

    def test_pagerduty_module_exports(self):
        """Test PagerDuty module exports."""
        from onprem_automation.integrations.pagerduty import (
            PagerDutyConfig,
            PagerDutyClient
        )
        assert PagerDutyConfig is not None
        assert PagerDutyClient is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
