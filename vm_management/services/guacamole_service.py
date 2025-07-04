"""Apache Guacamole API service for VM management"""

from typing import Annotated, Any

import httpx
from fastapi import Depends
from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from pydantic import BaseModel

logger = get_logger("application")

JSON_APPLICATION_CONTENT_TYPE = "application/json"


class GuacamoleConfig(BaseModel):
    """Configuration model for Guacamole service"""

    base_url: str
    admin_username: str
    admin_password: str
    timeout: int = 30
    group_name: str
    rdp_port: str = "3389"
    ssh_port: str = "22"
    guacd_hostname: str = "guacamole-guacd"


class GuacamoleAuthResponse(BaseModel):
    """Response model for Guacamole authentication"""

    auth_token: str
    data_source: str
    username: str = ""
    available_data_sources: list[str] = []


class BaseConnectionParameters(BaseModel):
    """Base parameters for Guacamole connections"""

    # Common parameters for all protocols
    hostname: str = ""
    port: str = ""
    username: str = ""
    password: str = ""

    # Recording
    recording_path: str = ""
    recording_name: str = ""
    recording_exclude_output: str = ""
    recording_exclude_mouse: str = ""
    recording_include_keys: str = ""
    create_recording_path: str = ""

    # Display
    read_only: str = ""
    swap_red_blue: str = ""
    cursor: str = ""
    color_depth: str = ""

    # Clipboard
    clipboard_encoding: str = ""
    disable_copy: str = ""
    disable_paste: str = ""

    # Other common params
    timezone: str | None = None
    dest_port: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict with parameter naming convention"""
        result = {}
        for key, value in self.model_dump().items():
            param_key = key.replace("_", "-")
            result[param_key] = value
        return result


class GuacamoleConnectionParameters(BaseConnectionParameters):
    """Parameters for Guacamole SSH connection"""

    # SSH-specific parameters
    private_key: str = ""
    passphrase: str = ""
    command: str = ""
    color_scheme: str = ""
    font_name: str = ""
    font_size: str = ""

    # Optional SSH parameters
    enable_sftp: str = ""
    sftp_port: str = ""
    sftp_server_alive_interval: str = ""
    enable_audio: str = ""
    scrollback: str = ""
    server_alive_interval: str = ""
    backspace: str = ""
    terminal_type: str = ""
    create_typescript_path: str = ""
    host_key: str = ""
    locale: str = ""
    typescript_path: str = ""
    typescript_name: str = ""
    sftp_root_directory: str = ""


class RDPConnectionParameters(BaseConnectionParameters):
    """Parameters for Guacamole RDP connection"""

    # RDP-specific authentication
    domain: str = ""

    # Gateway
    gateway_hostname: str = ""
    gateway_port: str = ""
    gateway_username: str = ""
    gateway_password: str = ""
    gateway_domain: str = ""

    # Security
    security: str = "any"
    disable_auth: str = ""
    ignore_cert: str = "true"

    # Display settings
    server_layout: str = ""
    console: str = ""
    width: str = ""
    height: str = ""
    dpi: str = ""
    resize_method: str = ""

    # Audio settings
    console_audio: str = ""
    disable_audio: str = ""
    enable_audio_input: str = ""

    # Redirection
    enable_printing: str = ""
    printer_name: str = ""
    enable_drive: str = ""
    drive_name: str = ""
    drive_path: str = ""
    create_drive_path: str = ""

    # Performance settings
    enable_wallpaper: str = ""
    enable_theming: str = ""
    enable_font_smoothing: str = ""
    enable_full_window_drag: str = ""
    enable_desktop_composition: str = ""
    enable_menu_animations: str = ""
    disable_bitmap_caching: str = ""
    disable_offscreen_caching: str = ""
    disable_glyph_caching: str = ""

    # Remote app
    remote_app: str = ""
    remote_app_dir: str = ""
    remote_app_args: str = ""

    # Advanced options
    load_balance_info: str = ""
    initial_program: str = ""
    client_name: str = ""
    preconnection_id: str = ""
    preconnection_blob: str = ""
    static_channels: str = ""

    # SFTP
    sftp_hostname: str = ""
    sftp_host_key: str = ""
    sftp_username: str = ""
    sftp_password: str = ""
    sftp_private_key: str = ""
    sftp_passphrase: str = ""
    sftp_root_directory: str = ""
    sftp_directory: str = ""


class GuacamoleConnectionAttributes(BaseModel):
    """Attributes for Guacamole connection"""

    max_connections: str = ""
    max_connections_per_user: str = ""
    weight: str = ""
    failover_only: str = ""
    guacd_port: str = ""
    guacd_encryption: str = ""
    guacd_hostname: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict with attribute naming convention"""
        result = {}
        for key, value in self.model_dump().items():
            attr_key = key.replace("_", "-")
            result[attr_key] = value
        return result


