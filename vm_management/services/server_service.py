"""Service layer for server operations integrating OpenStack and database management"""

# ruff: noqa: B904
import uuid
from typing import Annotated

import httpx
from despsharedlibrary.schemas.sandbox_schema import ServerStatus
from fastapi import Depends
from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from pydantic import BaseModel

from vm_management import models
from vm_management.exceptions import (
    DatabaseError,
    DbServerNotFoundError,
    InfrastructureError,
    OpenStackServerNotFoundError,
    ProjectNotFoundError,
    ProjectServiceError,
    ServerManagementError,
)
from vm_management.models.server import DBServerCreate, DBServerRead, DBServerUpdate, ServerCreationPayload
from vm_management.services import GuacamoleService, get_guacamole_service
from vm_management.services.guacamole_service import GuacamoleConnectionAttributes, RDPConnectionParameters
from vm_management.services.infrastructure_service import InfrastructureService, get_infrastructure_service
from vm_management.services.openstack_server_service import (
    OpenStackServerService,
    ServerInvalidStateError,
    get_openstack_server_service,
)
from vm_management.services.project_service import ProjectService, get_project_service
from vm_management.services.sandbox_db_service import SandboxDBService, get_sandbox_db_service

logger = get_logger("application")


class ServerConfig(BaseModel):
    """Configuration for a server"""

    with_openstack: bool = True


