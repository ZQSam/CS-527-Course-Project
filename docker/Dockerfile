# Defects4J v2.0.0 requires Java 8; see its tagged README.
# Official Temurin image resolves to 8u504-b01 on linux/amd64.
FROM eclipse-temurin:8-jdk-jammy@sha256:185d4ef919b98cd195690c33f3fd93bd49c66c70f0b662e54566c0dbaebea6ce

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive TZ=America/Los_Angeles

RUN apt-get update && apt-get install -y --no-install-recommends \
    ant ca-certificates cpanminus curl git libdbd-csv-perl libdbi-perl \
    libjson-parse-perl libjson-perl liburi-perl make perl python3 subversion \
    tzdata unzip wget zip \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch v2.0.0 https://github.com/rjust/defects4j.git /opt/defects4j \
    && test "$(git -C /opt/defects4j rev-parse HEAD)" = 01f13c69425fb8a0db290d12b1d48da1641bf6a9 \
    && cd /opt/defects4j && cpanm --installdeps --notest . \
    && ./init.sh

ENV D4J_HOME=/opt/defects4j \
    GZOLTAR_HOME=/opt/gzoltar \
    GZOLTAR_CLI=/opt/gzoltar/com.gzoltar.cli-1.7.3-jar-with-dependencies.jar \
    GZOLTAR_AGENT=/opt/gzoltar/com.gzoltar.agent.rt-1.7.3-all.jar
ENV PATH="/opt/defects4j/framework/bin:${PATH}"

RUN mkdir -p /opt/gzoltar /opt/environment \
    && curl --fail --location --retry 3 \
      https://repo.maven.apache.org/maven2/com/gzoltar/com.gzoltar.cli/1.7.3/com.gzoltar.cli-1.7.3-jar-with-dependencies.jar \
      -o "$GZOLTAR_CLI" \
    && curl --fail --location --retry 3 \
      https://repo.maven.apache.org/maven2/com/gzoltar/com.gzoltar.agent.rt/1.7.3/com.gzoltar.agent.rt-1.7.3-all.jar \
      -o "$GZOLTAR_AGENT" \
    && printf '%s  %s\n' 3b657e3a82ca1a44971a3bc5014814e57a9c5e54 "$GZOLTAR_CLI" \
      e6ed986cce6e03bb4106344faab4127e22cb6c2c "$GZOLTAR_AGENT" | sha1sum --check - \
    && sha256sum "$GZOLTAR_CLI" "$GZOLTAR_AGENT" > /opt/environment/gzoltar.sha256 \
    && dpkg-query -W > /opt/environment/packages.tsv \
    && java -jar "$GZOLTAR_CLI" --help > /opt/environment/gzoltar-help.txt \
    && git config --system --add safe.directory /opt/defects4j \
    && git config --system --add safe.directory /opt/defects4j/project_repos/commons-lang.git \
    && defects4j info -p Lang > /opt/environment/defects4j-lang.txt

COPY scripts/setup_python.py /opt/setup_python.py
RUN python3 /opt/setup_python.py --target /opt/python-deps
ENV PYTHONPATH=/opt/python-deps

ARG LOCAL_UID=1000
ARG LOCAL_GID=1000
# Lang tests inspect Java's user.home. A numeric UID without a passwd entry
# gives Java an invalid home, introducing unrelated SystemUtils test failures.
RUN groupadd --gid "$LOCAL_GID" researcher \
    && useradd --uid "$LOCAL_UID" --gid "$LOCAL_GID" --create-home researcher

USER researcher
WORKDIR /workspace
CMD ["bash"]
