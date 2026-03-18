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
#  WEB DASHBOARD  (admin + shop login via browser)
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("web_login"))


@app.route("/login", methods=["GET", "POST"])
def web_login():
    error = None
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd   = request.form.get("password", "")
        user  = User.query.filter_by(username=uname, is_active=True).first()
        if user and bcrypt.checkpw(pwd.encode(), user.password_hash.encode()):
            session["user_id"]   = user.id
            session["username"]  = user.username
            session["shop_id"]   = user.shop_id
            session["full_name"] = user.full_name
            log(user.username, user.shop_id, "WEB_LOGIN")
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("web_login"))


@app.route("/dashboard")
@login_required
def dashboard():
    shop_id  = session["shop_id"]
    shops    = [k for k in SHOPS if k != "admin"] if shop_id == "admin" else [shop_id]

    # Stats
    base  = CustomerEntry.query.filter(CustomerEntry.shop_id.in_(shops))
    today = datetime.date.today()
    ts    = datetime.datetime.combine(today, datetime.time.min)
    te    = datetime.datetime.combine(today, datetime.time.max)

    stats = {
        "total":    base.count(),
        "today":    base.filter(CustomerEntry.created_at.between(ts, te)).count(),
        "pending":  base.filter(CustomerEntry.work_status == "Pending").count(),
        "inprog":   base.filter(CustomerEntry.work_status == "In Progress").count(),
        "done":     base.filter(CustomerEntry.work_status == "Completed").count(),
        "revenue":  db.session.query(func.coalesce(func.sum(CustomerEntry.total_amount), 0))
                      .filter(CustomerEntry.shop_id.in_(shops)).scalar(),
        "paid":     db.session.query(func.coalesce(func.sum(CustomerEntry.amount_paid), 0))
                      .filter(CustomerEntry.shop_id.in_(shops)).scalar(),
        "due":      db.session.query(func.coalesce(func.sum(CustomerEntry.pending_amount), 0))
                      .filter(CustomerEntry.shop_id.in_(shops)).scalar(),
    }

    now   = datetime.datetime.utcnow()
    five  = now + datetime.timedelta(days=5)
    overdue  = base.filter(CustomerEntry.work_status.in_(["Pending", "In Progress"]),
                           CustomerEntry.expected_time < now)\
                   .order_by(CustomerEntry.expected_time).limit(10).all()
    upcoming = base.filter(CustomerEntry.work_status.in_(["Pending", "In Progress"]),
                           CustomerEntry.expected_time.between(now, five))\
                   .order_by(CustomerEntry.expected_time).limit(10).all()

    # Per-shop breakdown for admin
    shop_breakdown = []
    if shop_id == "admin":
        for sid in [k for k in SHOPS if k != "admin"]:
            sq = CustomerEntry.query.filter_by(shop_id=sid)
            shop_breakdown.append({
                "name":    SHOPS[sid],
                "total":   sq.count(),
                "pending": sq.filter(CustomerEntry.work_status == "Pending").count(),
                "revenue": db.session.query(func.coalesce(func.sum(CustomerEntry.total_amount), 0))
                             .filter(CustomerEntry.shop_id == sid).scalar(),
                "due":     db.session.query(func.coalesce(func.sum(CustomerEntry.pending_amount), 0))
                             .filter(CustomerEntry.shop_id == sid).scalar(),
            })

    return render_template("dashboard.html",
                           stats=stats, overdue=overdue, upcoming=upcoming,
                           shop_breakdown=shop_breakdown,
                           shops=SHOPS, session=session)