class ServerService:
    """Service layer for server operations integrating OpenStack and database management"""

    def __init__(
        self,
        openstack_service: OpenStackServerService,
        db_service: SandboxDBService,
        server_config: ServerConfig,
        infrastructure_service: InfrastructureService,
        project_service: ProjectService,
        guacamole_service: GuacamoleService,
    ):
        self.openstack_service = openstack_service
        self.db_service = db_service
        self.server_config = server_config
        self.infrastructure_service = infrastructure_service
        self.project_service = project_service
        self.guacamole_service = guacamole_service

    async def create_server(self, server_creation_payload: ServerCreationPayload, transaction_id: str = "") -> None:
        """Create a server in OpenStack by running a terraform k8s job

        Args:
            server_creation_payload: Server creation payload
            transaction_id: Transaction ID
        """
        logger.info("Creating server - project_id=%s", server_creation_payload.project_id)

        if self.server_config.with_openstack:
            try:
                # Create the server in the database
                project_id = uuid.UUID(str(server_creation_payload.project_id))
                db_server_create = DBServerCreate(project_id=project_id)
                db_server_create.openstack_server_id = str(uuid.uuid4())
                db_server = await self.db_service.create_server(db_server_create)

                # create guacamole user
                await self.guacamole_service.create_user_and_assign_to_group(
                    username=server_creation_payload.username,
                    password=server_creation_payload.password,
                    group_identifier=self.guacamole_service.config.group_name,
                )

                # Update the state in the database
                db_server_update = DBServerUpdate(id=db_server.id, state=ServerStatus.CREATING)
                await self.db_service.store_event_in_database(project_id, ServerStatus.CREATING.name, "STARTED")
                await self.db_service.update_server(db_server_update)

                try:
                    # Use infrastructure service to create the server infrastructure
                    await self.infrastructure_service.create_server_with_terraform(
                        server_id=db_server.id,
                        server_creation_payload=server_creation_payload,
                        transaction_id=transaction_id,
                    )
                    logger.info("Server creation in progress - server_id=%s", db_server.id)
                except InfrastructureError as infra_err:
                    message = f"Failed to create server infrastructure - server_id={db_server.id}"
                    logger.exception(message, exc_info=infra_err)
                    db_server_update = DBServerUpdate(id=db_server.id, state=ServerStatus.ERROR)
                    await self.db_service.store_event_in_database(project_id, ServerStatus.CREATING.name, "FAILED")
                    await self.db_service.update_server(db_server_update)
                    raise ServerManagementError(message)

            except (DatabaseError, InfrastructureError, ProjectServiceError, ServerManagementError):
                if db_server:
                    db_server_update = DBServerUpdate(id=db_server.id, state=ServerStatus.ERROR)
                    await self.db_service.store_event_in_database(project_id, ServerStatus.CREATING.name, "FAILED")
                    await self.db_service.update_server(db_server_update)
                raise
            except Exception as e:
                if db_server:
                    db_server_update = DBServerUpdate(id=db_server.id, state=ServerStatus.ERROR)
                    await self.db_service.store_event_in_database(project_id, ServerStatus.CREATING.name, "FAILED")
                    await self.db_service.update_server(db_server_update)
                message = "Failed to create server"
                logger.exception(message, exc_info=e)
                raise ServerManagementError(message) from ellipsis
        else:
            message = "Server creation without OpenStack with horizon is deprecated"
            logger.warning(message)
            raise ServerManagementError(message)

    async def shelve_server(self, server_id: uuid.UUID) -> None:
        """Shelve a server in OpenStack and update its state in the database

        Args:
            server_id: Database server ID
        """
        logger.info("Shelving server - server_id=%s", server_id)

        try:
            # First get the server record from the database
            db_server = await self.db_service.get_server_by_id(server_id)

            # Get the OpenStack server ID
            openstack_server_id = db_server.openstack_server_id

            # Shelve server in OpenStack
            await self.openstack_service.shelve_server(uuid.UUID(openstack_server_id))

            openstack_server = await self.openstack_service.get_server_by_id(uuid.UUID(openstack_server_id))

            # Suspending state update the state in the database
            state = ServerStatus.SUSPENDING
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
            updated_server = await self.db_service.update_server(db_server_update)

            # Delete guacamole connection
            await self._delete_guacamole_connection(updated_server)

            # Wait for the server to be shelved
            await self.openstack_service.wait_for_server(
                server_id=openstack_server.id, wait=900, status=models.OpenStackServerStatus.SHELVED_OFFLOADED.value
            )

            # Suspended state update the state in the database
            state = ServerStatus.SUSPENDED
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(
                db_server.project_id, ServerStatus.SUSPENDING.name, "SUCCEEDED"
            )
            await self.db_service.update_server(db_server_update)

            logger.info("Completed server shelving - server_id=%s, state=%s", server_id, state)
        except (DbServerNotFoundError, OpenStackServerNotFoundError, ServerInvalidStateError, DatabaseError):
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED")
            raise
        except Exception as e:
            logger.exception("Failed to shelve server - error=%s", str(e))
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED")
            msg = f"Failed to shelve server: {e}"
            raise ServerManagementError(msg, server_id=server_id)

    async def shelve_servers(self, server_ids: list[uuid.UUID]) -> dict[uuid.UUID, bool]:
        """Shelve multiple servers in OpenStack and update their states in the database

        Args:
            server_ids: List of database server IDs to shelve

        Returns:
            dict[uuid.UUID, bool]: Dictionary mapping server IDs to success status
        """
        logger.info("Shelving multiple servers - count=%s", len(server_ids))

        results = {}

        for server_id in server_ids:
            try:
                # First get the server record from the database
                db_server = await self.db_service.get_server_by_id(server_id)

                # Get the OpenStack server ID
                openstack_server_id = db_server.openstack_server_id

                # Shelve server in OpenStack
                await self.openstack_service.shelve_server(uuid.UUID(openstack_server_id))

                # Update the state in the database to SUSPENDING
                state = ServerStatus.SUSPENDING
                db_server_update = DBServerUpdate(id=db_server.id, state=state)
                await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
                updated_server = await self.db_service.update_server(db_server_update)

                # Delete guacamole connection
                await self._delete_guacamole_connection(updated_server)

                logger.info("Initiated shelving for server - server_id=%s", server_id)
                results[server_id] = True
            except (DbServerNotFoundError, OpenStackServerNotFoundError, ServerInvalidStateError, DatabaseError) as e:
                message = f"Failed to initiate shelving for server - server_id={server_id}"
                logger.exception(message, exc_info=e)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[server_id] = False
            except Exception as e:
                message = f"Unexpected error shelving server - server_id={server_id}"
                logger.exception(message, exc_info=e)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[server_id] = False

        # Now wait for all servers to complete shelving and update their status
        for server_id in [sid for sid, success in results.items() if success]:
            try:
                db_server = await self.db_service.get_server_by_id(server_id)
                openstack_server_id = uuid.UUID(db_server.openstack_server_id)

                # Wait for the server to be shelved
                await self.openstack_service.wait_for_server(
                    server_id=openstack_server_id, wait=900, status=models.OpenStackServerStatus.SHELVED_OFFLOADED.value
                )

                # Update the state in the database to SUSPENDED
                state = ServerStatus.SUSPENDED
                db_server_update = DBServerUpdate(id=db_server.id, state=state)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "SUCCEEDED"
                )
                await self.db_service.update_server(db_server_update)

                logger.info("Completed server shelving - server_id=%s, state=%s", server_id, state)
            except Exception as e:
                logger.error("Failed to complete shelving for server - server_id=%s, error=%s", server_id, str(e))
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[server_id] = False

        success_count = sum(1 for success in results.values() if success)
        logger.info("Completed shelving multiple servers - total=%s, success=%s", len(server_ids), success_count)

        return results

    async def shelve_openstack_servers(self, openstack_server_ids: list[uuid.UUID]) -> dict[uuid.UUID, bool]:
        """Shelve multiple OpenStack servers and update their states in the database

        Args:
            openstack_server_ids: List of OpenStack server IDs to shelve

        Returns:
            dict[uuid.UUID, bool]: Dictionary mapping OpenStack server IDs to success status
        """
        logger.info("Shelving multiple OpenStack servers - count=%s", len(openstack_server_ids))

        results = {}
        db_servers_map = {}

        # First, try to find all servers in the database
        for openstack_id in openstack_server_ids:
            try:
                db_server = await self.db_service.get_server_by_openstack_id(str(openstack_id))
                db_servers_map[openstack_id] = db_server
            except DbServerNotFoundError:
                message = f"Server not found in database - openstack_id={openstack_id}"
                logger.warning(message)
                results[openstack_id] = False

        # Initiate shelving for all servers found in the database
        for openstack_id, db_server in db_servers_map.items():
            try:
                # Shelve server in OpenStack
                await self.openstack_service.shelve_server(openstack_id)

                # Update the state in the database to SUSPENDING
                state = ServerStatus.SUSPENDING
                db_server_update = DBServerUpdate(id=db_server.id, state=state)
                await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
                updated_server = await self.db_service.update_server(db_server_update)

                # Delete guacamole connection
                await self._delete_guacamole_connection(updated_server)

                logger.info("Initiated shelving for server - openstack_id=%s, db_id=%s", openstack_id, db_server.id)
                results[openstack_id] = True
            except (OpenStackServerNotFoundError, ServerInvalidStateError, DatabaseError) as e:
                message = f"Failed to initiate shelving for server - openstack_id={openstack_id}"
                logger.exception(message, exc_info=e)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[openstack_id] = False
            except Exception as e:
                message = f"Unexpected error shelving server - openstack_id={openstack_id}"
                logger.exception(message, exc_info=e)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[openstack_id] = False

        # Now wait for all servers to complete shelving and update their status
        for openstack_id, success in list(results.items()):
            if not success or openstack_id not in db_servers_map:
                continue

            try:
                db_server = db_servers_map[openstack_id]

                # Wait for the server to be shelved
                await self.openstack_service.wait_for_server(
                    server_id=openstack_id, wait=900, status=models.OpenStackServerStatus.SHELVED_OFFLOADED.value
                )

                # Update the state in the database to SUSPENDED
                state = ServerStatus.SUSPENDED
                db_server_update = DBServerUpdate(id=db_server.id, state=state)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "SUCCEEDED"
                )
                await self.db_service.update_server(db_server_update)

                logger.info(
                    "Completed server shelving - openstack_id=%s, db_id=%s, state=%s", openstack_id, db_server.id, state
                )
            except Exception as e:
                message = f"Failed to complete shelving for server - openstack_id={openstack_id}"
                logger.exception(message, exc_info=e)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.SUSPENDING.name, "FAILED"
                )
                results[openstack_id] = False

        success_count = sum(1 for success in results.values() if success)
        logger.info(
            "Completed shelving multiple OpenStack servers - total=%s, success=%s",
            len(openstack_server_ids),
            success_count,
        )

        return results

    async def unshelve_server(self, server_id: uuid.UUID) -> None:
        """Unshelve a server in OpenStack and update its state in the database

        Args:
            server_id: Database server ID
        """
        logger.info("Unshelving server - server_id=%s", server_id)

        try:
            # First get the server record from the database
            db_server = await self.db_service.get_server_by_id(server_id)

            # Get the OpenStack server ID
            openstack_server_id = db_server.openstack_server_id

            # Unshelve server in OpenStack
            await self.openstack_service.unshelve_server(uuid.UUID(openstack_server_id))

            openstack_server = await self.openstack_service.get_server_by_id(uuid.UUID(openstack_server_id))

            # Update the state in the database
            state = ServerStatus.RESUMING
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
            updated_server = await self.db_service.update_server(db_server_update)

            # Wait for the server to be unshelved
            await self.openstack_service.wait_for_server(
                server_id=openstack_server.id, wait=900, status=models.OpenStackServerStatus.ACTIVE.value
            )

            # Update the state in the database
            state = ServerStatus.READY
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.RESUMING.name, "SUCCEEDED")
            updated_server = await self.db_service.update_server(db_server_update)

            # Create RDP connection
            await self._create_gucameole_connection(updated_server)

            logger.info("Completed server unshelving - server_id=%s, state=%s", server_id, state)

        except (DbServerNotFoundError, OpenStackServerNotFoundError, ServerInvalidStateError, DatabaseError):
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.RESUMING.name, "FAILED")
            raise
        except Exception as e:
            message = f"Failed to unshelve server - error={e}"
            logger.exception(message, exc_info=e)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.RESUMING.name, "FAILED")
            raise ServerManagementError(message, server_id=server_id)

    async def reset_server(self, server_id: uuid.UUID, transaction_id: str) -> None:
        """Reset a server in OpenStack and update its state in the database

        Args:
            server_id: Database server ID
            transaction_id: Transaction ID
        """
        logger.info("Resetting server - server_id=%s", server_id)

        try:
            # First get the server record from the database
            db_server = await self.db_service.get_server_by_id(server_id)

            # Get the OpenStack server ID
            openstack_server_id = db_server.openstack_server_id

            # Reset server in OpenStack
            await self.openstack_service.reset_server(uuid.UUID(openstack_server_id))

            openstack_server = await self.openstack_service.get_server_by_id(uuid.UUID(openstack_server_id))

            # Resetting state update the state in the database
            state = ServerStatus.RESETTING
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
            updated_server = await self.db_service.update_server(db_server_update)

            # Delete guacamole connection
            await self._delete_guacamole_connection(updated_server)

            # Wait for the server to be reset
            await self.openstack_service.wait_for_server(
                server_id=openstack_server.id, wait=900, status=models.OpenStackServerStatus.ACTIVE.value
            )

            # Ready state update the state in the database
            state = ServerStatus.READY
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            updated_server = await self.db_service.update_server(db_server_update)

            # Create RDP connection
            await self._create_gucameole_connection(updated_server)

            # Configure server with Ansible
            await self.configure_server_with_ansible(updated_server.id, transaction_id)
            await self.db_service.store_event_in_database(
                db_server.project_id, ServerStatus.RESETTING.name, "SUCCEEDED"
            )

            logger.info("Installing applications with ansible on the server - server_id=%s", server_id)

            logger.info("Completed server reset - server_id=%s, state=%s", server_id, state)

        except (DbServerNotFoundError, OpenStackServerNotFoundError, ServerInvalidStateError, DatabaseError):
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.RESETTING.name, "FAILED")
            raise

        except Exception as e:
            message = f"Failed to reset server - error={e}"
            logger.exception(message, exc_info=e)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.RESETTING.name, "FAILED")
            raise ServerManagementError(message, server_id=server_id)

    async def delete_server(self, server_id: uuid.UUID) -> None:
        """Delete a server in OpenStack and mark it as deleted in the database

        Args:
            server_id: Database server ID
        """
        logger.info("Deleting server - server_id=%s", server_id)

        try:
            # First get the server record from the database
            db_server = await self.db_service.get_server_by_id(server_id)

            # Get the OpenStack server ID
            openstack_server_id = uuid.UUID(db_server.openstack_server_id)

            # First get the server to ensure it exists
            await self.openstack_service.get_server_by_id(openstack_server_id)

            # Update the state in the database to deleting
            state = ServerStatus.DELETING
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, state.name, "STARTED")
            await self.db_service.update_server(db_server_update)

            # Delete server in OpenStack
            await self.openstack_service.delete_server(openstack_server_id)

            # Mark as deleted in the database
            state = ServerStatus.DELETED
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.DELETING.name, "SUCCEEDED")
            await self.db_service.update_server(db_server_update)

            # Delete the guacamole connection
            await self._delete_guacamole_connection(db_server)

            await self.db_service.delete_server_by_openstack_id(str(openstack_server_id))

            logger.info("Completed server deletion - server_id=%s", server_id)

        except OpenStackServerNotFoundError as e:
            logger.warning("Server not found - server_id=%s, error=%s", server_id, str(e))
            # We don't need to update anything if the server wasn't found
            # Mark as deleted in the database

            state = ServerStatus.DELETED
            db_server_update = DBServerUpdate(id=db_server.id, state=state)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.DELETING.name, "SUCCEEDED")
            await self.db_service.update_server(db_server_update)

            await self.db_service.delete_server_by_openstack_id(str(openstack_server_id))
            logger.info("Completed server deletion - server_id=%s", server_id)

        except (DbServerNotFoundError, ServerInvalidStateError, DatabaseError):
            raise
        except Exception as e:
            message = f"Failed to delete server - error={e}"
            logger.exception(message, exc_info=e)
            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.DELETING.name, "FAILED")
            raise ServerManagementError(message, server_id=server_id)

    async def configure_server_with_ansible(self, server_id: uuid.UUID, transaction_id: str) -> None:
        """Configure a server with Ansible

        Args:
            server_id: Database server ID
            transaction_id: Transaction ID
        Raises:
            ResourceNotFoundError: If the server or project is not found
            ServerInvalidStateError: If the server is in an invalid state
            SQLAlchemyError: If there's a database error
            aiohttp.ClientError: If there's an error communicating with external services
        """
        logger.info("Configuring server with Ansible - server_id=%s", server_id)
        try:
            # Get server from database
            server = await self.db_service.get_server_by_id(server_id)

            # Get project from project management
            try:
                project = await self.project_service.get_project_by_id(server.project_id)
                logger.info("Retrieved project information - project_id=%s", server.project_id)
            except ProjectNotFoundError:
                raise

            # Run Ansible setup via the infrastructure service
            await self.db_service.store_event_in_database(server.project_id, ServerStatus.INSTALLING.name, "STARTED")
            await self.infrastructure_service.run_ansible_setup(server.id, server.public_ip, project, transaction_id)

            # Update server status to indicate configuration is in progress
            db_server_update = DBServerUpdate(id=server_id, state=ServerStatus.INSTALLING)
            await self.db_service.update_server(db_server_update)

            logger.info("Ansible configuration initiated - server_id=%s", server_id)
        except InfrastructureError as infra_err:
            message = f"Infrastructure error during ansible configuration - server_id={server_id}"
            logger.exception(message, exc_info=infra_err)
            # Update server status to ERROR
            db_server_update = DBServerUpdate(id=server_id, state=ServerStatus.ERROR)
            await self.db_service.update_server(db_server_update)
            await self.db_service.store_event_in_database(server.project_id, ServerStatus.INSTALLING.name, "FAILED")
            raise ServerManagementError(f"Failed to configure server with Ansible: {infra_err}", server_id=server_id)
        except (
            DbServerNotFoundError,
            OpenStackServerNotFoundError,
            ServerInvalidStateError,
            DatabaseError,
            ProjectServiceError,
        ):
            raise
        except Exception as e:
            message = "Failed to configure server with Ansible"
            logger.exception(message, exc_info=e)
            # Update server status to ERROR
            db_server_update = DBServerUpdate(id=server_id, state=ServerStatus.ERROR)
            await self.db_service.update_server(db_server_update)
            await self.db_service.store_event_in_database(server.project_id, ServerStatus.INSTALLING.name, "FAILED")
            raise ServerManagementError(message, server_id=server_id)

    async def terraform_complete(
        self, server_id: uuid.UUID, server_update: DBServerUpdate, transaction_id: str
    ) -> None:
        """Update server status to indicate terraform completion

        Args:
            server_id: Database server ID
            server_update: Server updates
            transaction_id: Transaction ID
        """
        logger.info("Terraform completion - server_id=%s", server_id)

        try:
            db_server = await self.db_service.get_server_by_id(server_id)
            if server_update.state == ServerStatus.ERROR:
                logger.warning("Terraform job failed - server_id=%s", server_id)

                # Update server status to error
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.CREATING.name, "FAILED", server_update.error_type
                )
                await self.db_service.update_server(server_update)
                return

            await self.db_service.store_event_in_database(db_server.project_id, ServerStatus.CREATING.name, "SUCCEEDED")

            # Update server status to installing and call ansible setup
            server_update.state = ServerStatus.INSTALLING

            db_server = await self.db_service.update_server(server_update)

            # create connection rdp to the server
            await self._create_gucameole_connection(db_server)

            await self.configure_server_with_ansible(server_id, transaction_id)

            logger.info(" Server updated successfully - server_id=%s", server_id)

        except (
            OpenStackServerNotFoundError,
            DbServerNotFoundError,
            ServerInvalidStateError,
            DatabaseError,
            InfrastructureError,
            ProjectServiceError,
        ):
            raise
        except Exception as e:
            message = "Failed to update server"
            logger.exception(message, exc_info=e)
            raise ServerManagementError(message, server_id=server_id)

    async def ansible_complete(self, server_id: uuid.UUID, updates: DBServerUpdate) -> DBServerRead:
        """Update server status to indicate ansible completion

        Args:
            server_id: Database server ID
            updates: Server updates containing the final status (READY or ERROR)
        """
        logger.info("Ansible completion - server_id=%s", server_id)

        try:
            # Update server status based on the provided state
            db_server_update = DBServerUpdate(id=server_id, state=updates.state)
            db_server = await self.db_service.get_server_by_id(server_id)
            await self.db_service.update_server(db_server_update)

            if updates.state == ServerStatus.READY:
                logger.info("Server configuration completed successfully - server_id=%s", server_id)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.INSTALLING.name, "SUCCEEDED"
                )
            else:
                logger.warning("Server configuration failed - server_id=%s", server_id)
                await self.db_service.store_event_in_database(
                    db_server.project_id, ServerStatus.INSTALLING.name, "FAILED"
                )
            return db_server

        except (OpenStackServerNotFoundError, DbServerNotFoundError, ServerInvalidStateError, DatabaseError):
            raise
        except Exception as e:
            message = "Failed to update server"
            logger.exception(message, exc_info=e)
            raise ServerManagementError(message, server_id=server_id)

    async def _create_gucameole_connection(self, server: DBServerRead) -> None:
        """Create a RDP connection to the server

        Args:
            server: Database server
        """
        logger.info("Creating RDP connection to the server - server_id=%s", server.id)

        try:
            # Get the project from the database
            project = await self.db_service.get_project_by_id(server.project_id)

            # Create a separate Guacamole service instance for user authentication
            user_guacamole_service = GuacamoleService(self.guacamole_service.config)
            await user_guacamole_service.authenticate(
                username=project.profile.username, password=project.profile.password
            )

            # Check if connection already exists
            connection_name = f"RDP-{project.name}-{server.public_ip}"
            connections = await user_guacamole_service.list_connections()

            # Check if connection already exists by name
            if not connections:
                logger.info("No connections found for server - server_id=%s", server.id)
            else:
                for conn_details in connections.values():
                    if conn_details.get("name") == connection_name:
                        logger.warning("RDP connection already exists - name=%s", connection_name)
                        return

            # Create the RDP connection parameters
            rdp_connection_parameters = RDPConnectionParameters(
                hostname=server.public_ip,
                port=self.guacamole_service.config.rdp_port,
                username=project.profile.username,
                password=project.profile.password,
            )
            guacamole_connection_attributes = GuacamoleConnectionAttributes(
                max_connections="5",
                guacd_hostname=self.guacamole_service.config.guacd_hostname,
            )

            # Create the RDP connection using the user-authenticated service
            await user_guacamole_service.create_connection(
                name=connection_name,
                protocol="rdp",
                parameters=rdp_connection_parameters,
                attributes=guacamole_connection_attributes,
            )
            await self.db_service.store_event_in_database(
                server.project_id, ServerStatus.CREATING.name, "SUCCEEDED", "GUACAMOLE RDP connection created"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "already exists" in e.response.text:
                logger.warning("RDP connection already exists - name=%s", connection_name)
            else:
                logger.exception("Failed to create RDP connection - HTTP error: %s", str(e))
                await self.db_service.store_event_in_database(
                    server.project_id, ServerStatus.CREATING.name, "FAILED", "Failed to create RDP connection."
                )
        except Exception as e:
            logger.exception("Failed to create RDP connection - error: %s", str(e))
            await self.db_service.store_event_in_database(
                server.project_id, ServerStatus.CREATING.name, "FAILED", "Failed to create RDP connection."
            )

    async def _delete_guacamole_connection(self, server: DBServerRead) -> None:
        """Delete the RDP connection to the server

        Args:
            server: Database server
        """
        logger.info("Deleting RDP connection for server - server_id=%s", server.id)

        try:
            # Get the project from the database
            project = await self.db_service.get_project_by_id(server.project_id)

            # Create a separate Guacamole service instance for user authentication
            user_guacamole_service = GuacamoleService(self.guacamole_service.config)
            await user_guacamole_service.authenticate(
                username=project.profile.username, password=project.profile.password
            )

            # List all connections
            connections = await user_guacamole_service.list_connections()
            if not connections:
                logger.info("No connections found for server - server_id=%s", server.id)
                return

            # Find connection by name
            connection_name = f"RDP-{project.name}-{server.public_ip}"
            connection_id = None

            for conn_id, conn_details in connections.items():
                if conn_details.get("name") == connection_name:
                    connection_id = conn_id
                    break

            if not connection_id:
                logger.info("No connection found with name: %s", connection_name)
                return

            # Delete the connection
            await user_guacamole_service.delete_connection(connection_id)
            await self.db_service.store_event_in_database(
                server.project_id, ServerStatus.DELETING.name, "SUCCEEDED", "GUACAMOLE RDP connection deleted"
            )
            logger.info("Deleted RDP connection - server_id=%s, connection_id=%s", server.id, connection_id)

        except Exception as e:
            await self.db_service.store_event_in_database(
                server.project_id, ServerStatus.DELETING.name, "FAILED", "Failed to delete RDP connection."
            )
            logger.exception("Failed to delete RDP connection - error=%s", str(e))


def get_server_config() -> ServerConfig:
    """Get server configuration

    Returns
        ServerConfig: Server configuration
    """
    logger.debug("Getting server config")
    config = read_config().get("services").get("vm-management")
    with_openstack = config.get("terraform", True)

    return ServerConfig(with_openstack=with_openstack)


async def get_server_service(
    openstack_service: Annotated[OpenStackServerService, Depends(get_openstack_server_service)],
    db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    server_config: Annotated[ServerConfig, Depends(get_server_config)],
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    guacamole_service: Annotated[GuacamoleService, Depends(get_guacamole_service)],
) -> ServerService:
    """Get server service

    Args:
        openstack_service: OpenStack server service
        db_service: Sandbox database service
        server_config: Server configuration
        infrastructure_service: Infrastructure service
        project_service: Project service

    Returns:
        ServerService: Server service
    """
    return ServerService(
        openstack_service=openstack_service,
        db_service=db_service,
        server_config=server_config,
        infrastructure_service=infrastructure_service,
        project_service=project_service,
        guacamole_service=guacamole_service,
    )
