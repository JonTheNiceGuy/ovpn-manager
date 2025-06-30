# --- Stage 1: Builder ---
# Use a full Python image to build dependencies
FROM python:3.12-slim AS builder

WORKDIR /usr/src/app

# Install build dependencies
# We do this in a separate layer to leverage Docker's cache
COPY server/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /usr/src/app/wheels -r requirements.txt

# --- Stage 2: Final Image ---
# Use the same slim base image for the final container
FROM python:3.12-slim

# Create a dedicated group and user with no home directory and no shell.
# Using a fixed UID/GID (e.g., 1001) is good practice for Kubernetes security contexts.
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /usr/src/app

# Copy the pre-built wheels from the builder stage
COPY --from=builder /usr/src/app/wheels /wheels

# Install the dependencies from the wheels
RUN pip install --no-cache /wheels/*

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