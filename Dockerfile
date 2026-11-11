# Alchemist's Chimera - Hugging Face Spaces image
# Kiroween Hackathon 2026 Submission

FROM python:3.11-slim

WORKDIR /app

# Hugging Face Spaces runs the application as UID 1000.
ENV OLLAMA_MODELS=/app/.ollama/models \
    HF_HOME=/app/.cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install the compilers and tools required by the Python dependencies and Ollama.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    git \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama for local, air-gapped LLM inference.
RUN curl -fsSL https://ollama.com/install.sh | sh

# Install the pinned application dependency set, including Streamlit, pypdf,
# PyVis, spaCy, and the local Ollama client.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Download the entity extraction model into the image so startup does not need
# network access for the spaCy model.
RUN python -m spacy download en_core_web_sm

# Copy the Streamlit entrypoint, startup supervisor, application packages, and runtime assets.
COPY start.sh /app/start.sh
COPY app.py /app/app.py
COPY components/ /app/components/
COPY core/ /app/core/
COPY src/ /app/src/
COPY .streamlit/ /app/.streamlit/
COPY data/ /app/data/
COPY ontology/ /app/ontology/

# Create writable runtime and persistence directories even when a source
# directory is empty in the build context.
RUN mkdir -p \
    /app/.ollama/models \
    /app/.cache \
    /app/data/cache \
    /app/data/graphs \
    /app/data/input \
    /app/data/tmp \
    /app/data/uploads \
    /app/data/vector_store \
    /app/models \
    /app/ontology \
    && useradd --create-home --uid 1000 --shell /bin/bash appuser \
    && chown -R appuser:appuser /app \
    && chmod -R 777 /app \
    && chmod +x /app/start.sh

USER appuser

# Streamlit exposes this lightweight readiness endpoint without requiring an
# additional API server.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl --fail --silent http://localhost:7860/_stcore/health || exit 1

EXPOSE 7860

CMD ["/app/start.sh"]
