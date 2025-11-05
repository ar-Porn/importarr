FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    requests==2.31.0 \
    schedule==1.2.0

# Copy the script
COPY importarr.py /app/importarr.py

# Make script executable
RUN chmod +x /app/importarr.py

# Create mount point for import folder
RUN mkdir -p /import

# Run the script
ENTRYPOINT ["python3", "/app/importarr.py"]
