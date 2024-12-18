# syntax=docker/dockerfile:1.4
# the preceding line lets us use .gitignore for exclusions

FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    git \
    make \
    gcc \
    g++ \
    swi-prolog \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /src && \
    cd /src && \
    git clone --depth 1 https://github.com/eyereasoner/eye && \
    cd eye && \
    sh install.sh && \
    ln -s /opt/eye/bin/eye /usr/bin/eye

WORKDIR /app

COPY package.json .
COPY package-lock.json .
RUN npm ci

RUN pip install uv

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY pyproject.toml .
COPY uv.lock .

# do the initial sync for dependencies from the lock file
RUN uv sync \
    --no-install-project --no-install-workspace --no-sources \
    --frozen \
    --no-install-package swash

COPY . .

# do the full sync including installing the project etc
RUN uv sync --frozen

CMD ["bubble", "town"]