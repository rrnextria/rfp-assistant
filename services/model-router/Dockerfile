FROM python:3.12-slim
WORKDIR /app
COPY common /common
RUN pip install --no-cache-dir /common

COPY scripts/install_deps.py /install_deps.py
COPY services/model-router/pyproject.toml .
RUN python3 /install_deps.py
COPY services/model-router/ .
EXPOSE 8006
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006", "--reload"]
