from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp
import uvicorn
import os   
import shutil
import asyncio # Import asyncio for asyncio.to_thread

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
# IMPORTANT: For production, this should be a carefully managed directory,
# ideally with cleanup policies or cloud storage integration.
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Mount a static directory to serve the downloaded files
# This makes files in the DOWNLOAD_DIR accessible via '/downloads/{filename}'
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# The ThreadPoolExecutor is no longer explicitly needed here,
# as asyncio.to_thread uses an internal default executor.

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
    # Define yt-dlp options for MP3 conversion
    ydl_opts = {
        'format': 'bestaudio/best',  # Select best audio format
        'postprocessors': [{
            'key': 'FFmpegExtractAudio', # Use FFmpeg to extract audio
            'preferredcodec': 'mp3',     # Preferred audio codec is MP3
            'preferredquality': '192',   # MP3 quality (e.g., 192kbps)
        }],
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s-%(id)s.%(ext)s'), # Output template for file path
        'quiet': True,           # Suppress verbose output
        'no_warnings': True,     # Suppress warnings
        'noplaylist': True,      # Do not download entire playlists
        'extract_flat': True,    # Only extract metadata for the top-level URL
    }

    try:
        # Define the blocking function to run in a separate thread
        def blocking_download_mp3():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # yt-dlp's info dictionary contains the final filepath after post-processing
                # For simple video/audio downloads, 'filepath' is usually directly in info.
                # For post-processed files (like mp3 extraction), it might be in 'requested_downloads'
                # or require a bit more inference.
                # The most reliable way is often to infer from 'info' or check the directory
                
                # Check for 'filepath' in the main info_dict first, as it often points to the final file
                final_filepath = info.get('filepath')
                
                # If not directly available, try to infer from common yt-dlp patterns
                if not final_filepath:
                    # yt-dlp often renames the file with the preferred extension
                    title = info.get('title', 'unknown_title')
                    video_id = info.get('id', 'unknown_id')
                    potential_filename_pattern = f"{title}-{video_id}"
                    
                    # Search for the .mp3 file in the download directory that matches the pattern
                    found_files = [
                        f for f in os.listdir(DOWNLOAD_DIR) 
                        if f.startswith(potential_filename_pattern) and f.endswith('.mp3')
                    ]
                    
                    if found_files:
                        final_filepath = os.path.join(DOWNLOAD_DIR, found_files[0])
                    else:
                        # Fallback: less reliable, try to guess or return error
                        # This part might need further robustness based on yt-dlp's exact output.
                        # For most cases, the 'outtmpl' and 'filepath' in info should suffice.
                        print(f"Warning: Could not reliably determine final MP3 path for {url}. Info: {info}")
                        # As a last resort, construct a likely name and check existence
                        likely_filename = f"{title}-{video_id}.mp3"
                        if os.path.exists(os.path.join(DOWNLOAD_DIR, likely_filename)):
                            final_filepath = os.path.join(DOWNLOAD_DIR, likely_filename)
                        else:
                            raise Exception("Could not find the downloaded MP3 file.")

                return final_filepath

        # Use asyncio.to_thread to run the blocking function in a separate thread
        mp3_filepath = await asyncio.to_thread(blocking_download_mp3)

        # Ensure the filename is just the base name for the URL path
        mp3_filename = os.path.basename(mp3_filepath)

        # Construct the full download URL that clients can use
        download_url = f"/downloads/{mp3_filename}"

        return {"message": "Download and conversion successful", "download_url": download_url}

    except yt_dlp.utils.DownloadError as e:
        # Catch specific yt-dlp download errors
        raise HTTPException(status_code=400, detail=f"Video download error: {e}")
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.get("/download-video", summary="Download Video (Original Format)")
async def download_video(url: str):
    """
    Downloads a video from the provided URL in its original format.

    Args:
        url (str): The URL of the video to download.

    Returns:
        dict: A dictionary containing the URL to the downloaded video file.
    """
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s-%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_flat': True,
    }

    try:
        def blocking_download_video():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # For direct video downloads, 'filepath' in info_dict is usually reliable
                return info.get('filepath')

        video_filepath = await asyncio.to_thread(blocking_download_video)

        if not video_filepath:
            raise HTTPException(status_code=500, detail="Downloaded video file path could not be determined.")

        # Ensure the filename is just the base name for the URL path
        video_filename = os.path.basename(video_filepath)
        
        download_url = f"/downloads/{video_filename}"
        return {"message": "Download successful", "download_url": download_url}

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Video download error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# This ensures the app runs when the script is executed directly
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
