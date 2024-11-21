# Use Debian as base
FROM debian:trixie-slim

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    make \
    gcc \
    g++ \
    swi-prolog \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/x/install/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

# Install EYE reasoner
RUN mkdir -p /src && \
    cd /src && \
    git clone https://github.com/eyereasoner/eye && \
    cd eye && \
    sh install.sh && \
    ln -s /opt/eye/bin/eye /usr/bin/eye

# Set up app directory
WORKDIR /app

# Cache dependencies
COPY deno.json deno.lock ./
RUN deno cache --lock=deno.lock main.ts

# Copy application files
COPY . .

# Expose default port
EXPOSE 8000

# Start the server
CMD ["deno", "task", "serve"]