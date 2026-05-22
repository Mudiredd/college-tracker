from flask import (
    Flask, render_template, request, jsonify,
    Response, redirect, url_for, flash, send_file
)

from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
from datetime import datetime
from io import BytesIO
import requests
import json

# ===================== MODELS =====================
from models import db, User, Subscription, Payment, SearchHistory

# ===================== EXTENSIONS =====================
from extensions import bcrypt, mail, init_serializer

# ===================== BLUEPRINTS =====================
from auth import auth_bp
from admin import admin_bp

# ===================== SCRAPER =====================
from scraper import (
    login_step1,
    login_step2,
    click_marks_memo,
    get_marks_pdf,
    parse_pdf,
    EXAM_NAMES,
    get_exam_ids_for_student
)

# ===================== APP =====================
app = Flask(__name__)
CORS(app)

# ===================== CONFIG =====================
app.config['SECRET_KEY'] = 'srbgnr_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'vishnu12shiva@gmail.com'
app.config['MAIL_PASSWORD'] = 'YOUR_APP_PASSWORD'

app.config['ADMIN_EMAIL'] = 'vishnu12shiva@gmail.com'
app.config['ADMIN_PASSWORD'] = 'sravan123'

UPI_ID = 'mudireddyreddy68@nyes'

# ===================== INIT =====================
db.init_app(app)
bcrypt.init_app(app)
mail.init_app(app)

with app.app_context():
    init_serializer(app.config['SECRET_KEY'])

# ===================== LOGIN =====================
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ===================== BLUEPRINTS =====================
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)

# ===================== HELPERS =====================
def get_active_subscription(user):
    sub = Subscription.query.filter_by(
        user_id=user.id,
        is_active=True
    ).order_by(Subscription.id.desc()).first()

    if not sub:
        return None

    if (
        sub.plan == 'monthly'
        and sub.end_date
        and sub.end_date < datetime.now()
    ):
        sub.is_active = False
        db.session.commit()
        return None

    return sub


def get_searches_today(user):
    today = datetime.now().date()
    return SearchHistory.query.filter(
        SearchHistory.user_id == user.id,
        db.func.date(SearchHistory.searched_at) == today
    ).count()

# ===================== HOME =====================
@app.route('/')
@login_required
def index():
    if current_user.is_admin:
        return redirect(url_for('admin.admin_panel'))

    sub = get_active_subscription(current_user)
    searches_today = get_searches_today(current_user)

    return render_template(
        'index.html',
        user=current_user,
        sub=sub,
        searches_today=searches_today,
        searches_left=max(0, 5 - searches_today)
    )

# ===================== SEARCH LIMIT =====================
@app.route('/searches-remaining')
@login_required
def searches_remaining():
    count = get_searches_today(current_user)
    return jsonify({
        'searches_today': count,
        'searches_left': max(0, 5 - count)
    })

# ===================== SUBSCRIBE =====================
@app.route('/subscribe')
@login_required
def subscribe():
    sub = get_active_subscription(current_user)
    if sub:
        return redirect(url_for('index'))

    return render_template('subscribe.html', upi_id=UPI_ID)

# ===================== PAYMENT =====================
@app.route('/submit-payment', methods=['POST'])
@login_required
def submit_payment():
    utr = request.form.get('utr').strip()
    plan = request.form.get('plan')

    amount = 50.0 if plan == 'monthly' else 129.0

    payment = Payment(
        user_id=current_user.id,
        utr=utr,
        amount=amount,
        plan=plan
    )

    db.session.add(payment)
    db.session.commit()

    flash("Payment submitted!", "success")
    return redirect(url_for('account'))

# ===================== ACCOUNT =====================
@app.route('/account')
@login_required
def account():
    sub = get_active_subscription(current_user)

    searches = SearchHistory.query.filter_by(
        user_id=current_user.id
    ).order_by(SearchHistory.searched_at.desc()).limit(20).all()

    payments = Payment.query.filter_by(
        user_id=current_user.id
    ).order_by(Payment.submitted_at.desc()).all()

    return render_template(
        'account.html',
        sub=sub,
        searches=searches,
        payments=payments
    )

