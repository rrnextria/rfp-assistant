FROM python:3.12-slim

WORKDIR /app

# Install common package first (better caching)
COPY common /common
RUN pip install --no-cache-dir -e /common

# Install service dependencies
COPY services/rbac-service/pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy service source
COPY services/rbac-service/ .

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--reload"]
