"""
upload_videos.py — Upload downloaded videos to a GitHub Release so they can be
served directly without bloating the GitHub Pages artifact.

For each video in assets/videos/ that is recorded in the manifest, this script:
  1. Ensures a GitHub Release with the tag `v-assets` exists (creates it if not).
  2. Uploads any new video files as release assets.
  3. Stores the resulting download URLs in manifest["video_urls"] so that
     build_site.py can use them as <video src="..."> instead of a local path.

Requires the `gh` CLI to be authenticated (GH_TOKEN env var is sufficient on
GitHub Actions).
"""

import json
import os
import subprocess
from pathlib import Path

RELEASE_TAG   = "v-assets"
ASSETS_DIR    = Path("assets")
VIDEOS_DIR    = ASSETS_DIR / "videos"
MANIFEST_FILE = ASSETS_DIR / "manifest.json"


def _run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(str(c) for c in cmd)}\n{result.stderr}"
        )
    return result


def repo():
    return os.environ["GITHUB_REPOSITORY"]


def ensure_release():
    result = _run(["gh", "release", "view", RELEASE_TAG, "--repo", repo()], check=False)
    if result.returncode != 0:
        print(f"  Creating release {RELEASE_TAG}...")
        _run([
            "gh", "release", "create", RELEASE_TAG,
            "--repo",     repo(),
            "--title",    "Video Assets",
            "--notes",    "Auto-managed release for VK Archive video assets.",
            "--prerelease",
        ])
        print(f"  Release {RELEASE_TAG} created.")
    else:
        print(f"  Release {RELEASE_TAG} already exists.")


def get_existing_asset_names():
    out = _run([
        "gh", "release", "view", RELEASE_TAG, "--repo", repo(),
        "--json", "assets", "--jq", ".assets[].name",
    ])
    return set(filter(None, out.stdout.strip().splitlines()))


def upload_file(path):
    _run(["gh", "release", "upload", RELEASE_TAG, str(path), "--repo", repo()])


def main():
    if not MANIFEST_FILE.exists():
        print("No manifest.json found — nothing to upload.")
        return

    manifest   = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    video_keys = manifest.get("videos", {})

    if not video_keys:
        print("No videos in manifest — nothing to upload.")
        return

    ensure_release()
    existing = get_existing_asset_names()

    base_url   = f"https://github.com/{repo()}/releases/download/{RELEASE_TAG}"
    video_urls = manifest.get("video_urls", {})

    new_uploads = 0
    for key, local_path in video_keys.items():
        video_file = ASSETS_DIR / local_path
        if not video_file.is_file():
            continue

        filename = video_file.name

        if filename not in existing:
            print(f"  Uploading {filename} ...")
            try:
                upload_file(video_file)
                existing.add(filename)
                new_uploads += 1
            except Exception as exc:
                print(f"  Error uploading {key}: {exc}")
                continue

        # Record URL (covers both newly-uploaded and already-present assets)
        video_urls[key] = f"{base_url}/{filename}"

    manifest["video_urls"] = video_urls

    tmp = MANIFEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST_FILE)

    print(
        f"→ Uploaded {new_uploads} new video(s); "
        f"{len(video_urls)} total URL(s) in manifest."
    )


if __name__ == "__main__":
    main()
