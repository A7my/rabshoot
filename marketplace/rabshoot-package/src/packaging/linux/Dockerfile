# Builds the Linux .deb on Ubuntu 22.04 so it runs on 22.04+ / Debian 12+ (glibc 2.35).
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg software-properties-common build-essential pkg-config file \
        rsync libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev \
        librsvg2-dev patchelf
RUN add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3.12-dev
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path

COPY build-in-container.sh /usr/local/bin/build-in-container.sh
ENTRYPOINT ["bash", "/usr/local/bin/build-in-container.sh"]
