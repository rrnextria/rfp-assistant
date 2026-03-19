FROM python:3.12-slim

WORKDIR /app

# Install common package first (better caching)
COPY common /common
RUN pip install --no-cache-dir -e /common

# Install service dependencies
COPY services/adapters/pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy service source
COPY services/adapters/ .

EXPOSE 8007

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007", "--reload"]
