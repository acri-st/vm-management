"""Routes for server operations involving both database and OpenStack"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from msfwk.application import openapi_extra
from msfwk.context import current_config
from msfwk.desp.serco_logs.models import ActiveUserLog, EventType
from msfwk.desp.serco_logs.notify import send_logs_using_config
from msfwk.models import BaseDespResponse, DespResponse
from msfwk.notification import NotificationTemplate, send_email_to_mq
from msfwk.utils.logging import get_logger
from msfwk.utils.user import get_current_user

from vm_management.dependencies import get_transaction_id
from vm_management.models.server import DBServerUpdate, ServerCreationPayload
from vm_management.routes.error_handling import handle_server_exception
from vm_management.services.auth_service import get_mail_from_desp_user_id
from vm_management.services.lifecycle_service import LifecycleService, get_lifecycle_service
from vm_management.services.sandbox_db_service import SandboxDBService, get_sandbox_db_service
from vm_management.services.server_service import ServerService, get_server_service
from vm_management.utils import run_with_error_logging

logger = get_logger("application")
router = APIRouter(prefix="/servers", tags=["servers"])


@router.post(
    "",
    summary="Create a server (virtual machine) on a specified environment",
    response_description="The status of the request",
    response_model=BaseDespResponse,
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def create_server(
    server_creation_payload: ServerCreationPayload,
    server_service: Annotated[ServerService, Depends(get_server_service)],
    transaction_id: Annotated[str, Depends(get_transaction_id)],
    background_tasks: BackgroundTasks,
) -> DespResponse:
    """Create a server (virtual machine) on a specified environment"""
    logger.info("Creating server for user: %s", server_creation_payload.username)
    log = ActiveUserLog(event_type=EventType.CREATE_VM, service_name="DESP-AAS-sandbox", user_id=get_current_user().id)
    background_tasks.add_task(send_logs_using_config, current_config.get(), [log])
    try:
        await server_service.create_server(server_creation_payload, transaction_id=transaction_id)
        return DespResponse(
            data={"status": "accepted", "message": f"Server creation initiated for {server_creation_payload.username}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "server creation")


@router.get(
    "/suspended",
    response_model=BaseDespResponse[list[dict[str, Any]]],
    summary="List servers suspended for more than specified days",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def list_suspended_servers(
    days: int,
    db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
) -> DespResponse:
    """List servers that have been suspended for more than the specified number of days

    Args:
        days: Number of days to check against
        db_service: Database service

    Returns:
        DespResponse: List of suspended servers older than specified days
    """
    logger.info("Fetching servers suspended for more than %d days", days)
    try:
        servers = await db_service.get_suspended_servers_older_than(days)
        logger.info("Successfully retrieved %d suspended servers older than %d days", len(servers), days)

        return DespResponse(data=[server.model_dump() for server in servers])
    except Exception as e:
        return handle_server_exception(e, "suspended servers list")


@router.get(
    "/{server_id}",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Get server details by database ID",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def get_server(
    server_id: uuid.UUID, db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)]
) -> DespResponse:
    """Get detailed information about a server using its database ID
    Returns:
        DespResponse: Server details from database or error response
    """
    logger.debug("Fetching details for server with database ID: %s", server_id)
    try:
        # Get server directly from the database
        server = await db_service.get_server_by_id(server_id)

        if not server:
            logger.warning("Server not found in database - server_id=%s", server_id)
            return DespResponse(data={}, error=f"Server with ID {server_id} not found", http_status=404)

        return DespResponse(data=server.model_dump())
    except Exception as e:
        return handle_server_exception(e, "server details")


@router.get(
    "",
    response_model=BaseDespResponse[list[dict[str, Any]]],
    summary="List all servers from database",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def list_servers(
    db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    project_id: str | None = None,
) -> DespResponse:
    """List all available servers with optional filtering from database
    Args:
        project_id: Optional project ID to filter results
    Returns:
        DespResponse: List of servers from database or error response
    """
    logger.info("List Servers - Fetching servers from database with filters: project_id=%s", project_id or "None")
    try:
        if project_id:
            servers = await db_service.get_servers_by_project_id(project_id)
            logger.info("List Servers - Successfully retrieved %d servers for project_id=%s", len(servers), project_id)
        else:
            servers = await db_service.list_all_servers()
            logger.info("List Servers - Successfully retrieved %d servers", len(servers))

        return DespResponse(data=[sever.model_dump() for sever in servers])
    except Exception as e:
        return handle_server_exception(e, "server list")


@router.post(
    "/actions/suspend",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Run action to notify and suspend inactive servers",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def suspend_server(
    background_tasks: BackgroundTasks,
    lifecycle_service: Annotated[LifecycleService, Depends(get_lifecycle_service)],
) -> DespResponse:
    """Run action to notify and suspend inactive servers"""
    logger.info("Run action to notify and suspend inactive servers")

    try:
        # Get detailed server information without performing actions
        servers_to_notify, servers_to_delete = await lifecycle_service.get_servers_to_suspend()

        # Run actual lifecycle checks in background
        background_tasks.add_task(run_with_error_logging, lifecycle_service.run_lifecycle_checks)

        # Return the detailed server information in the response
        return DespResponse(
            data={
                "status": "accepted",
                "message": "Suspend action initiated",
                "servers_to_notify": servers_to_notify,
                "servers_to_delete": servers_to_delete,
                "notify_count": len(servers_to_notify),
                "delete_count": len(servers_to_delete),
            },
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "suspend servers action")


@router.post(
    "/{server_id}/actions/shelve",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Shelve a server and update database",
    openapi_extra=openapi_extra(secured=True),
)
async def shelve_server(
    server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> DespResponse:
    """Initiate server shelving operation in the background and update database

    Args:
        server_id: Database ID of the server to shelve
        background_tasks: FastAPI background tasks handler
        server_service: Server service

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Shelve Operation Queueing shelve operation for server_id=%s", server_id)

    try:
        # Add the shelve task to background tasks
        background_tasks.add_task(run_with_error_logging, server_service.shelve_server, server_id=server_id)

        return DespResponse(
            data={"status": "accepted", "message": f"Server shelving initiated for {server_id}"}, http_status=202
        )
    except Exception as e:
        return handle_server_exception(e, "server shelving")


