# syntax=docker/dockerfile:1
# Minimal image: OS base layer (python:3.12-slim) + this application only.
FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml ./
COPY seeder ./seeder
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SEEDER_CONFIG=/etc/seeder/config.yaml

# Copy the installed package and its dependencies from the build stage.
COPY --from=build /install /usr/local

# Run as a non-root, unprivileged user.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin seeder
USER 10001

ENTRYPOINT ["python", "-m", "seeder"]
