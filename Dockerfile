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

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application files
COPY . .

# Run tests by default
CMD ["pytest"]
