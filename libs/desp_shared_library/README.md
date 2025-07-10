# despsharedlibrary

Hold the python code shared across multiple microservice like schema or specific method for a project

## Prerequisite

install UV to manage your dependencies

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation
Ensure you have in your system a env variable __UV_INDEX_DSY_PIP_PASSWORD__ \(Ask for the value\)

In your project.toml
```toml
dependencies = [
    ...
    "despsharedlibrary>=1.0.0"
]
[tool.uv.sources]
despsharedlibrary = { index  = "dsy-pip" }

[[tool.uv.index]]
name = "dsy-pip"
url = "https://gitlab.acri-cwa.fr/api/v4/projects/782/packages/pypi/simple"
username = "__token__"
default = false
```

```bash
uv sync
```