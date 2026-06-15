FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    grep \
    && rm -rf /var/lib/apt/lists/*

# Copy essential files
COPY pyproject.toml README.md ./
COPY llmai ./llmai
COPY server ./server
COPY run_server.py ./

# Install the application
RUN pip install --no-cache-dir .

# Expose default port
EXPOSE 7777

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=7777
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV LLMAI_MODEL=qwen2.5-coder

CMD ["python", "/app/run_server.py"]
