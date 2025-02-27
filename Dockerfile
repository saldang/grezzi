FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the application into the container.
COPY . /app

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache
# Expose the application port.
EXPOSE 8000
# Run the application.
CMD ["dev", "--host", "0.0.0.0", "--port", "8000"]