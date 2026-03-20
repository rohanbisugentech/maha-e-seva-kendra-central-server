"""
╔══════════════════════════════════════════════════════════════╗
║  MAHA E-SEVA KENDRA — Central Server                        ║
║  REST API for 3 desktop shops + Full Admin Web Dashboard    ║
╚══════════════════════════════════════════════════════════════╝

Run:  python server.py
Deploy: Railway / Render / DigitalOcean (see README)
"""

import os, datetime, uuid, bcrypt
from functools import wraps
from flask import (Flask, request, jsonify, render_template,
                   session, redirect, url_for, abort)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_

# ── App setup ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "seva-kendra-secret-2024-change-this")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///seva_central.db"           # local fallback; use PostgreSQL in production
).replace("postgres://", "postgresql://")  # Railway fix

app.config["SQLALCHEMY_DATABASE_URI"]        = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

API_KEY = os.environ.get("API_KEY", "seva-api-key-2024")   # shops must send this header

SHOPS = {
    "shop_1": "Shop 1 — Kendra A",
    "shop_2": "Shop 2 — Kendra B",
    "shop_3": "Shop 3 — Kendra C",
    "admin":  "Admin",
}

# ── Models ─────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    shop_id       = db.Column(db.String(30), nullable=False)
    full_name     = db.Column(db.String(100), default="")
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class CustomerEntry(db.Model):
    __tablename__ = "customer_entries"
    id             = db.Column(db.Integer, primary_key=True)
    remote_id      = db.Column(db.String(50), unique=True, nullable=True)  # local PC id
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"))
    shop_id        = db.Column(db.String(30), nullable=False)
    handled_by     = db.Column(db.String(100), default="")
    customer_name  = db.Column(db.String(200), nullable=False)
    mobile_number  = db.Column(db.String(20), default="")
    work_address   = db.Column(db.String(300), default="")
    service_name   = db.Column(db.String(300), default="")
    expected_time  = db.Column(db.DateTime)
    total_amount   = db.Column(db.Float, default=0.0)
    amount_paid    = db.Column(db.Float, default=0.0)
    pending_amount = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(30), default="Not Paid")
    work_status    = db.Column(db.String(30), default="Pending")
    pending_reason = db.Column(db.String(300), default="")
    remarks        = db.Column(db.String(500), default="")
    reference      = db.Column(db.String(100), default="")
    created_at     = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                               onupdate=datetime.datetime.utcnow)


class GeneralEntry(db.Model):
    __tablename__ = "general_entries"
    id           = db.Column(db.Integer, primary_key=True)
    remote_id    = db.Column(db.String(50), unique=True, nullable=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"))
    shop_id      = db.Column(db.String(30), nullable=False)
    handled_by   = db.Column(db.String(100), default="")
    service_name = db.Column(db.String(200), nullable=False)
    total_amount = db.Column(db.Float, default=0.0)
    created_at   = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80))
    shop_id    = db.Column(db.String(30))
    action     = db.Column(db.String(50))
    detail     = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


def init_db():
    db.create_all()
    if not User.query.filter_by(username="admin").first():
        accounts = [
            ("admin",  "Admin@2024",  "admin",  "Admin Master"),
            ("shop1",  "Shop1@2024",  "shop_1", "Kendra A"),
            ("shop2",  "Shop2@2024",  "shop_2", "Kendra B"),
            ("shop3",  "Shop3@2024",  "shop_3", "Kendra C"),
        ]
        for uname, pwd, shop, fname in accounts:
            pw = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
            db.session.add(User(username=uname, password_hash=pw,
                                shop_id=shop, full_name=fname))
        db.session.commit()


def log(username, shop_id, action, detail=""):
    db.session.add(ActivityLog(username=username, shop_id=shop_id,
                               action=action, detail=detail))
    db.session.commit()


