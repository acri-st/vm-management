# MS framework

This docker image is the base for the microservices, allowing to share the common part of the code and libraries. It also rationalise the version of python. Below you can find the documentation about what is exposed

## logging

To get the logger for your code you need to import the logging module and request a logger from the get logger method.

```python
from utils.logging import get_logger

logger = get_logger("my_feature")

```

## Initialization

If your application requires some initialisation of connection to specific service or a setup to be done only once per startup (caching for instance).
```python
from msfwk.context import register_init
register_init(init)
```

## configuration

The application configuration is loaded at startup of your microservice and then being injected into the context of your application so you can use it immediately.

```
@app.get("/debug")
async def get_api_env(request: Request):
    ...
    logger.debug(request.state.config.databaseUrl)
    ...
```


## Metrics
TODO: based on https://github.com/trallnag/prometheus-fastapi-instrumentator


## Environment variables

- LOG_LEVEL: Change the log level for the entire application
- SLEEP_TIME: allows to reduce or increase the retry period between initalization attempt
- DEV_MODE: deactivate caches
- APP_CONFIG_FILE: config location


## Testing

Make sure you have installed the needed libraries from the root requirements.txt
Run the following command at the root of the project.

Setup
```
pip install -e .
pip install -r requirements.txt
pip install '.[test]'
```

Running tests
```
pytest tests;
```

## Documentation

Regarding the database schema it can generated using the following library
https://pypi.org/project/sqlalchemy-schemadisplay/