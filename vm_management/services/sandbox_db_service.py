"""Service for database operations in sandbox environments"""

# ruff: noqa: B904
import datetime
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from despsharedlibrary.schemas.sandbox_schema import Events, EventType, Profiles, Projects, Servers, ServerStatus
from fastapi import Depends
from msfwk.utils.logging import get_logger
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from vm_management import models
from vm_management.connectors import SandboxDBConnector, get_sandbox_db_connector
from vm_management.exceptions import DatabaseError, DbProfileNotFoundError, DbServerNotFoundError
from vm_management.models.profiles import ProfileRead
from vm_management.models.projects import ProjectRead
from vm_management.models.server import DBServerCreate, DBServerRead, DBServerUpdate

logger = get_logger("application")


class SandboxDBService:
    """Service for database operations in sandbox environments"""

    def __init__(self, db_connector: SandboxDBConnector) -> "SandboxDBService":
        self.db_connector = db_connector

    async def get_server_by_id(self, server_id: uuid.UUID) -> DBServerRead | None:
        """Get a server by its database ID using ORM"""
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement using the Servers table
                query = select(Servers).where(Servers.id == server_id)

                # Execute the statement
                result = await session.execute(query)

                # Get the first row
                server = result.scalar_one_or_none()

                if server is None:
                    logger.debug("Server not found - server_id=%s", server_id)
                    raise DbServerNotFoundError(server_id=server_id)

                return DBServerRead.from_db_model(server)
            except DbServerNotFoundError:
                raise
            except SQLAlchemyError as e:
                message = "Failed to get server by ID"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=server_id)

    async def get_server_by_openstack_id(self, openstack_server_id: str) -> DBServerRead | None:
        """Get a server by its OpenStack ID using ORM"""
        if isinstance(openstack_server_id, uuid.UUID):
            openstack_server_id = str(openstack_server_id)
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement using the Servers table
                query = select(Servers).where(Servers.openstack_server_id == openstack_server_id)

                # Execute the statement
                result = await session.execute(query)

                # Get the first row
                server = result.scalar_one_or_none()

                if server is None:
                    message = f"Server not found - openstack_server_id={openstack_server_id}"
                    logger.debug(message)
                    raise DbServerNotFoundError(server_id=openstack_server_id)

                return DBServerRead.from_db_model(server)
            except DbServerNotFoundError:
                raise
            except SQLAlchemyError as e:
                message = "Failed to get server by OpenStack ID"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=openstack_server_id)

    async def get_servers_by_project_id(self, project_id: str) -> list[DBServerRead]:
        """Get servers by project ID using ORM"""
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement using the Servers table
                query = select(Servers).where(Servers.project_id == project_id)

                # Execute the statement
                result = await session.execute(query)

                # Get all rows
                servers = result.scalars().all()

                if not servers:
                    logger.debug("No servers found for project - project_id=%s", project_id)
                    return []

                return [DBServerRead.from_db_model(server) for server in servers]
            except SQLAlchemyError as e:
                message = "Failed to get servers by project ID"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=project_id)

    async def list_all_servers(self) -> list[DBServerRead]:
        """List all servers using ORM"""
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement using the Servers table
                query = select(Servers)

                # Execute the statement
                result = await session.execute(query)

                # Get all rows
                servers = result.scalars().all()

                return [DBServerRead.from_db_model(server) for server in servers]
            except SQLAlchemyError as e:
                message = "Failed to list all servers"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message)

    async def get_suspended_servers_older_than(self, days: float) -> list[DBServerRead]:
        """Get servers that have been suspended for more than the specified number of days

        Args:
            days: Number of days to check against

        Returns:
            List of servers that have been suspended for more than the specified days
        """
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days)

        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement for suspended servers updated before cutoff date
                query = select(Servers).where(Servers.state == ServerStatus.SUSPENDED, Servers.updated_at < cutoff_date)

                # Execute the statement
                result = await session.execute(query)

                # Get all rows
                servers = result.scalars().all()

                logger.info("Found %d servers suspended for more than %s days", len(servers), days)
                return [DBServerRead.from_db_model(server) for server in servers]
            except SQLAlchemyError as e:
                message = "Failed to get suspended servers"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message)

    async def get_suspended_servers_in_window(
        self, lower_cutoff: datetime, upper_cutoff: datetime
    ) -> list[DBServerRead]:
        """Get servers that have been suspended for a duration in a specific window

        Args:
            lower_cutoff: The older timestamp (servers suspended before this time are NOT included)
            upper_cutoff: The newer timestamp (servers suspended after this time are NOT included)

        Returns:
            List of servers that have been suspended within the specified time window
        """
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement for suspended servers updated within the time window
                query = select(Servers).where(
                    Servers.state == ServerStatus.SUSPENDED,
                    Servers.updated_at <= upper_cutoff,
                    Servers.updated_at >= lower_cutoff,
                )

                # Execute the statement
                result = await session.execute(query)

                # Get all rows
                return result.scalars().all()

            except SQLAlchemyError as e:
                message = "Failed to get suspended servers in window"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message)

    async def update_server(self, db_server: DBServerUpdate) -> DBServerRead | None:
        """Update server with multiple fields using ORM"""
        async with self.db_connector.session_context(begin_transaction=True) as session:
            try:
                # Create an update statement using the Servers table
                updates = db_server.model_dump(
                    exclude_unset=True, exclude_none=True, exclude={"id", "error_type", "error_summary_base64"}
                )
                query = update(Servers).where(Servers.id == db_server.id).values(**updates)

                # Execute the statement
                await session.execute(query)

                # Get the updated row
                updated_server = await session.execute(select(Servers).where(Servers.id == db_server.id))
                server = updated_server.scalar_one_or_none()

                if server is None:
                    message = f"Server not found for update - server_id={db_server.id}"
                    logger.debug(message)
                    raise DbServerNotFoundError(server_id=db_server.id)

                logger.info("Server updated - server_id=%s, updates=%s", db_server.id, updates)
                return DBServerRead.from_db_model(server)
            except DbServerNotFoundError:
                raise
            except SQLAlchemyError as e:
                message = "Failed to update server"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=db_server.id)

    async def delete_server_by_openstack_id(self, openstack_server_id: str) -> bool:
        """Delete server using ORM"""
        if isinstance(openstack_server_id, uuid.UUID):
            openstack_server_id = str(openstack_server_id)
        async with self.db_connector.session_context(begin_transaction=True) as session:
            try:
                # Create a delete statement using the Servers table
                query = delete(Servers).where(Servers.openstack_server_id == openstack_server_id).returning(Servers.id)

                # Execute the statement
                result = await session.execute(query)

                # Check if a row was deleted
                deleted = result.scalar_one_or_none()

                if not deleted:
                    logger.debug("Server not found for deletion - openstack_server_id=%s", openstack_server_id)
                    return False

                logger.info("Server deleted - openstack_server_id=%s", openstack_server_id)

            except SQLAlchemyError as e:
                message = "Failed to delete server"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=openstack_server_id)
            return True

    async def create_server_from_openstack(
        self, openstack_server: models.OpenStackServerRead, project_id: str
    ) -> DBServerRead:
        """Create a sandbox database server entry from an OpenStack server

        Args:
            openstack_server: The OpenStack server object
            project_id: The UUID of the project to associate with the server

        Returns:
            The created server record
        """
        logger.info("Creating sandbox DB server from OpenStack server - server_id=%s", openstack_server.id)

        # Extract public IP if available
        public_ip = None
        if hasattr(openstack_server, "addresses") and openstack_server.addresses:
            # Try to find a public IP in the addresses
            for addresses in openstack_server.addresses.values():
                for address in addresses:
                    if address.get("OS-EXT-IPS:type") == "floating" or address.get("type") == "floating":
                        public_ip = address.get("addr")
                        break
                if public_ip:
                    break

        # Get server state
        state = openstack_server.status.lower() if hasattr(openstack_server, "status") else "unknown"

        # Generate a UUID for the server
        server_id = str(uuid.uuid4())

        async with self.db_connector.session_context(begin_transaction=True) as session:
            try:
                new_server = Servers(
                    id=server_id,
                    public_ip=public_ip,
                    state=state,
                    openstack_server_id=str(openstack_server.id),
                    project_id=project_id,
                )
                session.add(new_server)
                await session.commit()
                await session.refresh(new_server)

                return DBServerRead.from_db_model(new_server)

            except SQLAlchemyError as e:
                message = "Failed to create server from OpenStack"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=openstack_server.id)

    async def create_server(self, db_server_create: DBServerCreate) -> DBServerRead:
        """Create a server in the database"""
        async with self.db_connector.session_context(begin_transaction=True) as session:
            try:
                new_server = Servers(**db_server_create.model_dump())
                session.add(new_server)
                await session.commit()
                return DBServerRead.from_db_model(new_server)
            except SQLAlchemyError as e:
                message = "Failed to create server"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, server_id=db_server_create.id)

    async def store_event_in_database(
        self, project_id: uuid.UUID, step: str, status: str, content: str | None = None
    ) -> None:
        """Stores an event in the database."""
        async with self.db_connector.session_context() as db_session:
            try:
                if content is None:
                    content = f"Step '{step}' has {status.lower()}."
                event_type = EventType.VM
                new_event = Events(
                    project_id=project_id,
                    type=event_type,
                    step=step,
                    pipeline_id=" ",
                    status=status,
                    content=content,
                )

                db_session.add(new_event)
                await db_session.commit()
            except SQLAlchemyError as e:
                message = "Failed to store event in database"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message)

    async def get_profile_by_username(self, username: str) -> ProfileRead | None:
        """Get a profile by username using ORM"""
        async with self.db_connector.session_context() as session:
            try:
                query = select(Profiles).where(Profiles.username == username)
                result = await session.execute(query)
                profile = result.scalar_one_or_none()
                if profile is None:
                    logger.debug("Profile not found - username=%s", username)
                    raise DbProfileNotFoundError(username=username)
                return ProfileRead.from_db_model(profile)
            except DbProfileNotFoundError:
                raise
            except SQLAlchemyError as e:
                message = "Failed to get profile by username"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, username=username)

    async def get_project_by_id(self, project_id: uuid.UUID) -> ProjectRead:
        """Get a project by ID using ORM"""
        async with self.db_connector.session_context() as session:
            try:
                # Create a select statement using the Projects table with explicit joins for profile and server
                query = (
                    select(Projects)
                    .options(joinedload(Projects.profile), joinedload(Projects.server))
                    .where(Projects.id == project_id)
                )

                # Execute the statement
                result = await session.execute(query)

                # Get the project with its relationships
                project = result.scalar_one_or_none()

                if project is None:
                    message = f"Project not found with id {project_id}"
                    logger.debug(message)
                    raise DatabaseError(message)

                # Ensure that the profile is loaded
                if project.profile is None:
                    message = f"Project found but profile is missing with id {project_id}"
                    logger.error(message)
                    raise DatabaseError(message)

                # At this point, both profile and server (if it exists) are loaded
                # The ProjectRead.from_db_model method will handle the conversion
                return ProjectRead.from_db_model(project)
            except SQLAlchemyError as e:
                message = "Failed to get project by ID"
                logger.exception(message, exc_info=e)
                raise DatabaseError(message, project_id=project_id)


async def get_sandbox_db_service(
    db_connector: Annotated[SandboxDBConnector, Depends(get_sandbox_db_connector)],
) -> SandboxDBService:
    """Returns an instance of SandboxDBService"""
    return SandboxDBService(db_connector=db_connector)
