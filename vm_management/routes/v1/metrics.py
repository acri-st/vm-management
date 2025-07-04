"""API endpoints for Prometheus metrics"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from msfwk.application import openapi_extra
from msfwk.models import BaseDespResponse, DespResponse
from msfwk.utils.logging import get_logger

from vm_management.routes.error_handling import handle_server_exception
from vm_management.services import PrometheusService, SandboxDBService, get_prometheus_service, get_sandbox_db_service

logger = get_logger("application")
router = APIRouter(prefix="/metrics", tags=["metrics"])

time_range_description = "Time range in seconds (default: 1 hour)"


@router.get(
    "/resources/{server_id}/cpu",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Get CPU usage for a server",
    openapi_extra=openapi_extra(secured=True, internal=False),
)
async def get_cpu_usage(
    server_id: str,
    prometheus_service: Annotated[PrometheusService, Depends(get_prometheus_service)],
    sandbox_db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    time_range: int = Query(3600, description=time_range_description),
) -> DespResponse:
    """Get CPU usage for a server

    Args:
        server_id: Server ID
        prometheus_service: Prometheus service instance
        sandbox_db_service: Sandbox DB service instance
        time_range: Time range in seconds (default: 1 hour)

    Returns:
        DespResponse: Dict containing CPU usage data or error response
    """
    logger.info("Fetching CPU metrics for server_id=%s", server_id)

    try:
        server = await sandbox_db_service.get_server_by_id(server_id)
        cpu_data = await prometheus_service.get_cpu_usage(
            openstack_server_id=server.openstack_server_id, time_range=time_range
        )
        return DespResponse(data=cpu_data)
    except Exception as e:
        return handle_server_exception(e, "CPU metrics")


@router.get(
    "/resources/{server_id}/memory",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Get memory usage for a server",
    openapi_extra=openapi_extra(secured=True, internal=False),
)
async def get_memory_usage(
    server_id: str,
    prometheus_service: Annotated[PrometheusService, Depends(get_prometheus_service)],
    sandbox_db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    time_range: int = Query(3600, description=time_range_description),
) -> DespResponse:
    """Get memory usage for a server

    Args:
        server_id: OpenStack server ID
        prometheus_service: Prometheus service instance
        sandbox_db_service: Sandbox DB service instance
        time_range: Time range in seconds (default: 1 hour)

    Returns:
        DespResponse: Dict containing memory usage data or error response
    """
    logger.info("Fetching memory metrics for server_id=%s", server_id)
    try:
        server = await sandbox_db_service.get_server_by_id(server_id)
        memory_data = await prometheus_service.get_memory_usage(
            openstack_server_id=server.openstack_server_id, time_range=time_range
        )
        return DespResponse(data=memory_data)
    except Exception as e:
        return handle_server_exception(e, "memory metrics")


@router.get(
    "/resources/{server_id}/disk",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Get disk usage for a server",
    openapi_extra=openapi_extra(secured=True, internal=False),
)
async def get_disk_usage(
    server_id: str,
    prometheus_service: Annotated[PrometheusService, Depends(get_prometheus_service)],
    sandbox_db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    time_range: int = Query(3600, description=time_range_description),
) -> DespResponse:
    """Get disk usage for a server

    Args:
        server_id: OpenStack server ID
        prometheus_service: Prometheus service instance
        sandbox_db_service: Sandbox DB service instance
        time_range: Time range in seconds (default: 1 hour)

    Returns:
        DespResponse: Dict containing disk usage data or error response
    """
    logger.info("Fetching disk metrics for server_id=%s", server_id)
    try:
        server = await sandbox_db_service.get_server_by_id(server_id)
        disk_data = await prometheus_service.get_disk_usage(
            openstack_server_id=server.openstack_server_id, time_range=time_range
        )
        return DespResponse(data=disk_data)
    except Exception as e:
        return handle_server_exception(e, "disk metrics")


@router.get(
    "/resources/{server_id}/network",
    response_model=BaseDespResponse[dict[str, Any]],
    summary="Get network traffic for a server",
    openapi_extra=openapi_extra(secured=True, internal=False),
)
async def get_network_traffic(
    server_id: str,
    prometheus_service: Annotated[PrometheusService, Depends(get_prometheus_service)],
    sandbox_db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    time_range: int = Query(3600, description=time_range_description),
) -> DespResponse:
    """Get network traffic for a server

    Args:
        server_id: OpenStack server ID
        prometheus_service: Prometheus service instance
        sandbox_db_service: Sandbox DB service instance
        time_range: Time range in seconds (default: 1 hour)

    Returns:
        DespResponse: Dict containing network traffic data or error response
    """
    logger.info("Fetching network metrics for server_id=%s", server_id)
    try:
        server = await sandbox_db_service.get_server_by_id(server_id)
        network_data = await prometheus_service.get_network_traffic(
            openstack_server_id=server.openstack_server_id, time_range=time_range
        )
        return DespResponse(data=network_data)
    except Exception as e:
        return handle_server_exception(e, "network metrics")
