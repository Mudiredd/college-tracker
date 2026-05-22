from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
    send_file
)

from flask_cors import CORS

from flask_login import (
    LoginManager,
    login_required,
    current_user
)

from datetime import datetime

from io import BytesIO

import requests
import json

# REPORTLAB
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from reportlab.lib import colors
from reportlab.lib.units import inch

# MODELS
from models import (
    db,
    User,
    Subscription,
    Payment,
    SearchHistory
)

# EXTENSIONS
from extensions import (
    bcrypt,
    mail,
    init_serializer
)

# BLUEPRINTS
from auth import auth_bp
from admin import admin_bp

# SCRAPER
from scraper import (
    login_step1,
    login_step2,
    click_marks_memo,
    get_marks_pdf,
    parse_pdf,
    EXAM_NAMES,
    get_exam_ids_for_student
)

# =========================================================
# APP
# =========================================================

app = Flask(__name__)

CORS(app)

# =========================================================
# CONFIG
# =========================================================

app.config['SECRET_KEY'] = 'srbgnr_secret_key_2026'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college_tracker.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# MAIL

app.config['MAIL_SERVER'] = 'smtp.gmail.com'

app.config['MAIL_PORT'] = 587

app.config['MAIL_USE_TLS'] = True

app.config['MAIL_USERNAME'] = 'vishnu12shiva@gmail.com'

app.config['MAIL_PASSWORD'] = 'fvbu wfyb luer dbrz'  # Use environment variables in production!

# ADMIN

app.config['ADMIN_EMAIL'] = 'vishnu12shiva@gmail.com'

app.config['ADMIN_PASSWORD'] = 'sravan123'

UPI_ID = 'mudireddyreddy68@nyes'

# =========================================================
# EXTENSIONS
# =========================================================

db.init_app(app)

bcrypt.init_app(app)

mail.init_app(app)

with app.app_context():

    init_serializer(
        app.config['SECRET_KEY']
    )

# =========================================================
# LOGIN
# =========================================================

login_manager = LoginManager(app)

login_manager.login_view = 'auth.login'


@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )

# =========================================================
# BLUEPRINTS
# =========================================================

app.register_blueprint(auth_bp)

app.register_blueprint(admin_bp)

# =========================================================
# HELPERS
# =========================================================

def get_active_subscription(user):

    sub = Subscription.query.filter_by(
        user_id=user.id,
        is_active=True
    ).order_by(
        Subscription.id.desc()
    ).first()

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
        db.func.date(
            SearchHistory.searched_at
        ) == today
    ).count()

# =========================================================
# SEARCHES REMAINING
# =========================================================

@app.route('/searches-remaining')
@login_required
def searches_remaining():

    count = get_searches_today(
        current_user
    )

    return jsonify({

        'searches_today': count,

        'searches_left': max(
            0,
            5 - count
        )
    })

# =========================================================
# HOME
# =========================================================

@app.route('/')
@login_required
def index():

    if current_user.is_admin:

        return redirect(
            url_for(
                'admin.admin_panel'
            )
        )

    sub = get_active_subscription(
        current_user
    )

    searches_today = get_searches_today(
        current_user
    )

    return render_template(

        'index.html',

        user=current_user,

        sub=sub,

        searches_today=searches_today,

        searches_left=max(
            0,
            5 - searches_today
        )
    )

# =========================================================
# SUBSCRIBE
# =========================================================

@app.route('/subscribe')
@login_required
def subscribe():

    if current_user.is_admin:

        return redirect(
            url_for(
                'admin.admin_panel'
            )
        )

    sub = get_active_subscription(
        current_user
    )

    # ✅ IF SUBSCRIBED
    # REDIRECT TO HOME

    if sub:

        return redirect(
            url_for('index')
        )

    return render_template(

        'subscribe.html',

        sub=sub,

        upi_id=UPI_ID
    )

# =========================================================
# SUBMIT PAYMENT
# =========================================================

@app.route(
    '/submit-payment',
    methods=['POST']
)

@login_required
def submit_payment():

    utr = request.form.get(
        'utr'
    ).strip()

    plan = request.form.get(
        'plan'
    )

    amount = (
        50.0
        if plan == 'monthly'
        else 129.0
    )

    payment = Payment(

        user_id=current_user.id,

        utr=utr,

        amount=amount,

        plan=plan
    )

    db.session.add(payment)

    db.session.commit()

    flash(
        'Payment submitted successfully!',
        'success'
    )

    return redirect(
        url_for('account')
    )

# =========================================================
# ACCOUNT
# =========================================================

