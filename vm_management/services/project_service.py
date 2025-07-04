"""Service for interacting with the project management API"""

from uuid import UUID

import aiohttp
from msfwk.request import HttpClient
from msfwk.utils.logging import get_logger

from vm_management.exceptions import ProjectNotFoundError, ProjectServiceError

logger = get_logger("application")

# HTTP status codes
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201


class ProjectService:
    """Service for interacting with the project management API"""

    def __init__(self, http_client: HttpClient) -> None:
        self.http_client = http_client

    async def get_project_by_id(self, project_id: UUID) -> dict:
        """Get project details by project ID

        Args:
            project_id (UUID): The ID of the project to retrieve

        Returns:
            Dict: The project data

        Raises:
            aiohttp.ClientResponseError: If the HTTP request fails
            aiohttp.ClientConnectionError: If there's a connection error
        """
        logger.debug("Getting project - project_id=%s", project_id)
        url = f"/projects/{project_id}"
        try:
            async with (
                self.http_client.get_service_session("project-management") as session,
                session.get(url) as response,
            ):
                if response.status == HTTP_STATUS_NOT_FOUND:
                    error_msg = f"Project with ID {project_id} not found"
                    raise ProjectNotFoundError(error_msg)
                if response.status not in (HTTP_STATUS_OK, HTTP_STATUS_CREATED):
                    response_content = await response.json()
                    logger.debug(
                        "Project management API response - status=%s, response=%s",
                        response.status,
                        response_content,
                    )
                    error_msg = f"Project service returned status {response.status}"
                    raise ProjectServiceError(error_msg)

                result = await response.json()
                return result["data"]
        except aiohttp.ClientResponseError as e:
            if e.status == HTTP_STATUS_NOT_FOUND:
                error_msg = f"Project with ID {project_id} not found"
                raise ProjectNotFoundError(error_msg) from e
            error_msg = f"Project service error: {e}"
            raise ProjectServiceError(error_msg) from e
        except aiohttp.ClientError as e:
            error_msg = f"Connection error to project service: {e}"
            raise ProjectServiceError(error_msg) from e
        except (ValueError, KeyError) as e:
            error_msg = f"Unexpected error from project service: {e}"
            raise ProjectServiceError(error_msg) from e

    async def get_profile_by_id(self, user_id: UUID) -> dict:
        """Get project details by project ID

        Args:
            user_id (UUID): The ID of the user to retrieve

        Returns:
            Dict: The project data

        Raises:
            aiohttp.ClientResponseError: If the HTTP request fails
            aiohttp.ClientConnectionError: If there's a connection error
        """
        logger.debug("Getting profile - user_id=%s", user_id)
        url = f"/profiles/{user_id}"
        try:
            async with (
                self.http_client.get_service_session("project-management") as session,
                session.get(url) as response,
            ):
                if response.status == HTTP_STATUS_NOT_FOUND:
                    error_msg = f"Profile with ID {user_id} not found"
                    raise ProjectNotFoundError(error_msg)
                if response.status not in (HTTP_STATUS_OK, HTTP_STATUS_CREATED):
                    response_content = await response.json()
                    logger.debug(
                        "Project management API response - status=%s, response=%s",
                        response.status,
                        response_content,
                    )
                    error_msg = f"Project service returned status {response.status}"
                    raise ProjectServiceError(error_msg)

                result = await response.json()
                return result["data"]
        except aiohttp.ClientResponseError as e:
            if e.status == HTTP_STATUS_NOT_FOUND:
                error_msg = f"Profile with ID {user_id} not found"
                raise ProjectNotFoundError(error_msg) from e
            error_msg = f"Project service error: {e}"
            raise ProjectServiceError(error_msg) from e
        except aiohttp.ClientError as e:
            error_msg = f"Connection error to project service: {e}"
            raise ProjectServiceError(error_msg) from e
        except (ValueError, KeyError) as e:
            error_msg = f"Unexpected error from project service: {e}"
            raise ProjectServiceError(error_msg) from e


async def get_project_service() -> ProjectService:
    """Returns an instance of ProjectService"""
    return ProjectService(http_client=HttpClient())