# =========================================================
# 🔥 OLD SMART SCRAPING LOGIC RESTORED (IMPORTANT PART)
# =========================================================
@app.route('/get_results', methods=['POST'])
@login_required
def get_results():

    # ---- subscription check ----
    sub = get_active_subscription(current_user)
    if not sub:
        return jsonify({'type': 'error', 'message': 'No active subscription!'}), 403

    # ---- daily limit ----
    if get_searches_today(current_user) >= 5:
        return jsonify({'type': 'error', 'message': 'Daily limit reached!'}), 429

    data = request.json
    regd_no = data.get("regd_no")
    password = data.get("password", "0")

    # save history
    history = SearchHistory(user_id=current_user.id, regd_no=regd_no)
    db.session.add(history)
    db.session.commit()

    def generate():

        session = requests.Session()

        try:
            yield f"data: {json.dumps({'type':'step','message':'🔐 Logging in...'})}\n\n"
            login_step1(session, regd_no, password)

            yield f"data: {json.dumps({'type':'step','message':'🔑 Second auth...'})}\n\n"
            dashboard = login_step2(session, regd_no, password)

            yield f"data: {json.dumps({'type':'step','message':'📋 Opening marks memo...'})}\n\n"
            marks_page = click_marks_memo(session, dashboard)

            exam_ids = get_exam_ids_for_student(regd_no)

            yield f"data: {json.dumps({'type':'step','message':f'📅 Found {len(exam_ids)} exam sessions'})}\n\n"

            # ================= OLD LOGIC =================
            all_data = {sem: {"regular": None, "supplies": []} for sem in range(1, 7)}

            # ---- PHASE 1: find semester 1 ----
            sem1_found_idx = -1

            for idx, exam_id in enumerate(exam_ids):

                exam_name = EXAM_NAMES.get(exam_id, str(exam_id))

                res = get_marks_pdf(session, marks_page, str(exam_id), "1")

                if "pdf" not in res.headers.get("Content-Type", ""):
                    continue

                parsed = parse_pdf(res.content, exam_name, 1)

                if parsed:
                    all_data[1]["regular"] = {"exam": exam_name, "subjects": parsed}
                    sem1_found_idx = idx

                    yield f"data: {json.dumps({'type':'step','message':'✅ Semester 1 found'})}\n\n"
                    break

            if sem1_found_idx == -1:
                yield f"data: {json.dumps({'type':'error','message':'Semester 1 not found'})}\n\n"
                return

            # ---- PHASE 2: smart scanning ----
            remaining = exam_ids[sem1_found_idx:]
            highest_found = 1

            total = len(remaining) * 6
            done = 0

            for exam_id in remaining:

                exam_name = EXAM_NAMES.get(exam_id, str(exam_id))
                sems_to_check = range(1, min(highest_found + 2, 7))

                for sem in sems_to_check:

                    done += 1
                    progress = int((done / total) * 100)

                    yield f"data: {json.dumps({'type':'progress','progress':progress})}\n\n"

                    res = get_marks_pdf(session, marks_page, str(exam_id), str(sem))

                    if "pdf" not in res.headers.get("Content-Type", ""):
                        continue

                    parsed = parse_pdf(res.content, exam_name, sem)

                    if not parsed:
                        continue

                    is_supply = len(parsed) < 5

                    if not is_supply and all_data[sem]["regular"] is None:
                        all_data[sem]["regular"] = {
                            "exam": exam_name,
                            "subjects": parsed
                        }

                        highest_found = max(highest_found, sem)

                    elif is_supply:
                        all_data[sem]["supplies"].append({
                            "exam": exam_name,
                            "subjects": parsed
                        })

            result = {str(k): v for k, v in all_data.items()}

            yield f"data: {json.dumps({'type':'done','data':result})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# ===================== CREATE ADMIN =====================
def create_admin():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(email=app.config['ADMIN_EMAIL']).first():
            admin = User(
                name="Admin",
                email=app.config['ADMIN_EMAIL'],
                password=bcrypt.generate_password_hash(
                    app.config['ADMIN_PASSWORD']
                ).decode('utf-8'),
                regd_no="0000000",
                is_admin=True
            )

            db.session.add(admin)
            db.session.commit()
            print("Admin created!")

# ===================== RUN =====================
if __name__ == "__main__":
    create_admin()
    app.run(debug=True, threaded=True)