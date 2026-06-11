FROM nousresearch/hermes-agent:v2026.6.5

USER root

RUN cd /tmp && curl https://clickhouse.com/ | sh && \
    ./clickhouse install --noninteractive && \
    rm -f /tmp/clickhouse

RUN apt-get update && \
    apt-get install -y curl git gh openjdk-21-jdk-headless maven nodejs npm && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

RUN npm install -g @github/copilot

USER root
ENV PATH="/opt/hermes/.venv/bin:$PATH"

# /opt/data is the volume mount point — don't copy anything here
# it will be overwritten by the host volume at runtime
VOLUME ["/opt/data"]
