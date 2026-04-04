"""
download_assets.py — Download photo images and video files referenced in posts.json

Assets are saved under assets/:
  assets/images/{owner_id}_{photo_id}.jpg   — photo attachments
  assets/videos/{owner_id}_{video_id}.*     — video files

A manifest (assets/manifest.json) maps logical keys to relative filenames so
build_site.py can reference them with local paths.  Already-downloaded assets
are skipped, so re-runs are fast and incremental.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ASSETS_DIR   = Path("assets")
IMAGES_DIR   = ASSETS_DIR / "images"
VIDEOS_DIR   = ASSETS_DIR / "videos"
MANIFEST_FILE = ASSETS_DIR / "manifest.json"

RATE_LIMIT_DELAY = 0.1   # seconds between HTTP downloads


def load_manifest():
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"images": {}, "videos": {}}


def save_manifest(manifest):
    tmp = MANIFEST_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(MANIFEST_FILE)


def download_file(url, dest_path):
    """Stream-download a file over HTTP."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            fh.write(chunk)


def download_via_ytdlp(url, output_template):
    """Download a video via yt-dlp.  output_template may use %(ext)s."""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "-o", str(output_template),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp exited with non-zero status")


def collect_attachments(posts):
    """Yield (type, data_dict) for every attachment in posts and reposts."""
    for post in posts:
        sources = [post] + post.get("copy_history", [])
        for src in sources:
            for att in src.get("attachments", []):
                yield att.get("type"), att


def download_images(posts, manifest):
    """Download photo attachments; update manifest in place."""
    photos_seen = {}
    for kind, att in collect_attachments(posts):
        if kind != "photo":
            continue
        photo = att["photo"]
        owner_id = photo.get("owner_id", 0)
        photo_id = photo.get("id", 0)
        key = f"{owner_id}_{photo_id}"
        if key not in photos_seen:
            photos_seen[key] = photo

    total  = len(photos_seen)
    done   = 0
    skip   = 0
    failed = 0
    print(f"→ Found {total} unique photo(s)")

    for key, photo in photos_seen.items():
        manifest_path = manifest["images"].get(key)
        if manifest_path:
            existing_file = ASSETS_DIR / manifest_path
            if existing_file.exists():
                skip += 1
                continue
            manifest["images"].pop(key, None)

        sizes = sorted(
            photo.get("sizes", []), key=lambda s: s.get("width", 0), reverse=True
        )
        if not sizes:
            failed += 1
            continue

        url  = sizes[0]["url"]
        dest = IMAGES_DIR / f"{key}.jpg"
        try:
            download_file(url, dest)
            manifest["images"][key] = f"images/{key}.jpg"
            done += 1
        except Exception as exc:
            print(f"  Error downloading photo {key}: {exc}")
            failed += 1
        # Save after each photo so progress survives interruption
        save_manifest(manifest)
        time.sleep(RATE_LIMIT_DELAY)

    print(f"  photos — downloaded: {done}, skipped: {skip}, failed: {failed}")


def download_videos(posts, manifest):
    """Download video attachments; update manifest in place."""
    videos_seen = {}
    for kind, att in collect_attachments(posts):
        if kind != "video":
            continue
        vid = att["video"]
        owner_id = vid.get("owner_id", 0)
        video_id = vid.get("id", 0)
        key = f"{owner_id}_{video_id}"
        if key not in videos_seen:
            videos_seen[key] = vid

    total  = len(videos_seen)
    done   = 0
    skip   = 0
    failed = 0
    print(f"→ Found {total} unique video(s)")

    for key, vid in videos_seen.items():
        if key in manifest["videos"]:
            skip += 1
            continue

        title = vid.get("title", key)
        print(f"  Downloading video: {title} ({key})")

        # Prefer the best available direct VK mp4 URL (native VK videos have a 'files' dict)
        files = vid.get("files", {})
        direct_url = None
        for quality in ("mp4_1080", "mp4_720", "mp4_480", "mp4_360", "mp4_240"):
            if files.get(quality):
                direct_url = files[quality]
                break

        try:
            if direct_url:
                dest = VIDEOS_DIR / f"{key}.mp4"
                download_file(direct_url, dest)
                manifest["videos"][key] = f"videos/{key}.mp4"
                done += 1
            else:
                # Fall back to yt-dlp for external videos (YouTube, etc.)
                player = vid.get("player", "")
                if not player:
                    print(f"  Skipping {key}: no downloadable URL")
                    failed += 1
                    continue
                template = VIDEOS_DIR / f"{key}.%(ext)s"
                valid_suffixes = (".mp4", ".webm", ".mkv", ".mov")
                # Remove stale outputs for this key so yt-dlp result detection is unambiguous.
                stale_matches = [
                    f for f in VIDEOS_DIR.glob(f"{key}.*")
                    if f.suffix.lower() in valid_suffixes
                ]
                for stale_file in stale_matches:
                    stale_file.unlink()
                download_via_ytdlp(player, template)
                # Locate the file yt-dlp created deterministically.
                matches = [
                    f for f in VIDEOS_DIR.glob(f"{key}.*")
                    if f.suffix.lower() in valid_suffixes
                ]
                if matches:
                    mp4_matches = [f for f in matches if f.suffix.lower() == ".mp4"]
                    selected = (
                        max(mp4_matches, key=lambda f: f.stat().st_mtime)
                        if mp4_matches
                        else max(matches, key=lambda f: f.stat().st_mtime)
                    )
                    filename = selected.name
                    manifest["videos"][key] = f"videos/{filename}"
                    done += 1
                else:
                    print(f"  Warning: yt-dlp finished but output not found for {key}")
                    failed += 1
        except Exception as exc:
            print(f"  Error downloading video {key}: {exc}")
            failed += 1

        # Save after each video so progress survives interruption
        save_manifest(manifest)
        time.sleep(RATE_LIMIT_DELAY)

    print(f"  videos  — downloaded: {done}, skipped: {skip}, failed: {failed}")


def main():
    posts_file = Path("posts.json")
    if not posts_file.exists():
        print("ERROR: posts.json not found. Run fetch_vk.py first.")
        sys.exit(1)

    ASSETS_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)
    VIDEOS_DIR.mkdir(exist_ok=True)

    print("→ Loading posts.json...")
    data  = json.loads(posts_file.read_text(encoding="utf-8"))
    posts = data.get("posts", [])

    manifest = load_manifest()

    download_images(posts, manifest)
    download_videos(posts, manifest)

    save_manifest(manifest)
    print(f"→ Manifest saved to {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
