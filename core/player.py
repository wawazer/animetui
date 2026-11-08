import os
import shutil
import subprocess

DOWNLOAD_DIR = os.path.join(".", "downloads")
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def is_tool_available(tool_name: str) -> bool:
    return shutil.which(tool_name) is not None


def play_stream(stream_url: str, title: str = "Stream", referer: str = "") -> tuple[bool, str]:
    if not stream_url:
        return False, "Error: Empty stream URL"

    if not is_tool_available("mpv"):
        return False, "Error: mpv player not found in PATH"

    cmd = [
        "mpv",
        f"--title={title}",
        "--ontop",
        "--force-window=immediate",
        f"--user-agent={DEFAULT_UA}",
    ]

    if referer:
        cmd.append(f"--referrer={referer}")

    cmd.append(stream_url)

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True if os.name != "nt" else False,
        )
        return True, f"Playing: {title}"
    except Exception as exc:
        return False, f"Play error: {exc}"


def download_stream(stream_url: str, title: str = "Stream", referer: str = "") -> tuple[bool, str]:
    if not stream_url:
        return False, "Error: Empty stream URL"

    if not is_tool_available("yt-dlp"):
        return False, "Error: yt-dlp not found in PATH"

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    # Sanitize title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_", ".")).strip()
    out_tmpl = os.path.join(DOWNLOAD_DIR, f"{safe_title or 'video'}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--user-agent",
        DEFAULT_UA,
        "-o",
        out_tmpl,
    ]

    if referer:
        cmd.extend(["--referer", referer])

    cmd.append(stream_url)

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True if os.name != "nt" else False,
        )
        return True, f"Downloading: {title}"
    except Exception as exc:
        return False, f"Download error: {exc}"
