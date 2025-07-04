"""Models for servers"""

import datetime
import enum
import uuid
from typing import Any

from despsharedlibrary.schemas.sandbox_schema import Servers, ServerStatus
from msfwk.models import BaseModelAdjusted
from pydantic import BaseModel, Field


class OpenStackServerStatus(enum.Enum):
    """Enum class to represent the status of an openstack server"""

    ACTIVE = "ACTIVE"
    SHELVED_OFFLOADED = "SHELVED_OFFLOADED"
    SHELVED = "SHELVED"
    SHUTOFF = "SHUTOFF"
    PAUSED = "PAUSED"
    SUSPENDED = "SUSPENDED"
    ERROR = "ERROR"


class OpenStackServerRead(BaseModelAdjusted):
    """Class to represent an openstack server"""

    id: uuid.UUID
    name: str
    status: str
    project_id: str
    user_id: str
    created_at: str
    updated_at: str
    flavor: dict[str, Any]
    addresses: dict[str, Any]
    metadata: dict[str, Any] = {}
    description: str | None = None
    tags: list[str] = []
    vm_state: str | None = None
    task_state: str | None = None
    power_state: int | None = None
    launched_at: str | None = None
    terminated_at: str | None = None
    attached_volumes: list[dict[str, Any]] = []
    key_name: str | None = None
    security_groups: list[dict[str, Any]] = []
    access_ipv4: str | None = None

    @classmethod
    def from_openstack_server(cls, server) -> "OpenStackServerRead":
        """Create a Server instance from an openstack server object"""
        return cls(
            id=server.id,
            name=server.name,
            status=server.status,
            project_id=server.project_id,
            user_id=server.user_id,
            created_at=server.created_at,
            updated_at=server.updated_at,
            flavor=server.flavor,
            addresses=server.addresses,
            metadata=server.metadata if server.metadata else {},
            description=server.description,
            tags=server.tags if server.tags else [],
            vm_state=server.vm_state,
            task_state=server.task_state,
            power_state=server.power_state,
            launched_at=server.launched_at,
            terminated_at=server.terminated_at,
            attached_volumes=server.attached_volumes if server.attached_volumes else [],
            key_name=server.key_name,
            security_groups=server.security_groups if server.security_groups else [],
            access_ipv4=server.access_ipv4,
        )


class DBServerRead(BaseModelAdjusted):
    """Class to represent a server in the database"""

    id: uuid.UUID
    public_ip: str | None
    state: ServerStatus | None
    created_at: datetime.datetime | None
    updated_at: datetime.datetime | None
    openstack_server_id: str | None
    project_id: uuid.UUID | None

    @classmethod
    def from_db_model(cls, db_server: Servers) -> "DBServerRead":
        """Create a Server instance from an openstack server object"""
        return cls(
            id=db_server.id,
            public_ip=db_server.public_ip,
            state=db_server.state,
            created_at=db_server.created_at,
            updated_at=db_server.updated_at,
            openstack_server_id=db_server.openstack_server_id,
            project_id=db_server.project_id,
        )


class DBServerCreate(BaseModelAdjusted):
    """Class to represent the creation of a server in the database"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    public_ip: str | None = None
    state: ServerStatus = ServerStatus.CREATING
    openstack_server_id: str | None = None
    project_id: uuid.UUID


class DBServerUpdate(BaseModelAdjusted):
    """Class to represent the update of a server in the database"""

    id: uuid.UUID
    public_ip: str | None = None
    state: ServerStatus | None = None
    openstack_server_id: str | None = None
    error_type: str | None = None
    error_summary_base64: str | None = None


class ServerCreationPayload(BaseModel):
    """Payload for creating a server"""

    username: str | None = None
    password: str | None = None
    image_name: str | None = None
    flavor_name: str | None = None
    project_id: str
    ssh_public_key: str | None = None
