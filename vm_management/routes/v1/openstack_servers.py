"""Routes for OpenStack-only server operations"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from msfwk.application import openapi_extra
from msfwk.models import BaseDespResponse, DespResponse
from msfwk.utils.logging import get_logger

from vm_management import models
from vm_management.models.alerts import AlertWebhookPayload
from vm_management.routes.error_handling import handle_server_exception
from vm_management.services import OpenStackServerService, get_openstack_server_service
from vm_management.services.server_service import ServerService, get_server_service
from vm_management.utils import run_with_error_logging

router = APIRouter(prefix="/openstack-servers", tags=["openstack-servers"])
logger = get_logger("application")


@router.get(
    "/{openstack_server_id}",
    response_model=BaseDespResponse[models.OpenStackServerRead],
    summary="Get OpenStack server details by ID",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def get_openstack_server(
    openstack_server_id: uuid.UUID,
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
) -> DespResponse:
    """Get detailed information about an OpenStack server using its ID
    Returns:
        DespResponse: Server details or error response
    """
    logger.debug("Fetching details for OpenStack server ID: %s", openstack_server_id)
    try:
        server = await openstack_service.get_server_by_id(openstack_server_id)
        return DespResponse(data=server.model_dump())
    except Exception as e:
        return handle_server_exception(e, "get_openstack_server", openstack_server_id)


@router.get(
    "",
    response_model=BaseDespResponse[list[models.OpenStackServerRead]],
    summary="List all OpenStack servers",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def list_openstack_servers(
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
    name: str | None = None,
) -> DespResponse:
    """List all available OpenStack servers with optional filtering
    Args:
        name: Optional server name to filter results
    Returns:
        DespResponse: List of servers or error response
    """
    logger.info("[List OpenStack Servers] Fetching servers with filters: name=%s", name or "None")
    try:
        if name:
            servers = await openstack_service.get_servers_by_name(name)
        else:
            servers = await openstack_service.list_servers()

        logger.info("[List OpenStack Servers] Successfully retrieved %d servers", len(servers))
        return DespResponse(data=[server.model_dump() for server in servers])
    except Exception as e:
        return handle_server_exception(e, "list_openstack_servers", name)


@router.post(
    "/{openstack_server_id}/actions/shelve",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Shelve an OpenStack server",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def shelve_openstack_server(
    openstack_server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
) -> DespResponse:
    """Initiate OpenStack server shelving operation in the background

    Args:
        openstack_server_id: ID of the OpenStack server to shelve
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("[Shelve Operation] Queueing shelve operation for OpenStack server_id=%s", openstack_server_id)

    try:
        # Add the shelve task to background tasks
        background_tasks.add_task(
            run_with_error_logging, openstack_service.shelve_server, server_id=openstack_server_id
        )

        return DespResponse(
            data={"status": "accepted", "message": f"OpenStack server shelving initiated for {openstack_server_id}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "shelve_openstack_server", openstack_server_id)


@router.post(
    "/{openstack_server_id}/actions/unshelve",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Unshelve an OpenStack server",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def unshelve_openstack_server(
    openstack_server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
) -> DespResponse:
    """Unshelve an OpenStack server by ID in the background

    Args:
        openstack_server_id: ID of the OpenStack server to unshelve
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("[Unshelve Operation] Queueing unshelve operation for OpenStack server_id=%s", openstack_server_id)

    try:
        # Add the unshelve task to background tasks
        background_tasks.add_task(
            run_with_error_logging, openstack_service.unshelve_server, server_id=openstack_server_id
        )

        return DespResponse(
            data={"status": "accepted", "message": f"OpenStack server unshelving initiated for {openstack_server_id}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "unshelve_openstack_server", openstack_server_id)


@router.post(
    "/{openstack_server_id}/actions/reset",
    response_model=BaseDespResponse[dict[str, str]],
    summary="Reset an OpenStack server",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def reset_openstack_server(
    openstack_server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
) -> DespResponse:
    """Reset (rebuild) an OpenStack server by ID in the background

    Args:
        openstack_server_id: ID of the OpenStack server to reset
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Reset Operation Queueing reset operation for OpenStack server_id=%s", openstack_server_id)

    try:
        # Add the reset task to background tasks
        background_tasks.add_task(run_with_error_logging, openstack_service.reset_server, server_id=openstack_server_id)

        return DespResponse(
            data={"status": "accepted", "message": f"OpenStack server reset initiated for {openstack_server_id}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "reset_openstack_server", openstack_server_id)


@router.delete(
    "/{openstack_server_id}",
    response_model=BaseDespResponse[dict],
    summary="Delete an OpenStack server",
    openapi_extra=openapi_extra(secured=True, internal=True),
)
async def delete_openstack_server(
    openstack_server_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
) -> DespResponse:
    """Delete an OpenStack server by ID in the background

    Args:
        openstack_server_id: ID of the OpenStack server to delete
        background_tasks: FastAPI background tasks handler

    Returns:
        DespResponse: Immediate response with accepted status
    """
    logger.info("Delete Operation Queueing delete operation for OpenStack server_id=%s", openstack_server_id)

    try:
        # Add the delete task to background tasks
        background_tasks.add_task(
            run_with_error_logging, openstack_service.delete_server, server_id=openstack_server_id
        )

        return DespResponse(
            data={"status": "accepted", "message": f"OpenStack server deletion initiated for {openstack_server_id}"},
            http_status=202,
        )
    except Exception as e:
        return handle_server_exception(e, "delete_openstack_server", openstack_server_id)


@router.post(
    "/alerts/shelve-inactive",
    summary="Shelve inactive OpenStack servers triggered by alerts",
    openapi_extra=openapi_extra(secured=False, internal=True),
)
async def shelve_inactive_openstack_servers(
    payload: AlertWebhookPayload,
    background_tasks: BackgroundTasks,
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> DespResponse:
    """Handle inactivity alerts and shelve inactive OpenStack servers in background"""
    instance_ids = [uuid.UUID(alert.labels.instance_id) for alert in payload.alerts]
    logger.info(
        "Inactivity Alert Received webhook to shelve %d inactive OpenStack servers: %s",
        len(instance_ids),
        ", ".join(str(id) for id in instance_ids),
    )

    # Process all servers in the background
    background_tasks.add_task(run_with_error_logging, server_service.shelve_openstack_servers, openstack_server_ids=instance_ids)

    return DespResponse(
        data={"message": f"Processing shelve requests for {len(instance_ids)} OpenStack servers"}, http_status=200
    )
