"""
fetch_vk.py — Download all posts from multiple VK walls and save to posts.json

Configure which users to fetch in users.txt (one screen name / numeric ID per line).
"""

import requests
import json
import time
import os
import sys
from pathlib import Path

VK_API_VERSION = "5.199"
ACCESS_TOKEN = os.environ.get("VK_TOKEN", "").strip()
RATE_LIMIT_DELAY = 0.35  # VK allows ~3 requests/sec
USERS_FILE = Path("users.txt")


def vk_api(method, **params):
    params["access_token"] = ACCESS_TOKEN
    params["v"] = VK_API_VERSION
    url = f"https://api.vk.com/method/{method}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"VK API error {err['error_code']}: {err['error_msg']}")
    return data["response"]


def resolve_users(identifiers):
    """Resolve a list of screen names / numeric IDs to full user objects."""
    cleaned = []
    for uid in identifiers:
        uid = uid.strip().rstrip("/")
        if uid.startswith("https://vk.com/"):
            uid = uid[len("https://vk.com/"):]
        if uid.startswith("vk.com/"):
            uid = uid[len("vk.com/"):]
        if uid:
            cleaned.append(uid)
    if not cleaned:
        return []
    result = vk_api(
        "users.get",
        user_ids=",".join(cleaned),
        fields="photo_200,screen_name,domain",
    )
    return result


def enrich_video_attachments(all_posts):
    """Call video.get in batches to add 'files' and 'player' to every video attachment."""
    # Collect unique videos preserving a reference to the dict so we can update it in place
    seen = {}
    for post in all_posts:
        sources = [post] + post.get("copy_history", [])
        for src in sources:
            for att in src.get("attachments", []):
                if att.get("type") == "video":
                    vid = att["video"]
                    key = (vid.get("owner_id"), vid.get("id"))
                    if key not in seen:
                        seen[key] = []
                    seen[key].append(vid)

    if not seen:
        return

    entries = list(seen.items())  # [((owner_id, video_id), [vid_dict, ...]), ...]
    print(f"  Enriching {len(entries)} unique video(s) via video.get...")
    BATCH = 200
    for i in range(0, len(entries), BATCH):
        batch = entries[i : i + BATCH]
        videos_param = ",".join(
            f"{key[0]}_{key[1]}" for key, _ in batch
        )
        try:
            resp = vk_api("video.get", videos=videos_param, extended=0)
            items_by_key = {
                (item["owner_id"], item["id"]): item
                for item in resp.get("items", [])
            }
            for key, vid_dicts in batch:
                enriched = items_by_key.get(key)
                if enriched:
                    files  = enriched.get("files", {})
                    player = enriched.get("player", "")
                    for vd in vid_dicts:
                        if files:
                            vd["files"] = files
                        if player:
                            vd["player"] = player
        except Exception as exc:
            print(f"    Warning: video.get batch failed: {exc}")
        time.sleep(RATE_LIMIT_DELAY)


def fetch_all_posts(owner_id):
    """Paginate through the entire wall for one user."""
    all_posts = []
    all_profiles = {}
    all_groups = {}
    offset = 0
    batch = 100
    total = None

    while True:
        resp = vk_api(
            "wall.get",
            owner_id=owner_id,
            count=batch,
            offset=offset,
            filter="owner",
            extended=1,
        )

        if total is None:
            total = resp["count"]

        items = resp.get("items", [])
        all_posts.extend(items)

        for p in resp.get("profiles", []):
            all_profiles[p["id"]] = p
        for g in resp.get("groups", []):
            all_groups[g["id"]] = g

        fetched = len(all_posts)
        print(f"    {fetched}/{total}...", end="\r")

        if not items or fetched >= total:
            break

        offset += batch
        time.sleep(RATE_LIMIT_DELAY)

    print(f"    {len(all_posts)} posts fetched.      ")
    return all_posts, list(all_profiles.values()), list(all_groups.values())


def load_user_list():
    if not USERS_FILE.exists():
        print(f"ERROR: {USERS_FILE} not found.")
        sys.exit(1)
    lines = USERS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def main():
    if not ACCESS_TOKEN:
        print("ERROR: VK_TOKEN environment variable is not set.")
        print("  export VK_TOKEN=vk1.a.YOUR_TOKEN_HERE")
        sys.exit(1)

    identifiers = load_user_list()
    if not identifiers:
        print(f"ERROR: {USERS_FILE} is empty or has no valid entries.")
        sys.exit(1)

    print(f"→ Resolving {len(identifiers)} user(s)...")
    users = resolve_users(identifiers)
    if not users:
        print("ERROR: Could not resolve any users.")
        sys.exit(1)

    output = {
        "users": [],
        "posts": [],
        "profiles": {},
        "groups": {},
    }

    for user in users:
        name = f"{user['first_name']} {user['last_name']}"
        uid = user["id"]
        print(f"\n→ Fetching posts for {name} (id{uid})...")

        posts, profiles, groups = fetch_all_posts(uid)

        # Tag every post so the site builder knows which user it belongs to
        for post in posts:
            post["_archive_owner_id"] = uid

        output["users"].append(user)
        output["posts"].extend(posts)
        for p in profiles:
            output["profiles"][str(p["id"])] = p
        for g in groups:
            output["groups"][str(g["id"])] = g

        time.sleep(RATE_LIMIT_DELAY)

    output["posts"].sort(key=lambda p: p.get("date", 0), reverse=True)

    print("\n→ Enriching video attachments with direct file URLs...")
    enrich_video_attachments(output["posts"])

    out_path = Path("posts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(output["posts"])
    print(f"\n→ Saved {total} posts from {len(users)} users to {out_path}")


if __name__ == "__main__":
    main()
