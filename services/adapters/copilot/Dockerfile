FROM python:3.12-slim

WORKDIR /app

# Install common package first for better layer caching
COPY common /common
RUN pip install --no-cache-dir -e /common

# Install copilot adapter dependencies
COPY services/adapters/copilot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full adapters package (copilot is a sub-package)
COPY services/adapters/ ./services/adapters/

# Expose port
EXPOSE 8009

# Run as a module so Python resolves the relative imports inside the package
CMD ["uvicorn", "services.adapters.copilot.main:app", "--host", "0.0.0.0", "--port", "8009"]
