FROM mcr.microsoft.com/devcontainers/python:3.13-bullseye

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

# Install Python tools
RUN pip install --no-cache-dir uv ruff pytest pytest-trio
