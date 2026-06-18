# Use Python 3.10 slim image
FROM python:3.10-slim

# Install system dependencies needed for OpenCV and system libraries
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /code

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files to the container
COPY . .

# Hugging Face Spaces runs as user 1000, so we need to ensure permissions are open
RUN chmod -R 777 /code

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Expose Hugging Face's default port
EXPOSE 7860

# Run the FastAPI web application on port 7860
CMD ["sh", "-c", "if [ -f object_detection/main.py ]; then python object_detection/main.py --web --port 7860 --device cpu; else python main.py --web --port 7860 --device cpu; fi"]
