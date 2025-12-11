FROM python:3.13-slim-bookworm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system dependencies (git is required for git dependencies)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the project files
COPY . /app

# Install dependencies
# We remove --frozen because the lock file contains the old local path dependency
# and we want to resolve the new PyPI dependency
RUN uv sync

# Expose the controller port
EXPOSE 8010

# Run the controller
# We use `uv run` to ensure we use the virtual environment
CMD ["uv", "run", "agentbeats", "run_ctrl"]
