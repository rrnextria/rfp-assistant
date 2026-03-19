FROM python:3.12-slim
WORKDIR /app
COPY common /common
RUN pip install --no-cache-dir /common

COPY scripts/install_deps.py /install_deps.py
COPY services/audit-service/pyproject.toml .
RUN python3 /install_deps.py
COPY services/audit-service/ .
EXPOSE 8008
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008", "--reload"]
