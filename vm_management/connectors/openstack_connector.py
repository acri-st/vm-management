"""OpenStack connector for managing connections to OpenStack API"""

import asyncio
from typing import Annotated, Optional

import openstack
from fastapi import Depends
from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from pydantic import BaseModel, field_validator

logger = get_logger("application")


class OpenStackCredentialsConfig(BaseModel):
    """Configuration model for OpenStack credentials"""

    auth_url: str
    identity_api_version: str
    username: str
    password: str
    tenant_name: str
    tenant_id: str
    region_name: str
    user_domain_name: str = "Default"
    project_domain_name: str = "Default"

    @field_validator("tenant_name", "identity_api_version", mode="before")
    @classmethod
    def convert_to_string(cls, v):
        """Convert numeric values to strings"""
        return str(v)


class OpenStackConnector:
    """Manages connections to OpenStack API"""

    _instance: Optional["OpenStackConnector"] = None
    _connection_timeout: int = 10
    _last_health_check: float = 0
    _health_check_interval: int = 60 * 10
    _lock = asyncio.Lock()

    def __init__(
        self,
        auth_url: str,
        identity_api_version: str,
        username: str,
        password: str,
        tenant_name: str,
        tenant_id: str,
        region_name: str,
        user_domain_name: str = "Default",
        project_domain_name: str = "Default",
    ):
        self.connection_params = {
            "auth_url": auth_url,
            "identity_api_version": identity_api_version,
            "username": username,
            "password": password,
            "tenant_name": tenant_name,
            "tenant_id": tenant_id,
            "region_name": region_name,
            "user_domain_name": user_domain_name,
            "project_domain_name": project_domain_name,
            "timeout": self._connection_timeout,
        }
        self.conn: openstack.connection.Connection | None = None

    async def connect(self) -> None:
        """Establish connection to OpenStack"""
        logger.info("Establishing OpenStack connection")
        try:
            async with self._lock:
                if not hasattr(self, "conn") or self.conn is None:
                    self.conn = openstack.connect(**self.connection_params)
                    logger.info("OpenStack Connection established to %s", self.connection_params["auth_url"])
        except Exception as e:
            logger.error("OpenStack Connection failed - error=%s", str(e))
            raise e

    def reset_connection(self):
        """Reset the connection"""
        self.conn = None


def get_openstack_config() -> OpenStackCredentialsConfig:
    """Get OpenStack configuration from config file"""
    config = read_config().get("ovh_openstack")
    return OpenStackCredentialsConfig(**config)


async def get_openstack_connector(
    openstack_config: Annotated[OpenStackCredentialsConfig, Depends(get_openstack_config)],
) -> OpenStackConnector:
    """Get OpenStack connector instance"""
    if not OpenStackConnector._instance:
        OpenStackConnector._instance = OpenStackConnector(
            auth_url=openstack_config.auth_url,
            identity_api_version=openstack_config.identity_api_version,
            username=openstack_config.username,
            password=openstack_config.password,
            tenant_name=openstack_config.tenant_name,
            tenant_id=openstack_config.tenant_id,
            region_name=openstack_config.region_name,
            user_domain_name=openstack_config.user_domain_name,
            project_domain_name=openstack_config.project_domain_name,
        )

    await OpenStackConnector._instance.connect()
    return OpenStackConnector._instance
