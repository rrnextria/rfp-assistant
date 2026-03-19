FROM python:3.12-slim

WORKDIR /app

# Install common package
COPY common /common
RUN pip install --no-cache-dir -e /common

# Copy service source then install (hatchling needs source present for editable installs)
COPY services/orchestrator/ .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