class GuacamoleService:
    """Service for interacting with Apache Guacamole API"""

    def __init__(self, config: GuacamoleConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.auth_token = None
        self.data_source = None

    async def authenticate(self, username: str | None = None, password: str | None = None) -> GuacamoleAuthResponse:
        """Authenticate with Guacamole API and get a token

        Args:
            username: Optional username override (defaults to config username)
            password: Optional password override (defaults to config password)

        Returns:
            GuacamoleAuthResponse with auth token and data source
        """
        username = username or self.config.admin_username
        password = password or self.config.admin_password

        url = f"{self.base_url}/api/tokens"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(url, data={"username": username, "password": password})

                response.raise_for_status()
                data = response.json()

                # Store the token and data source for future API calls
                self.auth_token = data.get("authToken")
                self.data_source = data.get("dataSource")

                return GuacamoleAuthResponse(
                    auth_token=self.auth_token,
                    data_source=self.data_source,
                    username=data.get("username", ""),
                    available_data_sources=data.get("availableDataSources", []),
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during Guacamole authentication: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error during Guacamole authentication: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Guacamole authentication: {e!s}")
            raise

    async def create_user_group(self, identifier: str, attributes: dict[str, Any] = None) -> dict[str, Any]:
        """Create a new user group in Guacamole

        Args:
            identifier: The unique identifier for the user group
            attributes: Optional attributes for the user group, defaults to {"disabled": ""}

        Returns:
            The response from the Guacamole API
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/userGroups"

        # Default attributes if none provided
        if attributes is None:
            attributes = {"disabled": ""}

        payload = {"identifier": identifier, "attributes": attributes}

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": JSON_APPLICATION_CONTENT_TYPE},
                    params={"token": self.auth_token},
                )

                response.raise_for_status()
                logger.info(f"Created user group: {identifier}")

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating user group: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error creating user group: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating user group: {e!s}")
            raise

    async def assign_permissions_to_user_group(
        self,
        group_identifier: str,
        connection_permissions: list[str] = None,
        system_permissions: list[str] = None,
        connection_id: str = None,
    ) -> dict[str, Any]:
        """Assign permissions to a user group

        Args:
            group_identifier: The identifier of the user group
            connection_permissions: List of connection permissions (e.g. ["READ"])
            system_permissions: List of system permissions (e.g. ["CREATE_USER", "ADMINISTER"])
            connection_id: Optional specific connection ID for connection permissions

        Returns:
            Empty dict if successful
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/userGroups/{group_identifier}/permissions"

        operations = []

        # Add connection permissions
        if connection_permissions:
            for permission in connection_permissions:
                connection_path = f"/connectionPermissions/{connection_id or ''}"
                operations.append({"op": "add", "path": connection_path, "value": permission})

        # Add system permissions
        if system_permissions:
            for permission in system_permissions:
                operations.append({"op": "add", "path": "/systemPermissions", "value": permission})

        if not operations:
            logger.warning("No permissions specified for group assignment")
            return {}

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.patch(
                    url,
                    json=operations,
                    headers={"Content-Type": JSON_APPLICATION_CONTENT_TYPE},
                    params={"token": self.auth_token},
                )

                response.raise_for_status()
                logger.info(f"Assigned permissions to user group: {group_identifier}")

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error assigning permissions: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error assigning permissions: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error assigning permissions: {e!s}")
            raise

    async def create_user(self, username: str, password: str, attributes: dict[str, Any] = None) -> dict[str, Any]:
        """Create a new user in Guacamole

        Args:
            username: Username for the new user
            password: Password for the new user
            attributes: Optional user attributes

        Returns:
            The response from the Guacamole API
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/users"

        # Use provided attributes or defaults
        user_attributes = attributes or {}

        payload = {"username": username, "password": password, "attributes": user_attributes}

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": JSON_APPLICATION_CONTENT_TYPE},
                    params={"token": self.auth_token},
                )

                response.raise_for_status()
                logger.info("Created user: %s", username)

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error creating user: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error creating user: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error creating user: %s", e)
            raise

    async def delete_user(self, username: str) -> dict[str, Any]:
        """Delete a user from Guacamole

        Args:
            username: The username to delete

        Returns:
            Empty dict if successful
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/users/{username}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.delete(url, params={"token": self.auth_token})

                response.raise_for_status()
                logger.info("Deleted user: %s", username)

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error deleting user: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error deleting user: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error deleting user: %s", e)
            raise

    async def assign_user_to_groups(self, username: str, group_identifiers: list[str]) -> dict[str, Any]:
        """Assign a user to one or more user groups

        Args:
            username: The username to assign to groups
            group_identifiers: List of group identifiers to assign the user to

        Returns:
            Empty dict if successful
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/users/{username}/userGroups"

        operations = []

        # Create operations for each group
        for group_id in group_identifiers:
            operations.append({"op": "add", "path": "/", "value": group_id})

        if not operations:
            logger.warning(f"No groups specified for user assignment: {username}")
            return {}

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.patch(
                    url,
                    json=operations,
                    headers={"Content-Type": JSON_APPLICATION_CONTENT_TYPE},
                    params={"token": self.auth_token},
                )

                response.raise_for_status()
                logger.info("Assigned user %s to %d groups", username, len(group_identifiers))

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error assigning user to groups: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error assigning user to groups: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error assigning user to groups: %s", e)
            raise

    async def delete_connection(self, connection_id: str) -> dict[str, Any]:
        """Delete a connection from Guacamole

        Args:
            connection_id: The ID of the connection to delete

        Returns:
            Empty dict if successful
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/connections/{connection_id}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.delete(url, params={"token": self.auth_token})

                response.raise_for_status()
                logger.info("Deleted connection: %s", connection_id)

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error deleting connection: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error deleting connection: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error deleting connection: %s", e)
            raise

    async def list_connections(self) -> dict[str, Any]:
        """List all connections in Guacamole

        Returns
            Dictionary of connections with their details
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/connections"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(url, params={"token": self.auth_token})

                response.raise_for_status()
                connections = response.json()
                logger.info("Retrieved %d connections", len(connections) if connections else 0)

                return connections

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error listing connections: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error listing connections: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error listing connections: %s", e)
            raise

    async def create_connection(
        self,
        name: str,
        protocol: str = "ssh",
        parent_identifier: str = "ROOT",
        parameters: BaseConnectionParameters | None = None,
        attributes: GuacamoleConnectionAttributes = None,
    ) -> dict[str, Any]:
        """Create a new connection in Guacamole

        Args:
            name: Name of the connection
            protocol: Protocol to use (ssh, rdp, vnc, etc.)
            parent_identifier: Parent identifier (e.g. "ROOT" or a connection group ID)
            parameters: Connection parameters
            attributes: Connection attributes

        Returns:
            The response from the Guacamole API
        """
        if self.auth_token is None or self.data_source is None:
            await self.authenticate()

        url = f"{self.base_url}/api/session/data/{self.data_source}/connections"

        # Select appropriate parameter class based on protocol
        if parameters is None:
            parameters = RDPConnectionParameters() if protocol.lower() == "rdp" else GuacamoleConnectionParameters()

        # Use default attributes if none provided
        conn_attributes = attributes or GuacamoleConnectionAttributes()

        payload = {
            "parentIdentifier": parent_identifier,
            "name": name,
            "protocol": protocol,
            "parameters": parameters.to_dict(),
            "attributes": conn_attributes.to_dict(),
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": JSON_APPLICATION_CONTENT_TYPE},
                    params={"token": self.auth_token},
                )

                response.raise_for_status()
                logger.info("Created connection: %s (%s)", name, protocol)

                return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error creating connection: %s - %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error creating connection: %s", e)
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating connection: {e!s}")
            raise

    async def create_user_and_assign_to_group(self, username: str, password: str, group_identifier: str) -> None:
        """Create a new user and assign to a group

        Args:
            username: The username to create
            password: The password for the new user
            group_identifier: The identifier of the group to assign the user to

        Returns:
            The response from the Guacamole API
        """
        logger.info("Creating Guacamole user and assigning to group: %s", username)
        try:
            await self.create_user(username, password)
            await self.assign_user_to_groups(username, [group_identifier])

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "already exists" in e.response.text:
                logger.info("User already exists")
                return
        except Exception as e:
            logger.error("Unexpected error creating Guacamole user and assigning to group: %s", str(e))
            # raise
        logger.info("Guacamole user created and group assigned successfully")


async def get_guacamole_config() -> GuacamoleConfig:
    """Get Guacamole configuration"""
    environment = read_config().get("general").get("application_environment")
    config = read_config().get("services").get("vm-management").get("guacamole")

    return GuacamoleConfig(
        base_url=config.get("base_url"),
        admin_username=config.get("username"),
        admin_password=config.get("password"),
        group_name=f"group-desp-{environment}",
    )


async def get_guacamole_service(config: Annotated[GuacamoleConfig, Depends(get_guacamole_config)]) -> GuacamoleService:
    """Get Guacamole service instance"""
    return GuacamoleService(config=config)


async def setup_guacamole_group(config: dict) -> bool:
    """Setup Guacamole group"""
    logger.info("Setting up Guacamole group")

    guac_config = await get_guacamole_config()
    guacamole_service = GuacamoleService(guac_config)

    try:
        # Create group
        group_name = guac_config.group_name
        await guacamole_service.create_user_group(identifier=group_name)

        # Assign permissions to group
        await guacamole_service.assign_permissions_to_user_group(
            group_identifier=group_name, system_permissions=["CREATE_CONNECTION"]
        )
        logger.info("Guacamole group setup completed successfully")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400 and "already exists" in e.response.text:
            # 400 Bad Request with "already exists" means group already exists
            logger.info("Guacamole group already exists")

            # Try assigning permissions even if group exists
            try:
                await guacamole_service.assign_permissions_to_user_group(
                    group_identifier=group_name,
                    system_permissions=["CREATE_CONNECTION"],
                )
                logger.info("Permissions assigned to existing group")
            except Exception as perm_error:
                logger.error("Failed to assign permissions to existing group: %s", str(perm_error))
                raise
        else:
            logger.error("Failed to setup Guacamole group: %s", str(e))
            raise
    except Exception as e:
        logger.error("Unexpected error during Guacamole group setup: %s", str(e))
        raise
    return True
