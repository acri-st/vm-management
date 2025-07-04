.PHONY: venv

venv:
	python3 -m venv ../.venv
	. ../.venv/bin/activate && \
	python -m pip install --upgrade pip && \
	python -m pip install -r requirements.txt && \
	python -m pip install -r ../base-service/requirements-dev.txt && \
	python -m pip install -r ../base-service/requirements.txt && \
	python -m pip install -e ../base-service 