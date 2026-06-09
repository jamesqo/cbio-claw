FROM nousresearch/hermes-agent:latest

USER root

RUN apt-get update && \
    apt-get install -y git gh openjdk-21-jdk-headless maven nodejs npm && \
    cd /tmp && curl https://clickhouse.com/ | sh && \
    ./clickhouse install --noninteractive && \
    rm -rf /var/lib/apt/lists/*

# Override the base image's USER hermes so the entrypoint starts as root.
# The upstream entrypoint remaps the hermes user to HERMES_UID/GID via
# usermod, chowns the data volume, then re-execs as hermes via gosu.
RUN sed -i "s/@kb.add('c-S-c')/#@kb.add('c-S-c')/" /opt/hermes/cli.py

USER root
ENV PATH="/opt/hermes/.venv/bin:$PATH"

# /opt/data is the volume mount point — don't copy anything here
# it will be overwritten by the host volume at runtime
VOLUME ["/opt/data"]