@app.route('/account')
@login_required
def account():

    sub = get_active_subscription(
        current_user
    )

    searches = SearchHistory.query.filter_by(
        user_id=current_user.id
    ).order_by(
        SearchHistory.searched_at.desc()
    ).limit(20).all()

    payments = Payment.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Payment.submitted_at.desc()
    ).all()

    searches_today = get_searches_today(
        current_user
    )

    return render_template(

        'account.html',

        sub=sub,

        searches=searches,

        payments=payments,

        searches_today=searches_today
    )

# =========================================================
# PDF GENERATOR
# =========================================================

@app.route(
    '/generate-pdf',
    methods=['POST']
)

@login_required
def generate_pdf():

    try:

        data_str = request.form.get(
            'data'
        )

        regd_no = request.form.get(
            'regd_no'
        )

        data = json.loads(data_str)

        # PDF BUFFER

        pdf_buffer = BytesIO()

        doc = SimpleDocTemplate(

            pdf_buffer,

            pagesize=letter
        )

        elements = []

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(

            'CustomTitle',

            parent=styles['Heading1'],

            fontSize=20,

            textColor=colors.HexColor(
                '#00d4ff'
            ),

            alignment=1,

            spaceAfter=20
        )

        # TITLE

        elements.append(

            Paragraph(
                "SR & BGNR College Tracker",
                title_style
            )
        )

        elements.append(

            Paragraph(

                f"Academic Report - {regd_no}",

                styles['Normal']
            )
        )

        elements.append(
            Spacer(1, 0.3 * inch)
        )

        # SUMMARY

        total_subjects = 0

        total_credits = 0

        for sem in range(1, 7):

            sem_data = data.get(
                str(sem)
            )

            if (
                sem_data
                and sem_data.get('regular')
            ):

                subjects = sem_data[
                    'regular'
                ]['subjects']

                total_subjects += len(
                    subjects
                )

                total_credits += sum(

                    float(
                        s.get(
                            'credits',
                            0
                        )
                    )

                    for s in subjects
                )

        summary_data = [

            ['Metric', 'Value'],

            [
                'Total Subjects',
                str(total_subjects)
            ],

            [
                'Total Credits',
                str(total_credits)
            ],

            [
                'Registration No',
                regd_no
            ]
        ]

        summary_table = Table(
            summary_data
        )

        summary_table.setStyle(
            TableStyle([

                (
                    'BACKGROUND',
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(
                        '#00d4ff'
                    )
                ),

                (
                    'TEXTCOLOR',
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    'GRID',
                    (0, 0),
                    (-1, -1),
                    1,
                    colors.black
                ),

                (
                    'FONTNAME',
                    (0, 0),
                    (-1, 0),
                    'Helvetica-Bold'
                ),

                (
                    'ALIGN',
                    (0, 0),
                    (-1, -1),
                    'CENTER'
                ),

                (
                    'BACKGROUND',
                    (0, 1),
                    (-1, -1),
                    colors.beige
                )
            ])
        )

        elements.append(
            summary_table
        )

        elements.append(
            Spacer(1, 0.3 * inch)
        )

        # SEMESTERS

        for sem in range(1, 7):

            sem_data = data.get(
                str(sem)
            )

            if (
                not sem_data
                or not sem_data.get(
                    'regular'
                )
            ):
                continue

            elements.append(

                Paragraph(

                    f"Semester {sem}",

                    styles['Heading2']
                )
            )

            elements.append(

                Paragraph(

                    f"Exam: {sem_data['regular']['exam']}",

                    styles['Normal']
                )
            )

            elements.append(
                Spacer(1, 0.1 * inch)
            )

            table_data = [[

                '#',
                'Subject',
                'Grade',
                'Credits'

            ]]

            subjects = sem_data[
                'regular'
            ]['subjects']

            for i, subject in enumerate(
                subjects,
                1
            ):

                table_data.append([

                    str(i),

                    subject['subject'][:35],

                    subject['grade'],

                    str(
                        subject['credits']
                    )
                ])

            table = Table(

                table_data,

                colWidths=[

                    0.5 * inch,

                    3.5 * inch,

                    1 * inch,

                    1 * inch
                ]
            )

            table.setStyle(
                TableStyle([

                    (
                        'BACKGROUND',
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(
                            '#00d4ff'
                        )
                    ),

                    (
                        'TEXTCOLOR',
                        (0, 0),
                        (-1, 0),
                        colors.white
                    ),

                    (
                        'GRID',
                        (0, 0),
                        (-1, -1),
                        1,
                        colors.black
                    ),

                    (
                        'FONTNAME',
                        (0, 0),
                        (-1, 0),
                        'Helvetica-Bold'
                    ),

                    (
                        'ROWBACKGROUNDS',
                        (0, 1),
                        (-1, -1),
                        [
                            colors.white,
                            colors.lightgrey
                        ]
                    )
                ])
            )

            elements.append(table)

            elements.append(
                Spacer(1, 0.25 * inch)
            )

        # BUILD PDF

        doc.build(elements)

        pdf_buffer.seek(0)

        return send_file(

            pdf_buffer,

            mimetype='application/pdf',

            as_attachment=True,

            download_name=
            f'SR-BGNR-{regd_no}.pdf'
        )

    except Exception as e:

        print(
            f"PDF ERROR: {str(e)}"
        )

        return jsonify({

            'error': str(e)

        }), 500

