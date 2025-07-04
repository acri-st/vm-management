import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch
from asyncio import TimeoutError
from aiohttp import ClientConnectionError, ClientResponseError, InvalidURL, ContentTypeError, ClientError
from fastapi.testclient import TestClient

from msfwk.utils.conftest import load_json, mock_read_config  # noqa: F401
from msfwk.utils.logging import ACRILoggerAdapter, get_logger

logger: ACRILoggerAdapter = get_logger("test")

mock_pytest_ip = "http://testserver"

def handle_vm_requests(path: str,
        query_data=None,
        post_data=None,
        raw: bool = False,
        streamed: bool = False,
        files=None,
        timeout=None,
        obey_rate_limit: bool = True,
        retry_transient_errors = None,
        max_retries: int = 10,
        **kwargs):
    logger.debug("=====>Catching %s %s",path,query_data or post_data)
    if path == f'{mock_pytest_ip}/delete_sandbox':
        logger.debug("=====>Mocking %s %s",path,query_data or post_data)
        mocked_response = MagicMock(spec=aiohttp.ClientResponse)
        mocked_response.status_code = 200
        mocked_response.status = 200
        mocked_response.json = AsyncMock(return_value=load_json(__file__, 'post_delete_sandbox.json'))
        mocked_response.__aenter__.return_value = mocked_response
        return mocked_response
    logger.debug("=====>Not Mocked %s %s",path,query_data or post_data)

@pytest.mark.component
def test_delete_vm(mock_read_config):  # noqa: F811
    from vm_management.main import app
    mock_read_config.return_value = {
            "services":{
                "vm-management":{
                    "active_directory_bridge_url": mock_pytest_ip
                }
            }
        }
    with patch("aiohttp.ClientSession") as mock:
        mock.return_value = mock # On new instance creation
        mock.__aenter__.return_value= mock # inside a with
        mock.post = MagicMock(side_effect=handle_vm_requests)

        with TestClient(app) as client:
            data = {
                "username": "desp-aas-pytest-common-name-aka-username",
                "pool_name": "desp-aas-pytest-pool_name"

            }
            response = client.post("/delete_vm",json=data)
            print(response.json())
            assert response.status_code == 200
            assert response.json()['data'] ==  {
                'message': 'VM delete successful'
            } 

@pytest.mark.component
def test_delete_vm_aio_error(mock_read_config):  # noqa: F811
    from vm_management.main import app
    mock_read_config.return_value = {
            "services":{
                "vm-management":{
                    "active_directory_bridge_url": mock_pytest_ip
                }
            }
        }
    
    error_list = [TimeoutError("TimeoutError"), 
                  ClientConnectionError("ClientConnectionError"),
                  #ClientResponseError("ClientResponseError"),
                  InvalidURL("InvalidURL"),
                  #ContentTypeError("ContentTypeError"),
                  ClientError("ClientError"),
                  KeyError("KeyError")
                  ]
    
    for error in error_list:
        with patch("aiohttp.ClientSession") as mock:
            mock.return_value = mock # On new instance creation
            mock.__aenter__.return_value= mock # inside a with
            mock.post = MagicMock(side_effect=error)

            with TestClient(app) as client:
                data = {
                    "username": "desp-aas-pytest-common-name-aka-username",
                    "pool_name": "desp-aas-pytest-pool_name"
                }
                try:
                    response = client.post("/delete_vm",json=data)
                    print(response.json())
                    print(error)
                    assert False
                except:
                    assert True
