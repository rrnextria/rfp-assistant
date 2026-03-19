FROM python:3.12-slim
WORKDIR /app
COPY common /common
RUN pip install --no-cache-dir /common

COPY scripts/install_deps.py /install_deps.py

# Install adapter client libraries so the orchestrator can call LLM providers directly
RUN pip install --no-cache-dir anthropic>=0.30 "openai>=1.0" google-generativeai>=0.7

# Copy adapter source files into /app/adapters so pipeline.py can import them
COPY services/adapters/ /app/adapters/

COPY services/orchestrator/pyproject.toml .
RUN python3 /install_deps.py
COPY services/orchestrator/ .
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
