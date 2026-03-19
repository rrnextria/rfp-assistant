FROM python:3.12-slim

WORKDIR /app

# Install common package first (better caching)
COPY common /common
RUN pip install --no-cache-dir -e /common

# Install service dependencies
COPY services/model-router/pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy service source
COPY services/model-router/ .

EXPOSE 8006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006", "--reload"]