@app.route("/entries")
@login_required
def entries():
    shop_id = session["shop_id"]
    shops   = [k for k in SHOPS if k != "admin"] if shop_id == "admin" else [shop_id]

    # Filters
    search   = request.args.get("q", "").strip()
    pay_f    = request.args.get("pay", "")
    work_f   = request.args.get("work", "")
    shop_f   = request.args.get("shop", "")
    date_f   = request.args.get("date", "")
    date_to  = request.args.get("date_to", "")
    page     = int(request.args.get("page", 1))
    per_page = 50

    q = CustomerEntry.query.filter(CustomerEntry.shop_id.in_(shops))
    if shop_id == "admin" and shop_f:
        q = q.filter(CustomerEntry.shop_id == shop_f)
    if search:
        pat = f"%{search}%"
        q = q.filter(or_(
            CustomerEntry.customer_name.ilike(pat),
            CustomerEntry.mobile_number.ilike(pat),
            CustomerEntry.reference.ilike(pat),
            CustomerEntry.service_name.ilike(pat),
            CustomerEntry.handled_by.ilike(pat),
        ))
    if pay_f:
        q = q.filter(CustomerEntry.payment_status == pay_f)
    if work_f:
        q = q.filter(CustomerEntry.work_status == work_f)
    if date_f:
        try:
            df = datetime.datetime.strptime(date_f, "%Y-%m-%d")
            q  = q.filter(CustomerEntry.created_at >= df)
        except Exception:
            pass
    if date_to:
        try:
            dt2 = datetime.datetime.strptime(date_to, "%Y-%m-%d") + datetime.timedelta(days=1)
            q   = q.filter(CustomerEntry.created_at < dt2)
        except Exception:
            pass

    total_count = q.count()
    items       = q.order_by(CustomerEntry.created_at.desc())\
                   .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total_count + per_page - 1) // per_page

    return render_template("entries.html",
                           entries=items, total=total_count,
                           page=page, total_pages=total_pages,
                           shops=SHOPS, session=session,
                           args=request.args)


@app.route("/reports")
@login_required
def reports():
    shop_id = session["shop_id"]
    shops   = [k for k in SHOPS if k != "admin"] if shop_id == "admin" else [shop_id]

    period  = request.args.get("period", "month")
    shop_f  = request.args.get("shop", "")
    today   = datetime.date.today()

    if period == "today":
        d_from = datetime.datetime.combine(today, datetime.time.min)
        d_to   = datetime.datetime.combine(today, datetime.time.max)
    elif period == "week":
        d_from = datetime.datetime.combine(today - datetime.timedelta(days=today.weekday()),
                                           datetime.time.min)
        d_to   = datetime.datetime.combine(today, datetime.time.max)
    elif period == "month":
        d_from = datetime.datetime.combine(today.replace(day=1), datetime.time.min)
        d_to   = datetime.datetime.combine(today, datetime.time.max)
    else:
        try:
            d_from = datetime.datetime.strptime(request.args.get("from", ""), "%Y-%m-%d")
            d_to   = datetime.datetime.strptime(request.args.get("to", ""), "%Y-%m-%d") \
                     + datetime.timedelta(days=1)
        except Exception:
            d_from = datetime.datetime.combine(today.replace(day=1), datetime.time.min)
            d_to   = datetime.datetime.combine(today, datetime.time.max)

    q_shops = shops if not (shop_id == "admin" and shop_f) else [shop_f]
    q = CustomerEntry.query.filter(
        CustomerEntry.shop_id.in_(q_shops),
        CustomerEntry.created_at.between(d_from, d_to)
    )

    entries = q.order_by(CustomerEntry.created_at.desc()).all()
    total_revenue = sum(e.total_amount   for e in entries)
    total_paid    = sum(e.amount_paid    for e in entries)
    total_pending = sum(e.pending_amount for e in entries)
    completed     = sum(1 for e in entries if e.work_status == "Completed")

    # Service breakdown
    svc_map = {}
    for e in entries:
        svc = e.service_name or "Other"
        if svc not in svc_map:
            svc_map[svc] = {"count": 0, "revenue": 0}
        svc_map[svc]["count"]   += 1
        svc_map[svc]["revenue"] += e.total_amount
    svc_list = sorted(svc_map.items(), key=lambda x: x[1]["count"], reverse=True)[:15]

    # Shop breakdown for admin
    shop_data = []
    if shop_id == "admin":
        for sid in [k for k in SHOPS if k != "admin"]:
            sq = [e for e in entries if e.shop_id == sid]
            shop_data.append({
                "name":    SHOPS[sid],
                "count":   len(sq),
                "revenue": sum(e.total_amount for e in sq),
                "paid":    sum(e.amount_paid  for e in sq),
                "due":     sum(e.pending_amount for e in sq),
            })

    return render_template("reports.html",
                           entries=entries, period=period,
                           total_revenue=total_revenue, total_paid=total_paid,
                           total_pending=total_pending, completed=completed,
                           svc_list=svc_list, shop_data=shop_data,
                           shops=SHOPS, session=session, args=request.args,
                           d_from=d_from, d_to=d_to)


