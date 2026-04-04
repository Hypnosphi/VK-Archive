# VK Archive → GitHub Pages

Back up every post from your personal VK wall and publish it as a fast,
searchable static site — automatically refreshed every day.

---

## Step 1 — Get a VK Access Token

You need a long-lived access token with `wall`, `photos`, and `offline` permissions.
The `offline` scope prevents the token from expiring.

### 1a. Create a VK Application

1. Go to **https://vk.com/apps?act=manage** and click **Create**.
2. Choose:
   - **Title:** anything (e.g. "My Archive")
   - **Platform:** `Standalone application`
3. Click **Connect application** and confirm.
4. Open the newly created app, go to **Settings** tab.
5. Note your **App ID** (the number in the URL or shown on the page).

### 1b. Authorize and Grab the Token

Paste this URL into your browser — **replace `YOUR_APP_ID`** with the number from step 1a:

```
https://oauth.vk.com/authorize?client_id=YOUR_APP_ID&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=wall,photos,offline&response_type=token&v=5.199
```

1. VK will ask you to log in (if not already) and grant the app permissions.
2. After you click **Allow**, you'll be redirected to a blank page.
3. Look at the URL bar — it will look like:
   ```
   https://oauth.vk.com/blank.html#access_token=vk1.a.VERY_LONG_STRING&expires_in=0&user_id=12345678
   ```
4. Copy everything after `access_token=` and before `&expires_in` — that's your token.

> **Keep this token private.** It gives read access to your VK account.
> The `expires_in=0` means it never expires (because you included `offline`).

---

## Step 2 — Set Up the GitHub Repository

```bash
# Clone or fork this repo, then push it to a new private GitHub repo
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Add the token as a GitHub Secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Name: `VK_TOKEN`
4. Value: paste the token you copied in Step 1b.
5. Click **Add secret**.

---

## Step 3 — Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**.
2. Under **Source**, select **GitHub Actions**.
3. Save.

---

## Step 4 — Run the Workflow

1. Go to **Actions** tab in your repo.
2. Click **Fetch & Deploy VK Archive** → **Run workflow** → **Run workflow**.
3. Wait ~1–2 minutes. Your archive will be live at:
   ```
   https://YOUR_USERNAME.github.io/YOUR_REPO/
   ```

The workflow also runs **automatically every day at 03:00 UTC** to pick up new posts.

---

## Local Usage (Optional)

If you want to run everything locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Set your token
export VK_TOKEN=vk1.a.YOUR_TOKEN_HERE

# Fetch posts (saves posts.json)
python fetch_vk.py

# Build the site (outputs to _site/)
python build_site.py

# Preview locally
cd _site && python -m http.server 8080
# Then open http://localhost:8080
```

---

## Configuring which users to archive

Edit **`users.txt`** — one entry per line. You can use any of these formats:

```
durov
id123456789
https://vk.com/another_user
```

Lines starting with `#` are ignored. The file ships with placeholder entries —
replace them with the five (or more) accounts you want to back up.

---

## Site structure

```
_site/
  index.html              ← directory of all archived profiles
  users/
    durov/
      index.html          ← page 1 of their posts
      page2.html …
    id123456789/
      index.html
      …
```

Each person gets their own paginated feed (50 posts/page). The index page
shows all profiles as cards with avatar, name, and post count.

---

## What Gets Archived

| Content | Included |
|---------|----------|
| Text posts | ✅ |
| Photos | ✅ (thumbnail + link to full res) |
| Reposts | ✅ (shown as quotes with original author) |
| Links | ✅ (with thumbnail + description) |
| Videos | ✅ (thumbnail + link to VK) |
| Audio | ✅ (artist / title) |
| Documents | ✅ (download link) |
| Likes / reposts / views count | ✅ |

---

## Files

```
.
├── users.txt              # ← edit this: one VK user per line
├── fetch_vk.py            # Fetches all posts via VK API → posts.json
├── build_site.py          # Generates static HTML site from posts.json
├── requirements.txt
├── posts.json             # Committed back to repo by CI (versioned history)
└── .github/
    └── workflows/
        └── deploy.yml     # GitHub Actions pipeline
```
