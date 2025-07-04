from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch

from msfwk import database
from despsharedlibrary.schemas.sandbox_schema import SandboxSchema
from msfwk.utils.logging import get_logger
from unittest.mock import MagicMock, Mock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine.result import Result
from sqlalchemy.exc import SQLAlchemyError

from msfwk.utils.conftest import mock_read_config
from config import test_vm_management_config
#from vm_management.interfaces import InstallableApplication
from mock_application_database_call import all_applications_database_test


logger = get_logger("test")

@pytest.fixture
async def mock_database_class():
    database.get_schema = Mock(return_value=SandboxSchema("postgresql+asyncpg://test:test@test:5432/test"))
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    database.get_schema().get_async_session = Mock(return_value=session)
    return session

@pytest.mark.component
def test_get_applications(mock_read_config, mock_database_class):
    from vm_management.main import app
    
    mock_read_config.return_value = test_vm_management_config
    record = MagicMock(spec=Result)
    mock_all_method = Mock(return_value=all_applications_database_test)
    mock_mapping = Mock()
    mock_mapping.all = mock_all_method
    record.mappings.return_value = mock_mapping
    mock_database_class.execute.return_value=record

    with TestClient(app) as client:
        response = client.get("/applications")
        logger.debug(response.json())
        assert response.status_code == 200
        assert response.json() == {"data": all_applications_database_test}


@patch(
    "sqlalchemy.ext.asyncio.AsyncSession.execute",
    side_effect=SQLAlchemyError("test")
)
@pytest.mark.component
@pytest.mark.skip(reason="The test has no mock for the database and failed")
def test_get_application_with_sqlachemy_error(mock_execute_error, mock_database_class):
    from vm_management.main import app

    with TestClient(app) as client:
        response = client.get("/applications")
        logger.debug(response.json())
        assert response.status_code == 500