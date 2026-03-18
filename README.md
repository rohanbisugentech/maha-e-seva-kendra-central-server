# ◈ MAHA E-SEVA KENDRA — Central Server

**Flask web server + REST API. Deploy once, all 3 shops sync to it.**

---

## 📁 Files
```
seva_central/
├── server.py          ← Flask app (API + web dashboard)
├── cloud_sync.py      ← Copy this to each shop PC alongside main.py
├── templates/         ← Web dashboard HTML pages
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── entries.html
│   ├── reports.html
│   ├── reminders.html
│   └── activity.html
├── requirements.txt
├── Procfile           ← For Railway/Render
└── README.md
```

---

## 🚀 DEPLOY IN 10 MINUTES — Railway.app (Free)

### Step 1: Push to GitHub
1. Create a free GitHub account at github.com
2. Create a new repository called `seva-kendra-server`
3. Upload all files from `seva_central/` folder to it

### Step 2: Deploy on Railway
1. Go to **railway.app** → Sign up free
2. Click **New Project → Deploy from GitHub**
3. Select your `seva-kendra-server` repo
4. Railway auto-detects Procfile and deploys

### Step 3: Add PostgreSQL
1. In your Railway project → **+ Add Service → Database → PostgreSQL**
2. Railway auto-sets `DATABASE_URL` environment variable ✅

### Step 4: Set environment variables in Railway
Go to your app → **Variables** tab and add:
```
SECRET_KEY     = any-random-long-string-here-change-this
API_KEY        = seva-api-key-2024
```

### Step 5: Get your URL
Railway gives you a URL like: `https://seva-kendra-server-production.up.railway.app`
**That's your admin dashboard URL** — open it from any browser, anywhere!

---

## 🔑 Web Dashboard Login

Open `https://YOUR-URL.railway.app` in any browser:

| Username | Password    | Access          |
|----------|-------------|-----------------|
| admin    | Admin@2024  | All shops, full |
| shop1    | Shop1@2024  | Shop 1 view     |
| shop2    | Shop2@2024  | Shop 2 view     |
| shop3    | Shop3@2024  | Shop 3 view     |

> Change passwords: update the `init_db()` accounts list in server.py before deploying.

---

## 🔄 CONNECT SHOP PCs (desktop app sync)

### Step 1: Copy cloud_sync.py
Put `cloud_sync.py` in the same folder as `main.py` on each shop PC.

### Step 2: Edit cloud_sync.py — change these 2 lines:
```python
SERVER_URL = "https://YOUR-APP.railway.app"   # ← your actual Railway URL
API_KEY    = "seva-api-key-2024"              # ← must match Railway env variable
```

### Step 3: Add 3 lines to main.py ShopWindow:
```python
# At top of main.py:
from cloud_sync import CloudSync

# In ShopWindow.__init__, after self._setup_reminders():
try:
    self.cloud = CloudSync(self.user, Session, self)
    self.cloud.start_auto_sync()
    self.cloud.sync_now()
except Exception as e:
    print(f"Cloud sync init failed: {e}")

# In ShopWindow.refresh_all():
if hasattr(self, 'cloud'):
    self.cloud.sync_now()
```

### How sync works:
- Auto-syncs every **5 minutes** in the background
- Also syncs immediately after every Add/Edit/Delete
- Works in a background thread — desktop app stays fast
- If internet is down: data stays local, syncs when connection returns
- One-way: **desktop → cloud** (cloud is read-only admin view)

---

## 📊 What Admin Sees Online

| Page | What's There |
|------|-------------|
| **Dashboard** | All 8 stat cards + shop-wise breakdown + overdue/upcoming tables. Auto-refreshes every 60s |
| **Entries** | All entries with full filter: search, pay status, work status, shop, date range. Paginated |
| **Reports** | Today / Week / Month / Custom. Revenue, collected, pending. Service breakdown. Shop breakdown |
| **Reminders** | Overdue, upcoming deadlines, pending payments. Adjustable window (3d to 30d) |
| **Activity Log** | Every login, sync, add, edit, delete — with timestamp, user, shop |

---

## 💰 Hosting Cost

| Platform | Cost | Notes |
|----------|------|-------|
| **Railway.app** | ~₹0–400/mo | Free tier: 500hr/mo. Paid: ~$5/mo |
| **Render.com** | Free | Free PostgreSQL (90 days), then ~$7/mo |
| **Hostinger VPS** | ~₹200/mo | Cheapest; needs manual setup |

Railway is recommended — easiest, auto-deploys from GitHub.

---

## 🔒 Security Notes

1. Change `API_KEY` in Railway env vars (don't use the default)
2. Change all passwords in `init_db()` before first deploy
3. All traffic is HTTPS (Railway provides SSL automatically)
4. Desktop apps send data via encrypted API key — shops can't see each other's data