# ── Auth helpers ───────────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("web_login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("shop_id") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def dt(s):
    """Parse ISO datetime string safely."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


# ══════════════════════════════════════════════════════════
#  REST API  (used by desktop Python app on each shop PC)
# ══════════════════════════════════════════════════════════

@app.route("/api/sync/entries", methods=["POST"])
@require_api_key
def sync_entries():
    """Shop PC calls this to push new/updated entries to the cloud."""
    data    = request.get_json(force=True)
    entries = data.get("entries", [])
    shop_id = data.get("shop_id")
    user    = data.get("username", "unknown")

    created = updated = 0
    for e in entries:
        rid = e.get("remote_id") or e.get("reference") or str(uuid.uuid4())
        existing = CustomerEntry.query.filter_by(remote_id=rid).first()
        if existing:
            # Update if newer
            existing.customer_name  = e.get("customer_name", existing.customer_name)
            existing.mobile_number  = e.get("mobile_number", existing.mobile_number)
            existing.work_address   = e.get("work_address",  existing.work_address)
            existing.service_name   = e.get("service_name",  existing.service_name)
            existing.handled_by     = e.get("handled_by",    existing.handled_by)
            existing.expected_time  = dt(e.get("expected_time"))
            existing.total_amount   = e.get("total_amount",   existing.total_amount)
            existing.amount_paid    = e.get("amount_paid",    existing.amount_paid)
            existing.pending_amount = e.get("pending_amount", existing.pending_amount)
            existing.payment_status = e.get("payment_status", existing.payment_status)
            existing.work_status    = e.get("work_status",    existing.work_status)
            existing.pending_reason = e.get("pending_reason", existing.pending_reason)
            existing.remarks        = e.get("remarks",        existing.remarks)
            existing.reference      = e.get("reference",      existing.reference)
            existing.updated_at     = datetime.datetime.utcnow()
            updated += 1
        else:
            u = User.query.filter_by(username=user).first()
            new = CustomerEntry(
                remote_id      = rid,
                user_id        = u.id if u else None,
                shop_id        = shop_id,
                customer_name  = e.get("customer_name", ""),
                mobile_number  = e.get("mobile_number", ""),
                work_address   = e.get("work_address",  ""),
                service_name   = e.get("service_name",  ""),
                handled_by     = e.get("handled_by",    ""),
                expected_time  = dt(e.get("expected_time")),
                total_amount   = e.get("total_amount",   0),
                amount_paid    = e.get("amount_paid",    0),
                pending_amount = e.get("pending_amount", 0),
                payment_status = e.get("payment_status", "Not Paid"),
                work_status    = e.get("work_status",    "Pending"),
                pending_reason = e.get("pending_reason", ""),
                remarks        = e.get("remarks",        ""),
                reference      = e.get("reference",      rid),
                created_at     = dt(e.get("created_at")) or datetime.datetime.utcnow(),
            )
            db.session.add(new)
            created += 1

    db.session.commit()
    log(user, shop_id, "SYNC", f"created:{created} updated:{updated}")
    return jsonify({"status": "ok", "created": created, "updated": updated})


@app.route("/api/sync/general", methods=["POST"])
@require_api_key
def sync_general():
    data    = request.get_json(force=True)
    entries = data.get("entries", [])
    shop_id = data.get("shop_id")
    user    = data.get("username", "unknown")

    created = 0
    for e in entries:
        rid = e.get("remote_id") or str(uuid.uuid4())
        if GeneralEntry.query.filter_by(remote_id=rid).first():
            continue
        u = User.query.filter_by(username=user).first()
        db.session.add(GeneralEntry(
            remote_id    = rid,
            user_id      = u.id if u else None,
            shop_id      = shop_id,
            handled_by   = e.get("handled_by", ""),
            service_name = e.get("service_name", "General"),
            total_amount = e.get("total_amount", 0),
            created_at   = dt(e.get("created_at")) or datetime.datetime.utcnow(),
        ))
        created += 1

    db.session.commit()
    return jsonify({"status": "ok", "created": created})


@app.route("/api/ping")
def ping():
    return jsonify({"status": "online", "time": datetime.datetime.utcnow().isoformat()})


# ══════════════════════════════════════════════════════════
#  CENTRAL API DEFAULT ROUTE
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "message": "MAHA E-SEVA KENDRA Central API is running. Send POST requests to /api/sync/entries"
    })


# ── Initialise DB on startup (works with gunicorn / Railway) ──
with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)