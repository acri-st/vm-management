from fastapi.testclient import TestClient
import pytest

from msfwk.utils.logging import get_logger
from unittest.mock import MagicMock, Mock
from sqlalchemy.engine.result import Result

from msfwk.utils.conftest import mock_read_config
from msfwk.schema.schema import Schema
from config import test_vm_management_config
from mock_application_database_call import all_applications_database_test
from utils import fake_table, mock_database_class

logger = get_logger("test")

@pytest.mark.component
@pytest.mark.only
def test_get_context(mock_read_config, mock_database_class:Schema):
    from vm_management.main import app
    
    mock_read_config.return_value = test_vm_management_config
    record = MagicMock(spec=Result)
    mock_all_method = Mock(return_value=all_applications_database_test)
    mock_mapping = Mock()
    mock_mapping.all = mock_all_method
    record.mappings.return_value = mock_mapping
    mock_database_class.get_async_session().execute.return_value=record
    mock_database_class.tables = {
      "application_x_project":fake_table(
        "application_x_project",
        ["projectId"]
      ),
      "Applications":fake_table(
        "Applications",
        []
      ),
      "Projects":fake_table(
        "Projects",
        ["project_id","vmId"]
      ),
      "Repositories":fake_table(
        "Repositories",
        []
      )
    }
    with TestClient(app) as client:
        response = client.get("/context/75bbe73a-be86-e248-840d-c126dfd03976")
        logger.debug(response.json())
        assert response.status_code == 200
        assert response.json() == {"data": {"content":"""---
- name: Desp Ansible Playbook
  hosts: localhost
  become: yes
  tasks:
    - name: Update the apt package list
      apt:
        update_cache: yes
    - name: Install Application1
      dnf:
        name: curl
        state: present
            
    - name: Install Application2
      script    
""","sha":"ebb6ee76f178509c9158b590f04c12696edfeb5a5a4a50fd3aa8405469e2f5da"}}

