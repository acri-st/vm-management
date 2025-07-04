"""Manages OpenStack Server operations shelving and unshelving, listing, retrieving"""

# ruff: noqa: TRY400, FBT001, FBT002, B904, BLE001
import asyncio
import uuid
from typing import Annotated

import openstack
import openstack.exceptions
from fastapi import Depends
from msfwk.utils.logging import get_logger
from pydantic import BaseModel

from vm_management.connectors import OpenStackConnector, get_openstack_connector
from vm_management.exceptions import (
    OpenStackServerNotFoundError,
    ServerInvalidStateError,
    ServerManagementError,
    ServerPermissionError,
)
from vm_management.models import OpenStackServerRead, OpenStackServerStatus

logger = get_logger("application")


class OpenStackServerConfig(BaseModel):
    """Configuration model for OpenStack server service"""

    user_server_metadata: dict


class OpenStackServerService:
    """Manages OpenStack Server operations shelving and unshelving, listing, retrieving"""

    def __init__(self, connector: OpenStackConnector, config: OpenStackServerConfig) -> None:
        self.connector = connector
        self.config = config

    def _is_user_vm(self, server: OpenStackServerRead) -> bool:
        """Check if server is a user VM based on metadata"""
        return all(server.metadata.get(k, "").lower() == v.lower() for k, v in self.config.user_server_metadata.items())

    async def _verify_user_vm(self, server: OpenStackServerRead, operation: str) -> None:
        """Verify that server is a user VM, raise exception if not"""
        if not self._is_user_vm(server):
            logger.warning("%s - Server %s is not a user VM", operation, server.id)
            raise ServerPermissionError(server_id=server.id)

    async def get_server_by_id(self, server_id: uuid.UUID) -> OpenStackServerRead | None:
        """Get server by ID"""
        try:
            server = await asyncio.to_thread(lambda: self.connector.conn.compute.get_server(server_id))

            return OpenStackServerRead.from_openstack_server(server)
        except openstack.exceptions.NotFoundException:
            raise OpenStackServerNotFoundError(server_id=server_id)
        except Exception as e:
            logger.error("get_server_by_id - Error getting server %s: %s", server_id, str(e))
            msg = f"Failed to get server by ID {server_id}, {e!s}"
            raise ServerManagementError(msg)

    async def get_servers_by_name(self, server_name: str) -> list[OpenStackServerRead]:
        """Get servers by name"""
        servers = await asyncio.to_thread(lambda: list(self.connector.conn.compute.servers(name=server_name)))
        return [OpenStackServerRead.from_openstack_server(server) for server in servers if self._is_user_vm(server)]

    async def list_servers(self, user_vms_only: bool = True) -> list[OpenStackServerRead]:
        """List all servers"""
        servers = await asyncio.to_thread(lambda: list(self.connector.conn.compute.servers()))
        logger.debug("list_servers - Found %d servers", len(servers))
        if user_vms_only:
            servers = [
                OpenStackServerRead.from_openstack_server(server) for server in servers if self._is_user_vm(server)
            ]
        return servers

    async def delete_server(self, server_id: uuid.UUID) -> None:  # noqa: C901
        """Delete a server by ID and its associated floating IPs and volumes"""
        try:
            server = await self.get_server_by_id(server_id)
            compute_server = await asyncio.to_thread(lambda: self.connector.conn.compute.get_server(server_id))
            await self._verify_user_vm(server, "delete_server")

            # Log associated resources for future cleanup
            resources = {
                "volumes": server.attached_volumes,
                "security_groups": server.security_groups,
                "networks": server.addresses,
                "key_name": server.key_name,
            }

            logger.debug("Associated resources for server %s: %s", server_id, resources)

            # Find and delete floating IPs associated with the server
            floating_ips = []
            for addresses in server.addresses.values():
                for address in addresses:
                    if address.get("OS-EXT-IPS:type") == "floating":
                        floating_ip = address.get("addr")
                        if floating_ip:
                            floating_ips.append(floating_ip)

            if floating_ips:
                logger.info("Found floating IPs to delete: %s", floating_ips)
                for floating_ip in floating_ips:
                    try:
                        # Find the floating IP object by its IP address
                        ip_obj = await asyncio.to_thread(
                            lambda: next(
                                (i for i in self.connector.conn.network.ips() if i.floating_ip_address == floating_ip),
                                None,
                            )
                        )

                        if ip_obj:
                            logger.info("Deleting floating IP %s (ID: %s)", floating_ip, ip_obj.id)
                            await asyncio.to_thread(lambda: self.connector.conn.network.delete_ip(ip_obj.id))
                        else:
                            logger.warning("Could not find floating IP object for %s", floating_ip)
                    except Exception as e:
                        logger.error("Failed to delete floating IP %s: %s", floating_ip, str(e))

            logger.info("Deleting server %s", server_id)
            await asyncio.to_thread(lambda: self.connector.conn.compute.delete_server(server.id))

            compute_server = await asyncio.to_thread(
                lambda: self.connector.conn.compute.wait_for_delete(compute_server)
            )
            logger.info("Server %s deleted", server_id)

            logger.info("Deleting volumes for server %s", server_id)
            # After server deletion, delete any attached volumes
            if hasattr(server, "attached_volumes") and server.attached_volumes:
                for volume in server.attached_volumes:
                    if volume.get("id"):
                        try:
                            await asyncio.to_thread(
                                lambda: self.connector.conn.block_storage.delete_volume(volume["id"])
                            )
                            logger.info("Deleted volume %s attached to server %s", volume["id"], server_id)
                        except Exception as e:
                            logger.error("Failed to delete volume %s: %s", volume["id"], e)

            logger.info("Volumes deleted for server %s.", server_id)
        except OpenStackServerNotFoundError:
            logger.warning("delete_server - Server %s not found", server_id)
            raise
        except Exception as e:
            logger.error("delete_server - Error deleting server %s: %s", server_id, str(e))
            msg = f"Failed to delete server {server_id}, {e!s}"
            raise ServerManagementError(msg)

    async def shelve_server(self, server_id: uuid.UUID) -> None:
        """Shelve a server by ID"""
        try:
            server = await self.get_server_by_id(server_id)

            await self._verify_user_vm(server, "shelve_server")

            valid_states = [
                OpenStackServerStatus.ACTIVE.value,
                OpenStackServerStatus.SHUTOFF.value,
                OpenStackServerStatus.PAUSED.value,
                OpenStackServerStatus.SUSPENDED.value,
            ]

            if server.status.lower() == OpenStackServerStatus.SHELVED.value.lower():
                logger.info("shelve_server - Server %s already shelved", server_id)
                return

            if server.status.lower() not in [s.lower() for s in valid_states]:
                logger.warning("shelve_server - Server %s in invalid state for shelving: %s", server_id, server.status)
                raise ServerInvalidStateError(
                    server_id=server_id,
                    current_state=server.status,
                    required_states=valid_states,
                )

            logger.info("shelve_server - Shelving server %s", server_id)
            await asyncio.to_thread(lambda: self.connector.conn.compute.shelve_server(server.id))
            logger.info("Server %s shelved", server_id)
        except (OpenStackServerNotFoundError, ServerInvalidStateError, ServerPermissionError) as e:
            logger.error("shelve_server - Error shelving server %s: %s", server_id, str(e))
            raise e
        except Exception as e:
            logger.error("shelve_server - Error shelving server %s: %s", server_id, str(e))
            msg = f"Failed to shelve server {server_id}, {e!s}"
            raise ServerManagementError(msg)

    async def unshelve_server(self, server_id: uuid.UUID) -> None:
        """Unshelve a server by ID"""
        try:
            server = await self.get_server_by_id(server_id)

            await self._verify_user_vm(server, "unshelve_server")

            valid_states = [OpenStackServerStatus.SHELVED.value, OpenStackServerStatus.SHELVED_OFFLOADED.value]

            if server.status.lower() == OpenStackServerStatus.ACTIVE.value.lower():
                logger.info("unshelve_server - Server %s already active", server_id)
                return
            if server.status.lower() not in [s.lower() for s in valid_states]:
                logger.warning(
                    "unshelve_server - Server %s in invalid state for unshelving: %s", server_id, server.status
                )
                raise ServerInvalidStateError(
                    server_id=server_id,
                    current_state=server.status,
                    required_states=valid_states,
                )

            logger.info("unshelve_server - Unshelving server %s", server_id)
            await asyncio.to_thread(lambda: self.connector.conn.compute.unshelve_server(server.id))
            logger.info("Server %s unshelved", server_id)
        except (OpenStackServerNotFoundError, ServerInvalidStateError, ServerPermissionError) as e:
            logger.error("unshelve_server - Error unshelving server %s: %s", server_id, str(e))
            raise e
        except Exception as e:
            logger.error("unshelve_server - Error unshelving server %s: %s", server_id, str(e))
            msg = f"Failed to unshelve server {server_id}, {e!s}"
            raise ServerManagementError(msg)

    async def shelve_servers(self, server_ids: list[uuid.UUID]) -> None:
        """Shelve multiple servers by ID"""
        for server_id in server_ids:
            try:
                await self.shelve_server(server_id)
                logger.info("shelve_servers - Successfully shelved server %s", server_id)
            except Exception as e:
                logger.error("shelve_servers - Error shelving server %s: %s", server_id, e)

    async def reset_server(self, server_id: uuid.UUID) -> None:
        """Reset a server by ID (hard reboot)"""
        try:
            server = await self.get_server_by_id(server_id)

            await self._verify_user_vm(server, "reset_server")

            valid_states = [
                OpenStackServerStatus.ACTIVE.value,
                OpenStackServerStatus.SHUTOFF.value,
                OpenStackServerStatus.ERROR.value,
            ]

            if server.status.lower() not in [s.lower() for s in valid_states]:
                logger.warning("reset_server - Server %s in invalid state for resetting: %s", server_id, server.status)
                raise ServerInvalidStateError(
                    server_id=server_id,
                    current_state=server.status,
                    required_states=valid_states,
                )

            logger.info("reset_server - Resetting server %s", server_id)
            compute_server = await asyncio.to_thread(lambda: self.connector.conn.compute.get_server(server_id))
            await asyncio.to_thread(
                lambda: self.connector.conn.compute.rebuild_server(server.id, compute_server.image.id)
            )
            logger.info("Server %s reset", server_id)
        except (OpenStackServerNotFoundError, ServerInvalidStateError, ServerPermissionError) as e:
            logger.error("reset_server - Error resetting server %s: %s", server_id, str(e))
            raise e
        except Exception as e:
            logger.error("reset_server - Error resetting server %s: %s", server_id, str(e))
            msg = f"Failed to reset server {server_id}, {e!s}"
            raise ServerManagementError(msg)

    async def wait_for_server(
        self,
        server_id: uuid.UUID,
        interval: int = 5,
        wait: int = 60 * 5,
        status: str = OpenStackServerStatus.ACTIVE.value,
    ) -> OpenStackServerRead:
        """Wait for server to reach a specific status"""
        try:
            server = await self.get_server_by_id(server_id)

            await self._verify_user_vm(server, "wait_for_server")

            logger.info("wait_for_server - Waiting for server %s to reach status %s", server_id, status)

            compute_server = await asyncio.to_thread(lambda: self.connector.conn.compute.get_server(server_id))
            compute_server = await asyncio.to_thread(
                lambda: self.connector.conn.compute.wait_for_server(
                    compute_server, interval=interval, wait=wait, status=status
                )
            )

            return OpenStackServerRead.from_openstack_server(compute_server)
        except (OpenStackServerNotFoundError, ServerInvalidStateError, ServerPermissionError) as e:
            logger.error("wait_for_server - Error waiting for server %s: %s", server_id, str(e))
            raise e
        except Exception as e:
            logger.error("wait_for_server - Error waiting for server %s: %s", server_id, str(e))
            msg = f"Failed to wait for server {server_id}, {e!s}"
            raise ServerManagementError(msg)


async def get_openstack_server_config() -> OpenStackServerConfig:
    """Get OpenStack server service configuration"""
    logger.debug("Getting Openstack config")

    return OpenStackServerConfig(
        user_server_metadata={"instance_role": "user-vm"},
    )


async def get_openstack_server_service(
    connector: Annotated[OpenStackConnector, Depends(get_openstack_connector)],
    openstack_server_config: Annotated[OpenStackServerConfig, Depends(get_openstack_server_config)],
) -> OpenStackServerService:
    """Get OpenStack server service instance"""
    return OpenStackServerService(connector, openstack_server_config)
