"""Models for projects"""

import datetime
import uuid

from despsharedlibrary.schemas.sandbox_schema import Projects
from msfwk.models import BaseModelAdjusted

from vm_management.models.profiles import ProfileRead
from vm_management.models.server import DBServerRead


class ProjectRead(BaseModelAdjusted):
    """Class to represent a project in the database"""

    id: uuid.UUID
    name: str
    ssh_key: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    profile: ProfileRead
    operatingsystem_id: uuid.UUID
    flavor_id: uuid.UUID
    repository_id: uuid.UUID
    server: DBServerRead | None

    @classmethod
    def from_db_model(cls, db_project: Projects) -> "ProjectRead":
        """Create a Project instance from a database project object"""
        return cls(
            id=db_project.id,
            name=db_project.name,
            ssh_key=db_project.ssh_key,
            created_at=db_project.created_at,
            updated_at=db_project.updated_at,
            profile=ProfileRead.from_db_model(db_project.profile),
            operatingsystem_id=db_project.operatingsystem_id,
            flavor_id=db_project.flavor_id,
            repository_id=db_project.repository_id,
            server=DBServerRead.from_db_model(db_project.server),
        )
