# OSS-1 Self-Service Pilot Kit
# Docker image with all dependencies

FROM python:3.10-slim

LABEL maintainer="International Group of Developers"
LABEL description="OSS-1: Thermal Shield Inspector for Starship"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    libportaudio2 \
    sox \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY models/ ./models/
COPY config/ ./config/
COPY record.sh analyze.sh ./

# Make scripts executable
RUN chmod +x record.sh analyze.sh

# Create directories for recordings
RUN mkdir -p /app/recordings

# Default command (show help)
CMD ["make", "help"]
