"""Manage the API entrypoints"""

import logging

from msfwk.application import app
from msfwk.context import current_config, register_init
from msfwk.mqclient import load_default_rabbitmq_config
from msfwk.utils.logging import get_logger

from vm_management.services.guacamole_service import setup_guacamole_group

from .routes.v1.guacemole import router as guacamole_router
from .routes.v1.metrics import router as prometheus_router
from .routes.v1.openstack_servers import router as openstack_servers_router
from .routes.v1.servers import router as servers_router

logger = get_logger("application")

logging.getLogger("keystoneauth").setLevel(logging.WARNING)
logging.getLogger("stevedore").setLevel(logging.WARNING)
logging.getLogger("openstack").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)

###############
#     VM
###############


async def init(config: dict) -> bool:
    """Init"""
    logger.info("Initialising vm management ...")
    load_succeded = load_default_rabbitmq_config()
    current_config.set(config)
    if load_succeded:
        logger.info("RabbitMQ config loaded")
    else:
        logger.error("Failed to load rabbitmq config")
    return load_succeded


# Register the init function
register_init(setup_guacamole_group)
register_init(init)

app.include_router(servers_router)
app.include_router(openstack_servers_router)
app.include_router(guacamole_router)
app.include_router(prometheus_router)
