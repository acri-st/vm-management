"""exceptions"""

from msfwk.exceptions import BaseError
from vm_management.constants import (
    DATABASE_ERROR,
    DB_PROFILE_NOT_FOUND_ERROR,
    DB_SERVER_NOT_FOUND_ERROR,
    INFRASTRUCTURE_ERROR,
    OPENSTACK_SERVER_NOT_FOUND_ERROR,
    PROJECT_NOT_FOUND_ERROR,
    PROJECT_SERVICE_ERROR,
    PROMETHEUS_ERROR,
    SERVER_INVALID_STATE_ERROR,
    SERVER_OPERATION_ERROR,
    SERVER_PERMISSION_ERROR,
)


class ServerManagementError(BaseError):
    """Base exception for all SERVER Management errors"""

    def __init__(
        self, message: str | None = None, code: int = SERVER_OPERATION_ERROR, server_id: str | None = None
    ) -> None:
        self.code = code
        self.message = message or "SERVER operation failed"
        self.server_id = server_id
        super().__init__(code, self.message)


class OpenStackServerNotFoundError(ServerManagementError):
    """Exception for OpenStack server not found errors"""

    def __init__(self, server_id: str | None = None) -> None:
        message = f"OpenStack server {server_id} not found" if server_id else "OpenStack server not found"
        super().__init__(message, OPENSTACK_SERVER_NOT_FOUND_ERROR, server_id)


class DbServerNotFoundError(ServerManagementError):
    """Exception for database server not found errors"""

    def __init__(self, server_id: str | None = None) -> None:
        message = f"Database server {server_id} not found" if server_id else "Database server not found"
        super().__init__(message, DB_SERVER_NOT_FOUND_ERROR, server_id)


class DbProfileNotFoundError(ServerManagementError):
    """Exception for database profile not found errors"""

    def __init__(self, username: str | None = None) -> None:
        message = f"Database profile {username} not found" if username else "Database profile not found"
        super().__init__(message, DB_PROFILE_NOT_FOUND_ERROR, username)


class ProjectNotFoundError(ServerManagementError):
    """Exception for project not found errors"""

    def __init__(self, project_id: str | None = None) -> None:
        message = f"Project {project_id} not found" if project_id else "Project not found"
        super().__init__(message, PROJECT_NOT_FOUND_ERROR, project_id)


class ServerInvalidStateError(ServerManagementError):
    """Exception for SERVER in invalid state for requested operation"""

    def __init__(
        self, server_id: str | None = None, current_state: str | None = None, required_states: list[str] | None = None
    ) -> None:
        states_msg = f", required states: {', '.join(required_states)}" if required_states else ""
        state_msg = f", current state: {current_state}" if current_state else ""
        message = f"SERVER {server_id} in invalid state for operation{state_msg}{states_msg}"
        super().__init__(message, SERVER_INVALID_STATE_ERROR, server_id)


class ServerPermissionError(ServerManagementError):
    """Exception for permission errors on SERVER operations"""

    def __init__(self, server_id: str | None = None) -> None:
        message = (
            f"Not authorized to perform operation on SERVER {server_id}"
            if server_id
            else "Not authorized to perform SERVER operation"
        )
        super().__init__(message, SERVER_PERMISSION_ERROR, server_id)


class DatabaseError(ServerManagementError):
    """Exception for database errors"""

    def __init__(self, message: str | None = None, server_id: str | None = None) -> None:
        message = message or "Database operation failed"
        super().__init__(message, DATABASE_ERROR, server_id)


class InfrastructureError(ServerManagementError):
    """Exception for infrastructure errors (Terraform, Ansible, K8s)"""

    def __init__(self, message: str | None = None, server_id: str | None = None) -> None:
        message = message or "Infrastructure operation failed"
        super().__init__(message, INFRASTRUCTURE_ERROR, server_id)


class ProjectServiceError(ServerManagementError):
    """Exception for project service errors"""

    def __init__(self, message: str | None = None, server_id: str | None = None) -> None:
        message = message or "Project service operation failed"
        super().__init__(message, PROJECT_SERVICE_ERROR, server_id)


class PrometheusError(ServerManagementError):
    """Exception for Prometheus errors"""

    def __init__(self, message: str | None = None, server_id: str | None = None) -> None:
        message = message or "Prometheus operation failed"
        super().__init__(message, PROMETHEUS_ERROR, server_id)
