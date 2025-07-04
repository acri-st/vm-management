"""Error handling for the VM management service"""

from uuid import UUID

import aiohttp
from msfwk.models import DespResponse
from msfwk.utils.logging import get_logger
from sqlalchemy.exc import SQLAlchemyError

from vm_management.constants import CONNECTION_ERROR, DATABASE_ERROR, SERVER_OPERATION_ERROR
from vm_management.exceptions import (
    DatabaseError,
    DbServerNotFoundError,
    InfrastructureError,
    OpenStackServerNotFoundError,
    ProjectNotFoundError,
    ProjectServiceError,
    PrometheusError,
    ServerInvalidStateError,
    ServerManagementError,
    ServerPermissionError,
)

logger = get_logger("application")


def handle_server_exception(e: Exception, operation: str, server_id: UUID | None = None) -> DespResponse:  # noqa: PLR0911
    """Handle server management exceptions and return appropriate DespResponse

    Args:
        e: The exception to handle
        operation: Description of the operation being performed
        server_id: Optional server ID for logging

    Returns:
        DespResponse with appropriate error details
    """
    server_info = f" for server {server_id}" if server_id else ""

    if isinstance(e, OpenStackServerNotFoundError | DbServerNotFoundError):
        return DespResponse(data={}, error=str(e), code=e.code, http_status=404)
    if isinstance(e, ProjectNotFoundError):
        return DespResponse(data={}, error=str(e), code=e.code, http_status=404)
    if isinstance(e, ServerInvalidStateError):
        return DespResponse(data={}, error=str(e), code=e.code, http_status=400)
    if isinstance(e, ServerPermissionError):
        return DespResponse(data={}, error=str(e), code=e.code, http_status=403)
    if isinstance(
        e, DatabaseError | InfrastructureError | ProjectServiceError | ServerManagementError | PrometheusError
    ):
        return DespResponse(data={}, error=str(e), code=e.code, http_status=500)
    if isinstance(e, SQLAlchemyError):
        logger.error("Database error during %s%s: %s", operation, server_info, str(e))
        return DespResponse(
            data={}, error=f"Database error during {operation}{server_info}", code=DATABASE_ERROR, http_status=500
        )
    if isinstance(e, aiohttp.ClientError):
        logger.error("Connection error during %s%s: %s", operation, server_info, str(e))
        return DespResponse(
            data={}, error=f"Connection error during {operation}{server_info}", code=CONNECTION_ERROR, http_status=503
        )
    logger.exception("Unexpected error during %s%s", operation, server_info)
    return DespResponse(
        data={},
        error=f"Unexpected error during {operation}{server_info}",
        code=SERVER_OPERATION_ERROR,
        http_status=500,
    )
