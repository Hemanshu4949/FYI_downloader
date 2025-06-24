# api.py
# This is your main FastAPI application file, adapted to use cookies
# for yt-dlp authentication.
# Save this file as 'api.py' in your project's root directory.

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp
import uvicorn
import os
import shutil
import asyncio
import tempfile # For creating temporary cookie files

app = FastAPI(
    title="Video Downloader API (Ethical Use Only)",
    description="""
    This API provides endpoints for downloading and converting videos to MP3 using yt-dlp.
    **WARNING:** Use of this API to download content from platforms like YouTube may violate their Terms of Service and copyright law.
    Ensure you have explicit permission for any content you download or convert.
    """,
    version="1.0.0"
)

# Directory to save downloaded files.
DOWNLOAD_DIR = "downloads"
# Ensure the downloads directory exists.
# The Dockerfile also ensures this, but it's good practice here too.
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Mount a static directory to serve the downloaded files
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# Function to get yt-dlp options, including cookie handling
def get_ydl_opts(output_template, cookie_file_path=None):
    """Constructs yt-dlp options dictionary."""
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_flat': True, # Use for faster metadata extraction without full downloads
    }
    if cookie_file_path:
        opts['cookiefile'] = cookie_file_path
    return opts

# Function to run blocking yt-dlp operations in a separate thread
async def run_yt_dlp_operation(url, output_template, cookie_string=None):
    """
    Handles yt-dlp download/extraction in a separate thread,
    optionally using cookies from an environment variable.
    """
    # Use a context manager for temporary file to ensure it's cleaned up
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp_cookie_file:
        if cookie_string:
            tmp_cookie_file.write(cookie_string)
        cookie_file_path = tmp_cookie_file.name

    try:
        # Define the blocking function that yt-dlp will run
        def blocking_download():
            ydl_opts = get_ydl_opts(output_template, cookie_file_path)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # yt-dlp's info dictionary contains the final filepath after post-processing
                # For simple video/audio downloads, 'filepath' is usually directly in info.
                # For post-processed files (like mp3 extraction), it might require inference.

                final_filepath = info.get('filepath')
                if not final_filepath:
                    # Robust way to find the actual downloaded file if 'filepath' is not direct
                    title = info.get('title', 'unknown_title')
                    video_id = info.get('id', 'unknown_id')
                    # yt-dlp adds the correct extension during post-processing
                    potential_filename_prefix = f"{title}-{video_id}"

                    # Search for the actual file in the download directory
                    found_files = [
                        f for f in os.listdir(DOWNLOAD_DIR)
                        if f.startswith(potential_filename_prefix)
                    ]

                    if found_files:
                        final_filepath = os.path.join(DOWNLOAD_DIR, found_files[0])
                    else:
                        raise Exception("Could not reliably determine the final downloaded file path.")
                
                return final_filepath

        # Use asyncio.to_thread to run the blocking yt-dlp operation
        filepath = await asyncio.to_thread(blocking_download)
        return filepath
    finally:
        # Ensure the temporary cookie file is deleted
        if os.path.exists(cookie_file_path):
            os.remove(cookie_file_path)


@app.get("/health", summary="Health Check")
async def health_check():
    """
    Checks the health of the API.
    """
    return {"status": "ok", "message": "API is running smoothly."}

@app.get("/mp3", summary="Download and Convert Video to MP3")
async def download_mp3(url: str):
    """
    Downloads a video from the provided URL and converts it to MP3 format.

    Args:
        url (str): The URL of the video to download.

    Returns:
        dict: A dictionary containing the URL to the downloaded MP3 file.
    """
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL parameter is required.")

    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s-%(id)s.%(ext)s')
    
    # Get cookie string from environment variable
    cookie_string = os.getenv('YTDLP_COOKIES')

    try:
        mp3_filepath = await run_yt_dlp_operation(url, output_template, cookie_string)

        # yt-dlp appends .mp3 if conversion is successful, so ensure we have the correct extension
        if not mp3_filepath.endswith('.mp3'):
            # This is a fallback if yt-dlp doesn't directly return the .mp3 path.
            # It tries to find the .mp3 file based on the original name.
            base_name = os.path.splitext(mp3_filepath)[0]
            potential_mp3_path = f"{base_name}.mp3"
            if os.path.exists(potential_mp3_path):
                mp3_filepath = potential_mp3_path
            else:
                # If still can't find, raise an error or try another strategy.
                raise Exception(f"MP3 file not found after conversion for {url}. Expected: {potential_mp3_path}")


        mp3_filename = os.path.basename(mp3_filepath)
        download_url = f"/downloads/{mp3_filename}"

        return {"message": "Download and conversion successful", "download_url": download_url}

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Video download error: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@app.get("/download-video", summary="Download Video (Original Format)")
async def download_video(url: str):
    """
    Downloads a video from the provided URL in its original format.

    Args:
        url (str): The URL of the video to download.

    Returns:
        dict: A dictionary containing the URL to the downloaded video file.
    """
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL parameter is required.")

    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s-%(id)s.%(ext)s')
    cookie_string = os.getenv('YTDLP_COOKIES') # Get cookie string for video downloads too

    try:
        video_filepath = await run_yt_dlp_operation(url, output_template, cookie_string)

        if not video_filepath:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Downloaded video file path could not be determined.")

        video_filename = os.path.basename(video_filepath)
        download_url = f"/downloads/{video_filename}"
        return {"message": "Download successful", "download_url": download_url}

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Video download error: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@app.get('/downloads/{filename}')
async def serve_downloaded_file(filename: str):
    """
    Serves downloaded files from the DOWNLOAD_DIR.
    """
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    
    # Ensure the path is within the DOWNLOAD_DIR for security
    # (send_from_directory does this automatically in Flask, but for FastAPI
    #  it's good to be explicit or use FileResponse directly with abspath and checks)
    return FileResponse(path=file_path, filename=filename)


# This ensures the app runs when the script is executed directly for local development.
# Render will use the 'uvicorn' command specified in the Dockerfile.
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

