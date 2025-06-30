ARG IMAGE_REPO=debian
ARG IMAGE_TAG=bookworm-slim
FROM ${IMAGE_REPO}:${IMAGE_TAG} AS builder

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY server/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /usr/src/app/wheels -r requirements.txt

FROM ${IMAGE_REPO}:${IMAGE_TAG}

# Create a dedicated group and user with no home directory and no shell.
# Using a fixed UID/GID (e.g., 1001) is good practice for Kubernetes security contexts.
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --no-create-home appuser

# Install Python
RUN apt-get update && \
    apt-get install -y python3 python3-pip libpq5 && \
    rm -rf /var/lib/apt/lists/*
# Note: libpq5 is the runtime library for psycopg2

WORKDIR /usr/src/app

# Copy the pre-built wheels from the builder stage
COPY --from=builder /usr/src/app/wheels /wheels

# Install the dependencies from the wheels
RUN pip install --break-system-packages --no-cache /wheels/*

# Copy the application code
COPY server/ ./server/
COPY migrations/ ./migrations/

# Change the ownership of the application directory to our new non-root user.
# This ensures our process can read its own files.
RUN chown -R appuser:appgroup /usr/src/app

# --- Switch to the non-root user ---
# All subsequent commands will be run as 'appuser'.
USER appuser

# Set environment variables for Gunicorn
ENV GUNICORN_CMD_ARGS="--bind=0.0.0.0:8000 --workers=3 --access-logfile - --error-logfile - --log-level info --logger-class server.logging.CustomGunicornLogger"

# Expose the port Gunicorn will run on
EXPOSE 8000

# The command to run the application
CMD ["gunicorn", "server:create_app()"]