# syntax=docker/dockerfile:1.4
# Use .gitignore for exclusions
# Use Python base image
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    make \
    gcc \
    g++ \
    swi-prolog \
    && rm -rf /var/lib/apt/lists/*

# Install EYE reasoner
RUN mkdir -p /src && \
    cd /src && \
    git clone https://github.com/eyereasoner/eye && \
    cd eye && \
    sh install.sh && \
    ln -s /opt/eye/bin/eye /usr/bin/eye

# Set up app directory
WORKDIR /app

# Install uv
RUN pip install uv

# Set up virtual environment path
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy application files
COPY . .

# Install Python dependencies
RUN uv sync

# Run tests by default
CMD ["pytest"]
