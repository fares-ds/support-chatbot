# syntax=docker/dockerfile:1

# The benchmark harness (#12). It is never part of an install: compose.yaml runs it next to a
# stack, on the stack's internal network. The image holds the dependencies, test tools
# included; compose.yaml mounts this directory over the code, so edits need no rebuild.

FROM python:3.12.15-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /bench
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked
COPY . .
# Bytecode stays out of the mounted directory, whose __pycache__ the host's own runs fill.
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONPYCACHEPREFIX=/tmp/pycache
ENTRYPOINT ["python", "-m", "bench"]
