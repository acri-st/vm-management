"""Auth service"""

from msfwk.exceptions import DespGenericError
from msfwk.request import HttpClient
from msfwk.utils.logging import get_logger

from vm_management.constants import AUTH_ERROR

logger = get_logger("auth_service")


async def get_mail_from_desp_user_id(desp_user_id: str) -> str:
    """Get the mail from the desp user id

    Args:
        desp_user_id (str): id of the desp user

    Returns:
        str: mail of the desp user
    """
    try:
        http_client = HttpClient()
        async with (
            http_client.get_service_session("auth") as http_session,
            http_session.get(f"/profile/{desp_user_id}") as response,
        ):
            if response.status != 200:  # noqa: PLR2004
                logger.error(await response.json())
            else:
                logger.info("Mail fetched !")

            response_content = await response.json()
            logger.info("Reponse from the service: %s", response_content)

            return response_content["data"]["profile"]["email"]

    except Exception as E:
        msg = f"Exception while contacting auth service : {E}"
        logger.exception(msg)
        raise DespGenericError(
            status_code=500,
            message=f"Could not call auth service : {E}",
            code=AUTH_ERROR,
        ) from None
