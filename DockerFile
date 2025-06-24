# Use an official Python runtime as a parent image
# We're choosing a slim version for smaller image size, based on Debian/Ubuntu
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies, including FFmpeg
# FFmpeg is crucial for yt-dlp's post-processing (like MP3 conversion)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    # Clean up apt caches to keep the image size down
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the working directory
COPY requirements.txt .

# Install any needed Python packages specified in requirements.txt
# Using --no-cache-dir to save space
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the working directory
COPY . .

# Create the downloads directory
# This ensures it exists when the container starts
RUN mkdir -p downloads

# Expose the port that Uvicorn will listen on
# Render will inject the actual port into the $PORT environment variable
EXPOSE 8000

# Define the command to run your application
# 'uvicorn api:app' assumes your main FastAPI app is in a file named 'api.py'
# and the FastAPI instance is named 'app'. Adjust if your file or app object name differs.
# We use $PORT provided by Render to bind the server.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