@router.post(
    "/{server_id}/actions/unshelve",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Unshelve a server and update database",
    openapi_extra=openapi_extra(secured=True),
)
async def unshelve_server(
    server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> DespResponse:
    """Unshelve a server by ID in the background and update database

    Args:
        server_id: Database ID of the server to unshelve
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Unshelve Operation Queueing unshelve operation for server_id=%s", server_id)

    try:
        # Add the unshelve task to background tasks
        background_tasks.add_task(run_with_error_logging, server_service.unshelve_server, server_id=server_id)

        return DespResponse(
            data={"status": "accepted", "message": f"Server unshelving initiated for {server_id}"}, http_status=202
        )
    except Exception as e:
        return handle_server_exception(e, "server unshelving")


@router.post(
    "/{server_id}/actions/reset",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Reset a server and update database",
    openapi_extra=openapi_extra(secured=True),
)
async def reset_server(
    server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
    transaction_id: Annotated[str, Depends(get_transaction_id)],
) -> DespResponse:
    """Reset (rebuild) a server by ID in the background and update database

    Args:
        server_id: Database ID of the server to reset
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Reset Operation Queueing reset operation for server_id=%s", server_id)

    try:
        # Add the reset task to background tasks
        background_tasks.add_task(
            run_with_error_logging, server_service.reset_server, server_id=server_id, transaction_id=transaction_id
        )

        return DespResponse(
            data={"status": "accepted", "message": f"Server reset initiated for {server_id}"}, http_status=202
        )
    except Exception as e:
        return handle_server_exception(e, "server reset")


@router.delete(
    "/{server_id}",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Delete a server and update database",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def delete_server(
    server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> DespResponse:
    """Delete a server by ID in the background and update database

    Args:
        server_id: Database ID of the server to delete
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Delete Operation Queueing delete operation for server_id=%s", server_id)

    try:
        # Add the delete task to background tasks
        background_tasks.add_task(run_with_error_logging, server_service.delete_server, server_id=server_id)

        return DespResponse(
            data={"status": "accepted", "message": f"Server deletion initiated for {server_id}"}, http_status=202
        )
    except Exception as e:
        return handle_server_exception(e, "server deletion")


@router.post(
    "/{server_id}/actions/terraform-complete",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Update server after terraform completion",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def terraform_complete(
    server_id: uuid.UUID,
    server_update: DBServerUpdate,
    server_service: Annotated[ServerService, Depends(get_server_service)],
    transaction_id: Annotated[str, Depends(get_transaction_id)],
) -> DespResponse:
    """Update server details after terraform creation job completes

    Args:
        server_id: Database ID of the server to update
        server_update: Request body containing updated server details (state, public_ip, openstack_server_id)

    Returns:
        DespResponse: Updated server details or error response
    """
    logger.info(
        "Processing terraform completion - server_id=%s, updates=%s",
        server_id,
        server_update.model_dump(exclude_none=True),
    )

    try:
        if not server_update.model_dump(exclude_none=True):
            logger.warning("No valid updates provided - server_id=%s", server_id)
            return DespResponse(data={}, error="No valid updates provided", http_status=400)

        await server_service.terraform_complete(server_id, server_update, transaction_id)

        logger.info(" Server updated successfully - server_id=%s", server_id)
        return DespResponse(
            data={"status": "accepted", "message": f"Server terraform completion initiated for {server_id}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "server terraform completion")


@router.post(
    "/{server_id}/actions/run-ansible",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Install application on a server",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def run_ansible(
    server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
    transaction_id: Annotated[str, Depends(get_transaction_id)],
) -> DespResponse:
    """Run Ansible to configure server by ID in the background

    Args:
        server_id: Database ID of the server
        transaction_id: Transaction ID of the request
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Queueing ansible run for server_id=%s", server_id)

    try:
        # Add the installation task to background tasks
        background_tasks.add_task(
            run_with_error_logging,
            server_service.configure_server_with_ansible,
            server_id=server_id,
            transaction_id=transaction_id,
        )

        return DespResponse(
            data={"status": "accepted", "message": f"Ansible run initiated for {server_id}"}, http_status=202
        )
    except Exception as e:
        return handle_server_exception(e, "server ansible run")


@router.post(
    "/{server_id}/actions/ansible-complete",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Update server after ansible completion",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def ansible_complete(
    server_id: uuid.UUID,
    server_update: DBServerUpdate,
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> DespResponse:
    """Update server details after ansible configuration job completes

    Args:
        server_id: Database ID of the server to update
        server_update: Request body containing updated server status (READY or ERROR)

    Returns:
        DespResponse: Updated server details or error response
    """
    logger.info(
        "Processing ansible completion - server_id=%s, updates=%s",
        server_id,
        server_update.model_dump(exclude_none=True),
    )

    try:
        if not server_update.model_dump(exclude_none=True):
            logger.warning("No valid updates provided - server_id=%s", server_id)
            return DespResponse(data={}, error="No valid updates provided", http_status=400)

        db_server = await server_service.ansible_complete(server_id, server_update)

        logger.info("Server updated successfully - server_id=%s", server_id)
        logger.info("Preparing to send email")

        db_project = await server_service.project_service.get_project_by_id(db_server.project_id)
        db_profile = await server_service.project_service.get_profile_by_id(db_project["profile"]["id"])
        mail = await get_mail_from_desp_user_id(db_profile["desp_owner_id"])

        await send_email_to_mq(
            notification_type=NotificationTemplate.GENERIC,
            user_email=mail,
            subject="Vm creation finished",
            message=f"Vm creation finished for project {db_project['name']}",
            user_id=db_profile["desp_owner_id"],
        )

        return DespResponse(
            data={"status": "accepted", "message": f"Server ansible completion processed for {server_id}"},
            http_status=200,
        )
    except Exception as e:
        return handle_server_exception(e, "server ansible completion")
