"""Service for managing server lifecycle operations"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends
from msfwk.mqclient import load_default_rabbitmq_config
from msfwk.notification import NotificationTemplate, send_email_to_mq
from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from pydantic import BaseModel

from vm_management.exceptions import DatabaseError
from vm_management.models.server import DBServerRead
from vm_management.services.auth_service import get_mail_from_desp_user_id
from vm_management.services.sandbox_db_service import SandboxDBService, get_sandbox_db_service
from vm_management.services.server_service import ServerService, get_server_service

logger = get_logger("application")


class LifecycleConfig(BaseModel):
    """Configuration for lifecycle service"""

    suspension_email_threshold_days: float = 25
    suspension_delete_threshold_days: float = 30
    notification_window_days: float = 1  # Only notify if server has been suspended for between X and X+1 days


class LifecycleService:
    """Service for managing server lifecycle operations"""

    def __init__(self, db_service: SandboxDBService, server_service: ServerService, config: LifecycleConfig) -> None:
        self.config = config
        self.db_service = db_service
        self.server_service = server_service

    async def run_lifecycle_checks(self) -> tuple[int, int]:
        """Run lifecycle checks in a loop

        Returns
            tuple[int, int]: Count of (servers to notify, servers to delete)
        """
        try:
            notify_count = await self._check_suspended_servers_for_email()
            delete_count = await self._check_suspended_servers_for_deletion()
        except Exception:
            logger.exception("Error in lifecycle check")
            raise
        else:
            logger.info("Lifecycle checks completed - notify_count=%d, delete_count=%d", notify_count, delete_count)
            return notify_count, delete_count

    async def get_servers_to_suspend(self) -> tuple[list[dict], list[dict]]:
        """Get servers that need notifications and deletion

        Returns
            tuple[list[dict], list[dict]]: (servers to notify, servers to delete) with details
        """
        try:
            # Get servers to be notified - only those in the notification window
            lower_threshold = self.config.suspension_email_threshold_days
            upper_threshold = self.config.suspension_email_threshold_days + self.config.notification_window_days

            notify_servers = await self._get_servers_in_notification_window(lower_threshold, upper_threshold)

            # Get suspended servers older than deletion threshold
            delete_servers = await self.db_service.get_suspended_servers_older_than(
                self.config.suspension_delete_threshold_days
            )

            # Format servers for notification with project details
            notify_servers_details = []
            for server in notify_servers:
                project = await self.server_service.project_service.get_project_by_id(server.project_id)
                notify_servers_details.append(
                    {
                        "server_id": str(server.id),
                        "project_id": str(server.project_id),
                        "project_name": project["name"],
                        "public_ip": server.public_ip,
                        "suspended_since": server.updated_at.isoformat(),
                        "days_suspended": (datetime.now(timezone.utc) - server.updated_at).days,
                    }
                )

            # Format servers for deletion with project details
            delete_servers_details = []
            for server in delete_servers:
                project = await self.server_service.project_service.get_project_by_id(server.project_id)
                delete_servers_details.append(
                    {
                        "server_id": str(server.id),
                        "project_id": str(server.project_id),
                        "project_name": project["name"],
                        "public_ip": server.public_ip,
                        "suspended_since": server.updated_at.isoformat(),
                        "days_suspended": (datetime.now(timezone.utc) - server.updated_at).days,
                    }
                )
        except Exception:
            logger.exception("Error getting lifecycle details")
            raise
        else:
            return notify_servers_details, delete_servers_details

    async def _get_servers_in_notification_window(self, lower_days: float, upper_days: float) -> list[DBServerRead]:
        """Get servers suspended for between lower_days and upper_days

        Args:
            lower_days: Minimum days suspended
            upper_days: Maximum days suspended

        Returns:
            list[DBServerRead]: Servers in the notification window
        """
        lower_cutoff = datetime.now() - timedelta(days=upper_days)  # noqa: DTZ005
        upper_cutoff = datetime.now() - timedelta(days=lower_days)  # noqa: DTZ005

        try:
            # Get servers suspended between lower and upper threshold
            return await self.db_service.get_suspended_servers_in_window(lower_cutoff, upper_cutoff)
        except Exception:
            logger.exception("Failed to get servers in notification window")
            raise

    async def _check_suspended_servers_for_email(self) -> int:
        """Check for suspended servers in the notification window and send notifications

        Returns
            int: Number of servers notified
        """
        lower_threshold = self.config.suspension_email_threshold_days
        upper_threshold = self.config.suspension_email_threshold_days + self.config.notification_window_days

        logger.info("Checking for suspended servers between %s and %s days", lower_threshold, upper_threshold)

        try:
            # Get servers suspended for between threshold and threshold+window
            suspended_servers = await self._get_servers_in_notification_window(lower_threshold, upper_threshold)

            if not suspended_servers:
                logger.info(
                    "No suspended servers found in notification window between %s and %s days",
                    lower_threshold,
                    upper_threshold,
                )
                return 0

            logger.info(
                "Found %d suspended servers in notification window between %s and %s days",
                len(suspended_servers),
                lower_threshold,
                upper_threshold,
            )

            # Send notifications for each suspended server
            for server in suspended_servers:
                project = await self.server_service.project_service.get_project_by_id(server.project_id)
                db_profile = await self.server_service.project_service.get_profile_by_id(project["profile"]["id"])
                user_email = await get_mail_from_desp_user_id(db_profile["desp_owner_id"])

                subject = "VM Inactivity Warning"
                message = f"Your VM {server.name} has been inactive and will be suspended soon if no action is taken."

                await send_email_to_mq(
                    notification_type=NotificationTemplate.GENERIC,
                    user_email=user_email,
                    subject=subject,
                    message=message,
                    user_id=db_profile["desp_owner_id"],
                )

                # Send event notification - to be implemented

            return len(suspended_servers)

        except DatabaseError:
            logger.exception("Failed to check suspended servers")
            raise

    async def _check_suspended_servers_for_deletion(self) -> int:
        """Check for suspended servers older than the deletion threshold and delete them

        Returns
            int: Number of servers deleted
        """
        logger.info("Checking for suspended servers older than %s days", self.config.suspension_delete_threshold_days)

        try:
            # Get suspended servers older than deletion threshold
            suspended_servers = await self.db_service.get_suspended_servers_older_than(
                self.config.suspension_delete_threshold_days
            )

            if not suspended_servers:
                logger.info(
                    "No suspended servers found older than %s days", self.config.suspension_delete_threshold_days
                )
                return 0

            logger.info(
                "Found %d suspended servers older than %s days",
                len(suspended_servers),
                self.config.suspension_delete_threshold_days,
            )

            # Send notifications and delete each suspended server
            for server in suspended_servers:
                project = await self.server_service.project_service.get_project_by_id(server.project_id)
                db_profile = await self.server_service.project_service.get_profile_by_id(project["profile"]["id"])
                user_email = await get_mail_from_desp_user_id(db_profile["desp_owner_id"])

                subject = "VM Suspension Notice"
                message = f"Your VM {server.name} has been scheduled for suspension due to prolonged inactivity."

                await send_email_to_mq(
                    notification_type=NotificationTemplate.GENERIC,
                    user_email=user_email,
                    subject=subject,
                    message=message,
                    user_id=db_profile["desp_owner_id"],
                )

                await self.server_service.delete_server(server.id)

            return len(suspended_servers)

        except DatabaseError:
            logger.exception("Failed to check suspended servers for deletion")
            raise
        except Exception:
            logger.exception("Failed to check suspended servers for deletion")
            raise

    async def _send_suspension_notification(self, server: DBServerRead, project_name: str) -> None:
        """Send a notification about a suspended server

        Args:
            server: The suspended server to send a notification about
            project_name: Name of the project the server belongs to
        """
        logger.info("Sending suspension notification - server_id=%s, project_id=%s", server.id, server.project_id)

        try:
            # Get user email
            project = await self.server_service.project_service.get_project_by_id(server.project_id)
            db_profile = await self.server_service.project_service.get_profile_by_id(project["profile"]["id"])
            user_email = await get_mail_from_desp_user_id(db_profile["desp_owner_id"])

            # Prepare notification data
            days_until_deletion = (
                self.config.suspension_delete_threshold_days - self.config.suspension_email_threshold_days
            )
            notification_data = (
                f"Dear user,\n\n"
                f"Your sandbox VM (ID: {server.id}) in project {project_name} "
                f"has been inactive for {self.config.suspension_email_threshold_days} days.\n\n"
                f"If no activity is detected in the next {days_until_deletion} days, "
                f"the VM will be automatically deleted.\n\n"
                f"Please take appropriate action if you wish to keep this VM.\n\n"
                f"VM Details:\n"
                f"- Project: {project_name}\n"
                f"- Server ID: {server.id}\n"
                f"- Server IP: {server.public_ip}\n"
                f"- Suspended since: {server.updated_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Best regards,\nDESP Team"
            )

            subject = (
                f"[DESP] Action Required: Sandbox VM for project {project_name} "
                f"will be deleted in {days_until_deletion} days"
            )

            logger.debug("Sending notification to %s with data: %s", user_email, notification_data)
            await send_email_to_mq(
                notification_type=NotificationTemplate.GENERIC,
                user_email=user_email,
                subject=subject,
                message=notification_data,
                user_id=db_profile["desp_owner_id"],
            )

        except Exception:
            logger.exception("Failed to send suspension notification - server_id=%s", server.id)


async def get_lifecycle_config() -> LifecycleConfig:
    """Get lifecycle configuration from app config

    Returns
        LifecycleConfig: Lifecycle configuration
    """
    config = read_config().get("services", {}).get("vm-management", {}).get("lifecycle", {})
    load_default_rabbitmq_config(read_config())
    suspension_email_threshold_days = config.get("suspension_email_threshold_days", 25)
    suspension_delete_threshold_days = config.get("suspension_delete_threshold_days", 30)

    return LifecycleConfig(
        suspension_email_threshold_days=suspension_email_threshold_days,
        suspension_delete_threshold_days=suspension_delete_threshold_days,
    )


async def get_lifecycle_service(
    config: Annotated[LifecycleConfig, Depends(get_lifecycle_config)],
    db_service: Annotated[SandboxDBService, Depends(get_sandbox_db_service)],
    server_service: Annotated[ServerService, Depends(get_server_service)],
) -> LifecycleService:
    """Get lifecycle service

    Args:
        config: Lifecycle configuration
        db_service: Sandbox DB service
        server_service: Server service

    Returns:
        LifecycleService: Lifecycle service
    """
    return LifecycleService(db_service=db_service, server_service=server_service, config=config)
