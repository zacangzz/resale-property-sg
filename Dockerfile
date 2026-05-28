# Use lightweight Python 3.13 image
FROM python:3.13-slim

# Set environment variables for Python and uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Install system dependencies (like curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official installer script
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:${PATH}"

# Set the working directory
WORKDIR /app

# Copy dependency specifications and lockfile
COPY pyproject.toml uv.lock ./

# Install project dependencies globally in the system environment
RUN uv sync --no-dev --frozen

# Copy the rest of the orchestration and etl scripts
COPY . .

# Set default CMD to materialize all Dagster assets in the orchestration module
CMD ["uv", "run", "dagster", "asset", "materialize", "--select", "*", "-m", "orchestration.definitions"]
