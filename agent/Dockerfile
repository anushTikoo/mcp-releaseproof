# Immutable pre-warmed runner image for MCP ReleaseProof sandboxed execution
FROM python:3.12-slim-bookworm

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create unprivileged releaseproof sandbox user (UID 10001, GID 10001)
RUN groupadd -g 10001 sandbox && \
    useradd -u 10001 -g 10001 -m -s /bin/sh sandbox

# Set working directory
WORKDIR /workspace

# Copy and install pinned requirements in builder stage/system python
COPY requirements-sandbox.txt /tmp/requirements-sandbox.txt
RUN pip install --no-cache-dir -r /tmp/requirements-sandbox.txt && \
    rm -f /tmp/requirements-sandbox.txt

# Ensure permissions on workspace
RUN chown -R 10001:10001 /workspace

# Switch to unprivileged non-root user
USER 10001:10001

# Entrypoint default command (disable cacheprovider for read-only workspace)
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "/workspace/test_harness.py"]
