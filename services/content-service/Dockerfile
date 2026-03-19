FROM python:3.12-slim
WORKDIR /app
COPY common /common
RUN pip install --no-cache-dir /common
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY scripts/install_deps.py /install_deps.py
COPY services/content-service/pyproject.toml .
RUN python3 /install_deps.py
COPY services/content-service/ .
EXPOSE 8003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
