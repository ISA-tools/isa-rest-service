FROM docker.io/library/python:3.14.5-slim-trixie AS builder

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN python -m venv "${VIRTUAL_ENV}" \
    && apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --requirement requirements.lock


FROM docker.io/library/python:3.14.5-slim-trixie AS runtime

LABEL org.opencontainers.image.title="ISA REST Service" \
      org.opencontainers.image.description="ISA metadata conversion and validation API" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="The ISA team, Philippe Rocca-Serra <philippe.rocca-serra@oerc.ox.ac.uk>, Milo Thurston <milo.thurston@oerc.ox.ac.uk>" \
      uk.ac.ox.oerc.isa-rest-service.ai-assisted="OpenAI Codex" \
      org.opencontainers.image.licenses="CPAL-1.0"

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV ENVIRONMENT=production
ENV HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV XDG_CACHE_HOME=/tmp/.cache

RUN groupadd --gid 10001 isa \
    && useradd --uid 10001 --gid isa --home-dir /app \
        --no-create-home --shell /usr/sbin/nologin isa

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=isa:isa api ./api
COPY --chown=isa:isa config.py isarest.py ./

USER 10001:10001

EXPOSE 5000

CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "--threads=4", "--timeout=300", "--graceful-timeout=60", "--access-logfile=-", "--error-logfile=-", "isarest:create_app()"]


FROM runtime AS test

ENV ENVIRONMENT=test

COPY --chown=isa:isa tests.py integration_tests.py isarest_client.py ./
COPY --chown=isa:isa testdata ./testdata

CMD ["python", "-W", "error::ResourceWarning", "-W", "error::DeprecationWarning", "-W", "default:Deprecated call to:DeprecationWarning", "-m", "unittest", "tests"]


FROM runtime AS production
