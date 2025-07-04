"""Models for profiles"""

import uuid

from despsharedlibrary.schemas.sandbox_schema import Profiles
from msfwk.models import BaseModelAdjusted


class ProfileRead(BaseModelAdjusted):
    """Class to represent a profile in the database"""

    id: uuid.UUID
    username: str
    password: str
    desp_owner_id: str | None

    @classmethod
    def from_db_model(cls, db_profile: Profiles) -> "ProfileRead":
        """Create a Profile instance from a database profile object"""
        return cls(
            id=db_profile.id,
            username=db_profile.username,
            password=db_profile.password,
            desp_owner_id=db_profile.desp_owner_id,
        )
