"""Guacamole routes for VM management"""

from typing import Annotated

from fastapi import APIRouter, Depends
from msfwk.models import BaseDespResponse, DespResponse
from msfwk.utils.logging import get_logger

from vm_management.services.guacamole_service import GuacamoleConfig, get_guacamole_config

logger = get_logger("application")
router = APIRouter(prefix="/guacamole", tags=["guacamole"])


@router.get("/base-url", response_model=BaseDespResponse[dict[str, str]])
async def get_base_url(config: Annotated[GuacamoleConfig, Depends(get_guacamole_config)]):
    """Get Guacamole base URL"""
    return DespResponse(
        data={"data": {"base_url": config.base_url}},
        http_status=200,
    )
