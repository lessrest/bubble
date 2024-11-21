FROM mcr.microsoft.com/devcontainers/base:alpine-3.20
RUN apk add deno swi-prolog --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing/
RUN mkdir -p /src && cd /src && git clone https://github.com/eyereasoner/eye
RUN cd /src/eye && sh install.sh
RUN ln -s /opt/eye/bin/eye /usr/bin/eye
