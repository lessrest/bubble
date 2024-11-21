FROM mcr.microsoft.com/devcontainers/base:ubuntu
RUN apt install -y swi-prolog
RUN mkdir -p /src && cd /src && git clone https://github.com/eyereasoner/eye
RUN cd /src/eye && sh install.sh
RUN ln -s /opt/eye/bin/eye /usr/bin/eye
RUN curl -fsSL https://deno.land/install.sh | sh
RUN cp /root/.deno/bin/deno /usr/bin/deno
