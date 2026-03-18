"""
cloud_sync.py  —  Add this file next to main.py on each shop PC.
Syncs local SQLite data to the central cloud server.

Usage in main.py ShopWindow.__init__:
    from cloud_sync import CloudSync
    self.cloud = CloudSync(self.user)
    self.cloud.start_auto_sync()   # syncs every 5 minutes
"""

import datetime, threading, requests
from sqlalchemy.orm import sessionmaker

# ─── EDIT THESE TWO LINES ───────────────────────────────────────────
SERVER_URL = "https://YOUR-APP.railway.app"   # your deployed server URL
API_KEY    = "seva-api-key-2024"              # must match server.py API_KEY
# ────────────────────────────────────────────────────────────────────

SYNC_INTERVAL = 300   # seconds (5 minutes)


class CloudSync:
    def __init__(self, user, db_session_factory, parent_widget=None):
        """
        user               - logged-in User ORM object from main.py
        db_session_factory - the Session = sessionmaker(bind=engine) from main.py
        parent_widget      - optional PyQt5 widget for status messages
        """
        self.user    = user
        self.Session = db_session_factory
        self.parent  = parent_widget
        self._timer  = None
        self._last_sync = None

    # ── Public ──────────────────────────────────────────────────────

    def sync_now(self):
        """Call this after any Add/Edit/Delete operation."""
        thread = threading.Thread(target=self._do_sync, daemon=True)
        thread.start()

    def start_auto_sync(self):
        """Auto-syncs every SYNC_INTERVAL seconds."""
        self._schedule_next()

    def stop(self):
        if self._timer:
            self._timer.cancel()

    def status(self):
        if self._last_sync:
            return f"Last sync: {self._last_sync.strftime('%H:%M:%S')}"
        return "Not synced yet"

    # ── Internal ────────────────────────────────────────────────────

    def _schedule_next(self):
        self._timer = threading.Timer(SYNC_INTERVAL, self._auto_sync_tick)
        self._timer.daemon = True
        self._timer.start()

    def _auto_sync_tick(self):
        self._do_sync()
        self._schedule_next()

    def _do_sync(self):
        try:
            self._sync_main_entries()
            self._sync_general_entries()
            self._last_sync = datetime.datetime.now()
            print(f"[CloudSync] ✅ Synced at {self._last_sync.strftime('%H:%M:%S')}")
        except Exception as ex:
            print(f"[CloudSync] ❌ Sync failed: {ex}")

    def _sync_main_entries(self):
        from main import CustomerEntry   # import your ORM model
        session = self.Session()
        try:
            # Send all entries modified in last 24 hours (or all if first sync)
            since = datetime.datetime.now() - datetime.timedelta(hours=24)
            entries = session.query(CustomerEntry).filter(
                CustomerEntry.shop_id == self.user.shop_id,
                CustomerEntry.updated_at >= since
            ).all()

            if not entries:
                return

            payload = {
                "shop_id":  self.user.shop_id,
                "username": self.user.username,
                "entries": [
                    {
                        "remote_id":      str(e.id),
                        "reference":      e.reference or "",
                        "customer_name":  e.customer_name,
                        "mobile_number":  e.mobile_number or "",
                        "work_address":   e.work_address  or "",
                        "service_name":   e.service_name  or "",
                        "handled_by":     e.handled_by    or "",
                        "expected_time":  e.expected_time.isoformat() if e.expected_time else None,
                        "total_amount":   e.total_amount,
                        "amount_paid":    e.amount_paid,
                        "pending_amount": e.pending_amount,
                        "payment_status": e.payment_status or "",
                        "work_status":    e.work_status    or "",
                        "pending_reason": e.pending_reason or "",
                        "remarks":        e.remarks        or "",
                        "created_at":     e.created_at.isoformat() if e.created_at else None,
                    }
                    for e in entries
                ]
            }

            resp = requests.post(
                f"{SERVER_URL}/api/sync/entries",
                json=payload,
                headers={"X-API-Key": API_KEY},
                timeout=15
            )
            resp.raise_for_status()
        finally:
            session.close()

    def _sync_general_entries(self):
        try:
            from main import GeneralEntry
        except ImportError:
            return

        session = self.Session()
        try:
            since = datetime.datetime.now() - datetime.timedelta(hours=24)
            entries = session.query(GeneralEntry).filter(
                GeneralEntry.shop_id == self.user.shop_id,
                GeneralEntry.created_at >= since
            ).all()

            if not entries:
                return

            payload = {
                "shop_id":  self.user.shop_id,
                "username": self.user.username,
                "entries": [
                    {
                        "remote_id":    f"gen-{e.id}",
                        "service_name": e.service_name,
                        "handled_by":   e.handled_by or "",
                        "total_amount": e.total_amount,
                        "created_at":   e.created_at.isoformat() if e.created_at else None,
                    }
                    for e in entries
                ]
            }

            resp = requests.post(
                f"{SERVER_URL}/api/sync/general",
                json=payload,
                headers={"X-API-Key": API_KEY},
                timeout=15
            )
            resp.raise_for_status()
        finally:
            session.close()


# ─────────────────────────────────────────────────────────────────────
#  HOW TO ADD SYNC TO main.py  (ShopWindow class)
# ─────────────────────────────────────────────────────────────────────
#
#  1. At top of main.py, add:
#       from cloud_sync import CloudSync
#
#  2. In ShopWindow.__init__, after self._setup_reminders(), add:
#       try:
#           self.cloud = CloudSync(self.user, Session, self)
#           self.cloud.start_auto_sync()
#           self.cloud.sync_now()   # immediate sync on startup
#       except Exception as e:
#           print(f"Cloud sync init failed: {e}")
#
#  3. In ShopWindow.refresh_all(), add at the end:
#       if hasattr(self, 'cloud'):
#           self.cloud.sync_now()
#
#  That's it. Syncs run in background threads — desktop app stays fast.
# ─────────────────────────────────────────────────────────────────────
