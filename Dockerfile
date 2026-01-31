# Python runtime
FROM python:3.10-slim

# Working directory
WORKDIR /app

# Requirements
COPY requirements.txt ./

# Install system build deps required for some Python packages
RUN apt-get update ; \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libcairo2-dev \
        libgirepository1.0-dev \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
        libmagic-dev \
    ; \
    rm -rf /var/lib/apt/lists/*

# Upgrade packaging tools
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]