@app.route("/reminders")
@login_required
def reminders():
    shop_id = session["shop_id"]
    shops   = [k for k in SHOPS if k != "admin"] if shop_id == "admin" else [shop_id]
    now     = datetime.datetime.utcnow()
    days    = int(request.args.get("days", 5))
    soon    = now + datetime.timedelta(days=days)
    base    = CustomerEntry.query.filter(CustomerEntry.shop_id.in_(shops))

    overdue  = base.filter(CustomerEntry.work_status.in_(["Pending","In Progress"]),
                           CustomerEntry.expected_time < now)\
                   .order_by(CustomerEntry.expected_time).all()
    upcoming = base.filter(CustomerEntry.work_status.in_(["Pending","In Progress"]),
                           CustomerEntry.expected_time.between(now, soon))\
                   .order_by(CustomerEntry.expected_time).all()
    unpaid   = base.filter(CustomerEntry.payment_status.in_(["Not Paid","Partial"]),
                           CustomerEntry.pending_amount > 0)\
                   .order_by(CustomerEntry.pending_amount.desc()).all()

    return render_template("reminders.html",
                           overdue=overdue, upcoming=upcoming, unpaid=unpaid,
                           days=days, shops=SHOPS, session=session)


@app.route("/activity")
@login_required
@admin_required
def activity():
    search   = request.args.get("q", "").strip()
    action_f = request.args.get("action", "")
    shop_f   = request.args.get("shop", "")
    page     = int(request.args.get("page", 1))
    per_page = 100

    q = ActivityLog.query
    if search:
        pat = f"%{search}%"
        q   = q.filter(or_(ActivityLog.username.ilike(pat),
                           ActivityLog.detail.ilike(pat)))
    if action_f:
        q = q.filter(ActivityLog.action == action_f)
    if shop_f:
        q = q.filter(ActivityLog.shop_id == shop_f)

    total = q.count()
    logs  = q.order_by(ActivityLog.created_at.desc())\
             .offset((page-1)*per_page).limit(per_page).all()
    pages = (total + per_page - 1) // per_page

    return render_template("activity.html",
                           logs=logs, total=total, page=page, pages=pages,
                           shops=SHOPS, session=session, args=request.args)


# ── JSON API for live stats (used by dashboard auto-refresh) ──
@app.route("/api/stats")
@login_required
def api_stats():
    shop_id = session["shop_id"]
    shops   = [k for k in SHOPS if k != "admin"] if shop_id == "admin" else [shop_id]
    base    = CustomerEntry.query.filter(CustomerEntry.shop_id.in_(shops))
    today   = datetime.date.today()
    ts = datetime.datetime.combine(today, datetime.time.min)
    te = datetime.datetime.combine(today, datetime.time.max)
    return jsonify({
        "total":   base.count(),
        "today":   base.filter(CustomerEntry.created_at.between(ts, te)).count(),
        "pending": base.filter(CustomerEntry.work_status == "Pending").count(),
        "due":     float(db.session.query(func.coalesce(func.sum(CustomerEntry.pending_amount), 0))
                           .filter(CustomerEntry.shop_id.in_(shops)).scalar()),
    })


# ── Initialise DB on startup (works with gunicorn / Railway) ──
with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)