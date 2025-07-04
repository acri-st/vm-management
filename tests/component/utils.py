from typing import AsyncGenerator
from unittest.mock import  MagicMock, Mock, patch
import pytest
from sqlalchemy import Column, MetaData, Table
from msfwk.schema.schema import Schema
from msfwk.utils.logging import ACRILoggerAdapter, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger: ACRILoggerAdapter = get_logger("test.utils")

@pytest.fixture(autouse=True)
async def mock_database_class() -> AsyncGenerator[Schema, None] :
    """Mock the database and return the session result can be mocked
    record = MagicMock(MappingResult)
    record._mapping = {"field1":1}
    mock_database_class.tables= {"mytable":fake_table("mytable",["col1","coln"])}
    mock_database_class.get_async_session().execute.return_value=[record]
    """
    logger.info("Mocking the database session")
    with patch("msfwk.database.get_schema") as mock:
        schema = Schema("postgresql+asyncpg://test:test@test:5432/test")
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        schema.get_async_session = Mock(return_value=session)
        mock.return_value = schema
        yield schema
    logger.info("Mocking database reset")
    
def fake_table(name:str,columns:list[str])-> Table:
    return Table(name,MetaData(),*[Column(col) for col in columns])