# =========================================================
# GET RESULTS
# =========================================================

@app.route(
    '/get_results',
    methods=['POST']
)

@login_required
def get_results():

    sub = get_active_subscription(
        current_user
    )

    if not sub:

        return jsonify({

            'type': 'error',

            'message':
            'No active subscription!'

        }), 403

    searches_today = get_searches_today(
        current_user
    )

    if searches_today >= 5:

        return jsonify({

            'type': 'error',

            'message':
            '❌ Daily limit reached!'

        }), 429

    data = request.json

    regd_no = data.get(
        "regd_no"
    )

    password = data.get(
        "password",
        "0"
    )

    # SAVE HISTORY

    history = SearchHistory(

        user_id=current_user.id,

        regd_no=regd_no
    )

    db.session.add(history)

    db.session.commit()

    initial_count = searches_today + 1

    # =====================================================
    # GENERATOR
    # =====================================================

    def generate():

        session = requests.Session()

        try:

            yield f"data: {json.dumps({'type':'searches_update','searches_left':max(0,5-initial_count)})}\n\n"

            yield f"data: {json.dumps({'type':'step','message':'🔐 Logging into college portal...'})}\n\n"

            login_step1(
                session,
                regd_no,
                password
            )

            yield f"data: {json.dumps({'type':'step','message':'🔑 Second authentication...'})}\n\n"

            dashboard = login_step2(

                session,
                regd_no,
                password
            )

            yield f"data: {json.dumps({'type':'step','message':'📋 Opening Marks Memo...'})}\n\n"

            marks_page = click_marks_memo(
                session,
                dashboard
            )

            exam_ids = get_exam_ids_for_student(
                regd_no
            )

            yield f"data: {json.dumps({'type':'step','message':f'📅 Found {len(exam_ids)} exam periods'})}\n\n"

            all_data = {

                sem: {

                    "regular": None,

                    "supplies": []

                }

                for sem in range(1, 7)
            }

            total = len(exam_ids) * 6

            done = 0

            for exam_id in exam_ids:

                exam_name = EXAM_NAMES.get(

                    exam_id,

                    str(exam_id)
                )

                for sem in range(1, 7):

                    done += 1

                    progress = int(
                        (done / total) * 100
                    )

                    yield f"data: {json.dumps({'type':'progress','progress':progress,'message':f'🔍 {exam_name} → Semester {sem}'})}\n\n"

                    try:

                        res = get_marks_pdf(

                            session,

                            marks_page,

                            str(exam_id),

                            str(sem)
                        )

                        if "pdf" not in res.headers.get(
                            "Content-Type",
                            ""
                        ).lower():
                            continue

                        parsed = parse_pdf(

                            res.content,

                            exam_name,

                            sem
                        )

                        if not parsed:
                            continue

                        is_supply = len(parsed) < 5

                        if (
                            not is_supply
                            and all_data[sem]['regular'] is None
                        ):

                            all_data[sem]['regular'] = {

                                "exam": exam_name,

                                "subjects": parsed
                            }

                        elif is_supply:

                            all_data[sem]['supplies'].append({

                                "exam": exam_name,

                                "subjects": parsed
                            })

                    except Exception as e:

                        print(
                            f"ERROR: {str(e)}"
                        )

                        continue

            result = {

                str(k): v

                for k, v in all_data.items()
            }

            yield f"data: {json.dumps({'type':'done','data':result})}\n\n"

        except GeneratorExit:

            print(
                f"Cancelled: {regd_no}"
            )

        except Exception as e:

            print(
                f"UNEXPECTED ERROR: {str(e)}"
            )

            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return Response(

        generate(),

        mimetype="text/event-stream"
    )

# =========================================================
# CREATE ADMIN
# =========================================================

def create_admin():

    with app.app_context():

        db.create_all()

        admin_email = app.config[
            'ADMIN_EMAIL'
        ]

        admin_password = app.config[
            'ADMIN_PASSWORD'
        ]

        if not User.query.filter_by(
            email=admin_email
        ).first():

            admin = User(

                name='Admin',

                email=admin_email,

                password=bcrypt
                .generate_password_hash(
                    admin_password
                )
                .decode('utf-8'),

                regd_no='0000000',

                is_admin=True
            )

            db.session.add(admin)

            db.session.commit()

            print("✅ Admin created!")

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    create_admin()

    app.run(

        debug=True,

        threaded=True
    )