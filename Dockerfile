# Use Python 3.10 as base image (supports CUDA and PyTorch)
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PyTorch Geometric and scientific computing
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt requirements-dev.txt ./

# Install core dependencies first (PyTorch must be installed before PyTorch Geometric)
RUN pip install --no-cache-dir torch>=1.8.0 numpy>=1.20.0

# Install remaining dependencies
RUN pip install --no-cache-dir \
    matplotlib>=3.4.0 \
    networkx>=2.6.0 \
    scikit-learn>=1.0.0 \
    tqdm>=4.60.0 \
    scipy>=1.7.0 \
    pandas>=1.3.0 \
    seaborn>=0.11.0

# Install PyTorch Geometric dependencies last
RUN pip install --no-cache-dir \
    torch-geometric>=2.0.0 \
    torch-scatter>=2.0.9 \
    torch-sparse>=0.6.13 \
    torch-cluster>=1.6.0 \
    torch-spline-conv>=1.2.1

# Copy the entire project
COPY . .

# Install the package in development mode
RUN pip install -e .

# Create directories for results and experiments
RUN mkdir -p /app/results /app/exp

# Set Python path
ENV PYTHONPATH=/app

# Expose port for potential web interfaces or notebooks
EXPOSE 8888

# Default command
CMD ["python", "-m", "polaris.experiments"]