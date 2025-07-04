"""Database connector for sandbox environments using SQLAlchemy in async mode"""

import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends
from msfwk.utils.config import read_config
from msfwk.utils.logging import get_logger
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

logger = get_logger("application")


class SandboxDBConfig(BaseModel):
    """Configuration model for Sandbox DB"""

    db_url: str
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False


class SandboxDBConnector:
    """Manages database connections for sandbox environments using SQLAlchemy in async mode"""

    _instance: Optional["SandboxDBConnector"] = None
    _connection_timeout: int = 10
    _lock = asyncio.Lock()

    def __init__(
        self,
        db_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self.db_url = db_url
        self.engine_params = {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "echo": echo,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "connect_args": {"timeout": self._connection_timeout},
        }
        self._engine: AsyncEngine | None = None

    async def engine(self) -> AsyncEngine:
        """Get or create the database engine"""
        if self._engine is None:
            async with self._lock:
                if self._engine is None:
                    try:
                        self._engine = create_async_engine(self.db_url, **self.engine_params)
                        logger.info("Database connection established.")
                    except OperationalError as e:
                        logger.error("Operational error connecting to database: %s", e)  # noqa: TRY400
                        raise
                    except socket.gaierror as e:
                        logger.error("DNS resolution error connecting to database: %s", e)  # noqa: TRY400
                        msg = f"Database connection failed - DNS resolution error: {e}"
                        raise SQLAlchemyError(msg) from e
                    except Exception as e:
                        logger.exception("Unexpected error connecting to database.")
                        msg = f"Database connection failed: {e}"
                        raise SQLAlchemyError(msg) from e
        return self._engine

    async def session(self) -> AsyncSession:
        """Create a new session"""
        engine = await self.engine()
        return AsyncSession(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session_context(self, begin_transaction: bool = False) -> AsyncGenerator[AsyncSession, None]:  # noqa: FBT001, FBT002
        """Context manager for database sessions"""
        session = await self.session()
        async with session:
            if begin_transaction:
                async with self.begin_transaction(session):
                    yield session
            else:
                yield session

    @asynccontextmanager
    async def begin_transaction(self, session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for transactions"""
        async with session.begin() as transaction:
            yield transaction


def get_sandbox_db_config() -> SandboxDBConfig:
    """Returns Sandbox DB configuration"""
    config = read_config()
    db_url = config.get("database_sandbox")
    echo = config.get("general").get("debug", False)

    return SandboxDBConfig(db_url=db_url, echo=echo)


async def get_sandbox_db_connector(
    db_config: Annotated[SandboxDBConfig, Depends(get_sandbox_db_config)],
) -> SandboxDBConnector:
    """Returns a singleton instance of SandboxDBConnector"""
    if not SandboxDBConnector._instance:  # noqa: SLF001
        try:
            SandboxDBConnector._instance = SandboxDBConnector(  # noqa: SLF001
                db_url=db_config.db_url,
                pool_size=db_config.pool_size,
                max_overflow=db_config.max_overflow,
                echo=db_config.echo,
            )
            await SandboxDBConnector._instance.engine()  # noqa: SLF001
        except SQLAlchemyError as e:
            logger.error("Database connection failed: %s", e)  # noqa: TRY400
            raise
    return SandboxDBConnector._instance  # noqa: SLF001
