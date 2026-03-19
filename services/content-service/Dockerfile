FROM python:3.12-slim

WORKDIR /app

# Install common package
COPY common /common
RUN pip install --no-cache-dir -e /common

# Install CPU-only torch first (avoids downloading 6GB+ CUDA packages)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy service source then install
COPY services/content-service/ .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
