"""
build_site.py — Build a static site from posts.json (multi-user, separate feeds)

Output structure:
  _site/
    index.html                  ← overview: one card per person
    {screen_name}/
      index.html                ← that person's posts, page 1
      page2.html
      ...
"""

import json
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path

OUT_DIR = Path("_site")
POSTS_PER_PAGE = 50

# Populated in main() from assets/manifest.json
ASSET_MANIFEST: dict = {"images": {}, "videos": {}}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ts_to_str(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M UTC")

def user_slug(user):
    return user.get("domain") or user.get("screen_name") or f"id{user['id']}"

def user_display_name(user):
    return f"{user.get('first_name','')} {user.get('last_name','')}".strip()

def page_filename(n):
    return "index.html" if n == 1 else f"page{n}.html"


# ─── Attachment renderers ─────────────────────────────────────────────────────

def render_attachment(att):
    kind = att.get("type")

    if kind == "photo":
        photo = att["photo"]
        owner_id = photo.get("owner_id", 0)
        photo_id = photo.get("id", 0)
        key = f"{owner_id}_{photo_id}"
        local = ASSET_MANIFEST.get("images", {}).get(key)
        sizes = sorted(photo.get("sizes", []), key=lambda s: s.get("width", 0), reverse=True)
        if local:
            src   = f"../assets/{local}"
            thumb = src
        elif sizes:
            src   = sizes[0]["url"]
            thumb = next((s["url"] for s in sizes if s.get("width", 0) <= 604), src)
        else:
            return ""
        return (f'<a href="{escape(src)}" target="_blank" rel="noopener">'
                f'<img class="photo" src="{escape(thumb)}" loading="lazy" alt="photo"></a>')

    elif kind == "link":
        link  = att["link"]
        url   = escape(link.get("url", "#"))
        title = escape(link.get("title", url))
        desc  = escape(link.get("description", ""))
        img_html = ""
        if link.get("photo"):
            sizes = sorted(link["photo"].get("sizes", []), key=lambda s: s.get("width", 0))
            if sizes:
                img_html = f'<img class="link-thumb" src="{escape(sizes[-1]["url"])}" alt="">'
        desc_html = f"<br><small>{desc}</small>" if desc else ""
        return (f'<a class="link-card" href="{url}" target="_blank" rel="noopener">'
                f'{img_html}<span class="link-text"><strong>{title}</strong>{desc_html}</span></a>')

    elif kind in ("video", "short_video"):
        vid    = att[kind]
        owner_id = vid.get("owner_id", 0)
        video_id = vid.get("id", 0)
        key    = f"{owner_id}_{video_id}"
        local  = ASSET_MANIFEST["videos"].get(key)
        title  = escape(vid.get("title", "Video"))
        thumb  = next((vid[k] for k in ["photo_800","photo_640","photo_320","photo_130"] if vid.get(k)), "")
        # Also check the newer 'image' array format
        if not thumb and vid.get("image"):
            img_list = sorted(vid["image"], key=lambda s: s.get("width", 0), reverse=True)
            if img_list:
                thumb = img_list[0].get("url", "")
        if local:
            src = f"../assets/{local}"
            poster_attr = f' poster="{escape(thumb)}"' if thumb else ""
            return (f'<video class="local-video" controls preload="none"'
                    f' aria-label="{title}"{poster_attr}>'
                    f'<source src="{escape(src)}">'
                    f'</video>'
                    f'<span class="video-title">{title}</span>')
        else:
            # Link to the original source if available, otherwise fall back to the VK page
            player  = vid.get("player", "")
            link_url = player if player else f"https://vk.com/video{owner_id}_{video_id}"
            img_tag = f'<img class="video-thumb" src="{escape(thumb)}" alt="">' if thumb else ""
            return (f'<a class="video-card" href="{escape(link_url)}" target="_blank" rel="noopener">'
                    f'{img_tag}<span class="play-icon">▶</span>'
                    f'<span class="video-title">{title}</span></a>')

    elif kind == "audio":
        audio = att["audio"]
        return f'<div class="audio-card">🎵 {escape(audio.get("artist",""))} — {escape(audio.get("title",""))}</div>'

    elif kind == "doc":
        doc = att["doc"]
        ext = escape(doc.get("ext", "")).upper()
        return (f'<a class="doc-card" href="{escape(doc.get("url","#"))}" target="_blank" rel="noopener">'
                f'📄 {escape(doc.get("title","Document"))} <small class="ext">{ext}</small></a>')

    return ""


def render_repost(copy, profiles_map, groups_map):
    owner_id = copy.get("from_id") or copy.get("owner_id", 0)
    if owner_id and owner_id > 0:
        owner = profiles_map.get(str(owner_id), {})
        name  = escape(f"{owner.get('first_name','')} {owner.get('last_name','')}".strip() or "Unknown")
        link  = f"https://vk.com/id{owner_id}"
    else:
        gid   = str(abs(owner_id)) if owner_id else "0"
        owner = groups_map.get(gid, {})
        name  = escape(owner.get("name", "Unknown group"))
        link  = f"https://vk.com/club{gid}"

    copy_text = escape(copy.get("text", "")).replace("\n", "<br>")
    copy_atts = "".join(filter(None, (render_attachment(a) for a in copy.get("attachments", []))))

    return (f'<blockquote class="repost">'
            f'<a class="repost-author" href="{link}" target="_blank" rel="noopener">{name}</a>'
            f'<div class="repost-text">{copy_text}</div>'
            f'<div class="repost-attachments">{copy_atts}</div>'
            f'</blockquote>')


def render_post_card(post, profiles_map, groups_map):
    date     = ts_to_str(post["date"])
    post_id  = post.get("id", "")
    owner_id = post.get("owner_id", "")
    vk_url   = f"https://vk.com/wall{owner_id}_{post_id}"

    text = escape(post.get("text", "")).replace("\n", "<br>")
    atts = "".join(filter(None, (render_attachment(a) for a in post.get("attachments", []))))
    reposts_html = "".join(render_repost(c, profiles_map, groups_map) for c in post.get("copy_history", []))

    likes    = post.get("likes",    {}).get("count", 0)
    reposts  = post.get("reposts",  {}).get("count", 0)
    comments = post.get("comments", {}).get("count", 0)
    views    = post.get("views",    {}).get("count", 0)
    stats = " &nbsp;".join(filter(None, [
        f'<span title="Likes">♥ {likes}</span>'        if likes    else "",
        f'<span title="Reposts">↩ {reposts}</span>'    if reposts  else "",
        f'<span title="Comments">💬 {comments}</span>' if comments else "",
        f'<span title="Views">👁 {views}</span>'        if views    else "",
    ]))

    badge      = '<span class="badge repost-badge">Repost</span>' if post.get("copy_history") else ""
    stats_html = f'<footer class="post-stats">{stats}</footer>' if stats else ""
    atts_html  = f'<div class="post-attachments">{atts}</div>'  if atts  else ""

    return (f'<article class="post" id="post-{post_id}">'
            f'<header class="post-header">'
            f'<time class="post-date">{date}</time>{badge}'
            f'<a class="post-link" href="{vk_url}" target="_blank" rel="noopener" title="Open on VK">↗</a>'
            f'</header>'
            f'<div class="post-text">{text}</div>'
            f'{reposts_html}{atts_html}{stats_html}'
            f'</article>')


# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3a;
  --text:#e2e8f0; --muted:#8892a4; --accent:#5b8cff; --link:#6eb6ff; --radius:12px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:var(--bg);color:var(--text);line-height:1.65;min-height:100vh}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}

/* Header */
.site-header{background:var(--surface);border-bottom:1px solid var(--border);
             padding:20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.back-link{font-size:0.85rem;color:var(--muted);white-space:nowrap;flex-shrink:0}
.back-link:hover{color:var(--accent);text-decoration:none}
.header-avatar{width:52px;height:52px;border-radius:50%;flex-shrink:0}
.header-text{flex:1;min-width:0}
.header-text h1{font-size:1.15rem;font-weight:700}
.header-text p{color:var(--muted);font-size:0.82rem;margin-top:2px}

main{max-width:680px;margin:0 auto;padding:32px 16px 64px}

/* Post card */
.post{background:var(--surface);border:1px solid var(--border);
      border-radius:var(--radius);padding:20px;margin-bottom:20px}
.post-header{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.post-date{color:var(--muted);font-size:0.82rem}
.post-link{margin-left:auto;color:var(--muted);font-size:1rem;transition:color .15s}
.post-link:hover{color:var(--accent);text-decoration:none}
.badge{font-size:.7rem;padding:2px 8px;border-radius:999px;
       font-weight:600;letter-spacing:.03em;text-transform:uppercase}
.repost-badge{background:#2a3a5a;color:#7aadff}
.post-text{white-space:pre-wrap;word-break:break-word;font-size:.97rem}
.post-text:empty{display:none}

/* Attachments */
.post-attachments,.repost-attachments{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.photo{max-width:100%;max-height:400px;border-radius:8px;display:block;object-fit:cover}
.link-card{display:flex;align-items:flex-start;gap:10px;background:var(--bg);
           border:1px solid var(--border);border-radius:8px;padding:10px 14px;
           width:100%;color:var(--text)}
.link-card:hover{border-color:var(--accent);text-decoration:none}
.link-thumb{width:60px;height:60px;object-fit:cover;border-radius:6px;flex-shrink:0}
.link-text{font-size:.88rem}
.video-card{position:relative;display:inline-block;border-radius:8px;
            overflow:hidden;max-width:100%;cursor:pointer}
.video-thumb{display:block;max-width:100%;max-height:300px;object-fit:cover}
.play-icon{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
           background:rgba(0,0,0,.6);color:#fff;font-size:1.8rem;
           width:56px;height:56px;display:flex;align-items:center;
           justify-content:center;border-radius:50%}
.video-title{display:block;background:rgba(0,0,0,.7);color:#fff;font-size:.8rem;padding:6px 10px}
.local-video{display:block;max-width:100%;max-height:400px;border-radius:8px}
.audio-card,.doc-card{background:var(--bg);border:1px solid var(--border);
                       border-radius:8px;padding:8px 14px;font-size:.88rem}
.doc-card{display:inline-block}
.ext{color:var(--muted)}

/* Reposts */
blockquote.repost{border-left:3px solid var(--accent);background:#1e2133;
                  border-radius:0 8px 8px 0;padding:12px 14px;margin-top:12px}
.repost-author{font-weight:600;font-size:.88rem;color:var(--accent);display:block;margin-bottom:6px}
.repost-text{font-size:.92rem;white-space:pre-wrap}
.repost-text:empty{display:none}

/* Stats */
.post-stats{margin-top:14px;font-size:.8rem;color:var(--muted);display:flex;gap:4px}

/* Pagination */
.pagination{display:flex;justify-content:center;gap:12px;margin-top:40px}
.pagination a{background:var(--surface);border:1px solid var(--border);
              border-radius:8px;padding:8px 18px;color:var(--text);font-size:.9rem}
.pagination a:hover{border-color:var(--accent);text-decoration:none}
.page-info{color:var(--muted);font-size:.85rem;text-align:center;margin-top:16px}

/* Overview / index page */
.overview-header{background:var(--surface);border-bottom:1px solid var(--border);
                 padding:40px 20px;text-align:center}
.overview-header h1{font-size:1.8rem;font-weight:800;margin-bottom:6px}
.overview-header p{color:var(--muted);font-size:.9rem}
.user-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
           gap:16px;padding:32px 20px 64px;max-width:900px;margin:0 auto}
.user-card{background:var(--surface);border:1px solid var(--border);
           border-radius:var(--radius);padding:20px;
           display:flex;align-items:center;gap:16px;transition:border-color .15s}
.user-card:hover{border-color:var(--accent);text-decoration:none}
.user-card img{width:64px;height:64px;border-radius:50%;flex-shrink:0}
.user-card-info strong{display:block;color:var(--text);font-size:1rem;margin-bottom:2px}
.user-card-info small{color:var(--muted);font-size:.82rem}
"""


# ─── Page templates ───────────────────────────────────────────────────────────

def build_user_page(page_num, total_pages, post_cards, user, total_posts):
    name   = escape(user_display_name(user))
    slug   = user_slug(user)
    domain = escape(slug)
    avatar = escape(user.get("photo_200", ""))
    avatar_tag = f'<img class="header-avatar" src="{avatar}" alt="">' if avatar else ""
    vk_url = f"https://vk.com/{domain}"

    posts_block = "\n".join(post_cards) if post_cards else (
        '<p style="color:var(--muted);text-align:center;margin-top:60px">No posts found.</p>')

    prev_link  = f'<a href="{page_filename(page_num-1)}">← Newer</a>' if page_num > 1 else ""
    next_link  = f'<a href="{page_filename(page_num+1)}">Older →</a>' if page_num < total_pages else ""
    pagination = f'<nav class="pagination">{prev_link}{next_link}</nav>' if prev_link or next_link else ""
    page_info  = f'<p class="page-info">Page {page_num} of {total_pages} &nbsp;·&nbsp; {total_posts} posts</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name} — VK Archive</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="site-header">
    <a class="back-link" href="../index.html">← All people</a>
    {avatar_tag}
    <div class="header-text">
      <h1>{name}</h1>
      <p><a href="{vk_url}" target="_blank" rel="noopener">@{domain}</a>
         &nbsp;·&nbsp; {total_posts} archived posts</p>
    </div>
  </header>
  <main>
    {posts_block}
    {pagination}
    {page_info}
  </main>
</body>
</html>"""


def build_index_page(users_meta):
    cards_html = ""
    for m in users_meta:
        user   = m["user"]
        slug   = user_slug(user)
        name   = escape(user_display_name(user))
        domain = escape(slug)
        avatar = escape(user.get("photo_200", ""))
        count  = m["count"]
        img_tag = f'<img src="{avatar}" alt="">' if avatar else ""
        cards_html += (
            f'<a class="user-card" href="{slug}/index.html">'
            f'{img_tag}'
            f'<div class="user-card-info">'
            f'<strong>{name}</strong>'
            f'<small>@{domain} &nbsp;·&nbsp; {count} posts</small>'
            f'</div></a>\n'
        )

    total_posts = sum(m["count"] for m in users_meta)
    n_users = len(users_meta)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VK Archive</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="overview-header">
    <h1>VK Archive</h1>
    <p>{n_users} people &nbsp;·&nbsp; {total_posts} posts total</p>
  </div>
  <div class="user-grid">
    {cards_html}
  </div>
</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global ASSET_MANIFEST

    posts_file = Path("posts.json")
    if not posts_file.exists():
        print("ERROR: posts.json not found. Run fetch_vk.py first.")
        raise SystemExit(1)

    manifest_file = Path("assets/manifest.json")
    if manifest_file.exists():
        with open(manifest_file, encoding="utf-8") as f:
            ASSET_MANIFEST = json.load(f)
        n_imgs = len(ASSET_MANIFEST.get("images", {}))
        n_vids = len(ASSET_MANIFEST.get("videos", {}))
        print(f"→ Loaded asset manifest ({n_imgs} images, {n_vids} videos)")
    else:
        print("→ No asset manifest found; all media will link to VK")

    print("→ Loading posts.json...")
    with open(posts_file, encoding="utf-8") as f:
        data = json.load(f)

    users        = data["users"]
    all_posts    = data["posts"]
    profiles_map = data.get("profiles", {})
    groups_map   = data.get("groups", {})

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # Copy downloaded assets into _site/assets/ so they are served by Pages
    assets_src = Path("assets")
    if assets_src.exists():
        shutil.copytree(assets_src, OUT_DIR / "assets")
        print("→ Copied assets/ → _site/assets/")

    # Group posts by owner
    posts_by_uid = {u["id"]: [] for u in users}
    for post in all_posts:
        uid = post.get("_archive_owner_id") or post.get("owner_id")
        if uid in posts_by_uid:
            posts_by_uid[uid].append(post)

    users_meta = []

    for user in users:
        uid   = user["id"]
        slug  = user_slug(user)
        name  = user_display_name(user)
        posts = posts_by_uid.get(uid, [])
        posts.sort(key=lambda p: p.get("date", 0), reverse=True)

        total_posts = len(posts)
        total_pages = max(1, (total_posts + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
        user_dir    = OUT_DIR / slug
        user_dir.mkdir(parents=True, exist_ok=True)

        print(f"→ {name}: {total_posts} posts → {total_pages} page(s) in _site/{slug}/")

        for page_num in range(1, total_pages + 1):
            chunk = posts[(page_num - 1) * POSTS_PER_PAGE : page_num * POSTS_PER_PAGE]
            cards = [render_post_card(p, profiles_map, groups_map) for p in chunk]
            html  = build_user_page(page_num, total_pages, cards, user, total_posts)
            (user_dir / page_filename(page_num)).write_text(html, encoding="utf-8")

        users_meta.append({"user": user, "count": total_posts})

    (OUT_DIR / "index.html").write_text(build_index_page(users_meta), encoding="utf-8")
    print("→ Wrote _site/index.html (overview)")
    print(f"→ Done.")


if __name__ == "__main__":
    main()
