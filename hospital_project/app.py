import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
from sqlalchemy import or_, func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'hospital.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, os.getenv('UPLOAD_FOLDER', 'uploads'))
app.config['EXPORT_FOLDER'] = os.path.join(BASE_DIR, os.getenv('EXPORT_FOLDER', 'exports'))

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

db = SQLAlchemy(app)
jwt = JWTManager(app)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    doctor = db.relationship('Doctor', backref='user_accounts', foreign_keys=[doctor_id])


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    contact = db.Column(db.String(30), unique=True, nullable=False)
    appointments = db.relationship('Appointment', backref='patient', cascade='all, delete-orphan')


class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialization = db.Column(db.String(120), nullable=False)
    appointments = db.relationship('Appointment', backref='doctor', cascade='all, delete-orphan')


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    diagnosis = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='Under Treatment')

    __table_args__ = (
        db.CheckConstraint("status IN ('Recovered','Under Treatment','Critical')", name='ck_status'),
        db.CheckConstraint("age >= 0", name='dummy_not_used') if False else db.UniqueConstraint('id', name='uq_appointment_id'),
    )


ALLOWED_STATUSES = {'Recovered', 'Under Treatment', 'Critical'}


def current_user():
    user_id = session.get('user_id')
    return db.session.get(User, user_id) if user_id else None


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def api_role_required(roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') not in roles:
                return jsonify(error='Forbidden: insufficient role'), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def validate_patient(data, partial=False):
    errors = {}
    if not partial or 'name' in data:
        if not str(data.get('name', '')).strip(): errors['name'] = 'Name is required.'
    if not partial or 'age' in data:
        try:
            age = int(data.get('age'))
            if not 0 <= age <= 120: errors['age'] = 'Age must be between 0 and 120.'
        except (TypeError, ValueError): errors['age'] = 'Age must be a number.'
    if not partial or 'gender' in data:
        if not str(data.get('gender', '')).strip(): errors['gender'] = 'Gender is required.'
    if not partial or 'contact' in data:
        if not str(data.get('contact', '')).strip(): errors['contact'] = 'Contact is required.'
    return errors


def patient_payload(p):
    return {'id': p.id, 'name': p.name, 'age': p.age, 'gender': p.gender, 'contact': p.contact}


def doctor_payload(d):
    return {'id': d.id, 'name': d.name, 'specialization': d.specialization}


def appointment_payload(a):
    return {'id': a.id, 'patient_id': a.patient_id, 'doctor_id': a.doctor_id,
            'date': a.date.isoformat(), 'diagnosis': a.diagnosis, 'status': a.status,
            'patient_name': a.patient.name if a.patient else None,
            'doctor_name': a.doctor.name if a.doctor else None}


def appointment_allowed(a):
    user = current_user()
    return user and (user.role == 'admin' or (user.role == 'doctor' and user.doctor_id == a.doctor_id))


@app.context_processor
def inject_user():
    return {'logged_user': current_user()}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if not current_user(): return redirect(url_for('login'))
    return render_template('dashboard.html', patient_count=Patient.query.count(), doctor_count=Doctor.query.count(), appointment_count=Appointment.query.count())


# -------------------- WEB: PATIENTS --------------------
@app.route('/patients', methods=['GET'])
def patients():
    return render_template('patients/list.html', patients=Patient.query.order_by(Patient.id.desc()).all())

@app.route('/patients/new', methods=['GET'])
@admin_required
def new_patient():
    return render_template('patients/form.html', patient=None, action=url_for('create_patient'))

@app.route('/patients', methods=['POST'])
@admin_required
def create_patient():
    data = request.form
    errors = validate_patient(data)
    if errors:
        for e in errors.values(): flash(e, 'danger')
        return render_template('patients/form.html', patient=None, action=url_for('create_patient'), form=data)
    try:
        p = Patient(name=data['name'].strip(), age=int(data['age']), gender=data['gender'], contact=data['contact'].strip())
        db.session.add(p); db.session.commit(); flash('Patient created.', 'success')
    except Exception:
        db.session.rollback(); flash('Could not create patient. Contact must be unique.', 'danger')
    return redirect(url_for('patients'))

@app.route('/patients/<int:patient_id>')
def patient_detail(patient_id):
    p = db.get_or_404(Patient, patient_id)
    return render_template('patients/detail.html', patient=p)

@app.route('/patients/<int:patient_id>/edit')
@admin_required
def edit_patient(patient_id):
    return render_template('patients/form.html', patient=db.get_or_404(Patient, patient_id), action=url_for('update_patient', patient_id=patient_id))

@app.route('/patients/<int:patient_id>', methods=['PUT', 'PATCH', 'POST'])
@admin_required
def update_patient(patient_id):
    p = db.get_or_404(Patient, patient_id)
    data = request.get_json(silent=True) if request.is_json else request.form
    partial = request.method == 'PATCH'
    errors = validate_patient(data, partial=partial)
    if errors: return jsonify(errors=errors), 400 if request.is_json else redirect(url_for('edit_patient', patient_id=patient_id))
    for field in ['name', 'gender', 'contact']:
        if field in data: setattr(p, field, str(data[field]).strip())
    if 'age' in data: p.age = int(data['age'])
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if request.is_json: return jsonify(error='Contact must be unique.'), 409
        flash('Contact must be unique.', 'danger'); return redirect(url_for('edit_patient', patient_id=patient_id))
    if request.is_json: return jsonify(message='Patient updated', data=patient_payload(p))
    flash('Patient updated.', 'success'); return redirect(url_for('patient_detail', patient_id=p.id))

@app.route('/patients/<int:patient_id>', methods=['DELETE', 'POST'])
@admin_required
def delete_patient(patient_id):
    if request.method == 'POST' and request.form.get('_method', '').upper() != 'DELETE':
        return 'Method Not Allowed', 405
    p = db.get_or_404(Patient, patient_id); db.session.delete(p); db.session.commit()
    if request.is_json: return jsonify(message='Patient deleted')
    flash('Patient deleted.', 'success'); return redirect(url_for('patients'))


# -------------------- WEB: DOCTORS --------------------
@app.route('/doctors')
def doctors():
    return render_template('doctors/list.html', doctors=Doctor.query.order_by(Doctor.id.desc()).all())

@app.route('/doctors/new')
@admin_required
def new_doctor():
    return render_template('doctors/form.html', doctor=None, action=url_for('create_doctor'))

@app.route('/doctors', methods=['POST'])
@admin_required
def create_doctor():
    name = request.form.get('name', '').strip(); specialization = request.form.get('specialization', '').strip()
    if not name or not specialization:
        flash('Name and specialization are required.', 'danger'); return redirect(url_for('new_doctor'))
    db.session.add(Doctor(name=name, specialization=specialization)); db.session.commit(); flash('Doctor created.', 'success')
    return redirect(url_for('doctors'))

@app.route('/doctors/<int:doctor_id>')
def doctor_detail(doctor_id):
    return render_template('doctors/detail.html', doctor=db.get_or_404(Doctor, doctor_id))

@app.route('/doctors/<int:doctor_id>/edit')
@admin_required
def edit_doctor(doctor_id):
    return render_template('doctors/form.html', doctor=db.get_or_404(Doctor, doctor_id), action=url_for('update_doctor', doctor_id=doctor_id))

@app.route('/doctors/<int:doctor_id>', methods=['PUT', 'POST'])
@admin_required
def update_doctor(doctor_id):
    d = db.get_or_404(Doctor, doctor_id); data = request.get_json(silent=True) if request.is_json else request.form
    d.name = str(data.get('name', d.name)).strip(); d.specialization = str(data.get('specialization', d.specialization)).strip()
    db.session.commit()
    if request.is_json: return jsonify(message='Doctor updated', data=doctor_payload(d))
    flash('Doctor updated.', 'success'); return redirect(url_for('doctor_detail', doctor_id=d.id))

@app.route('/doctors/<int:doctor_id>', methods=['DELETE', 'POST'])
@admin_required
def delete_doctor(doctor_id):
    if request.method == 'POST' and request.form.get('_method', '').upper() != 'DELETE':
        return 'Method Not Allowed', 405
    d = db.get_or_404(Doctor, doctor_id); db.session.delete(d); db.session.commit()
    if request.is_json: return jsonify(message='Doctor deleted')
    flash('Doctor deleted.', 'success'); return redirect(url_for('doctors'))


# -------------------- WEB: APPOINTMENTS --------------------
@app.route('/appointments')
def appointments():
    user = current_user()
    if not user: return redirect(url_for('login'))
    q = Appointment.query.order_by(Appointment.date.desc())
    if user.role == 'doctor': q = q.filter_by(doctor_id=user.doctor_id)
    return render_template('appointments/list.html', appointments=q.all())

@app.route('/appointments/new')
@admin_required
def new_appointment():
    return render_template('appointments/form.html', appointment=None, patients=Patient.query.all(), doctors=Doctor.query.all(), action=url_for('create_appointment'))

@app.route('/appointments', methods=['POST'])
@admin_required
def create_appointment():
    try:
        date_value = datetime.fromisoformat(request.form['date'])
        status = request.form.get('status', 'Under Treatment')
        if status not in ALLOWED_STATUSES: raise ValueError('Invalid status')
        a = Appointment(patient_id=int(request.form['patient_id']), doctor_id=int(request.form['doctor_id']), date=date_value, diagnosis=request.form['diagnosis'].strip(), status=status)
        db.session.add(a); db.session.commit(); flash('Appointment scheduled.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Could not create appointment: {e}', 'danger')
    return redirect(url_for('appointments'))

@app.route('/appointments/<int:appointment_id>')
def appointment_detail(appointment_id):
    a = db.get_or_404(Appointment, appointment_id)
    if current_user() and current_user().role == 'doctor' and not appointment_allowed(a): return 'Forbidden', 403
    return render_template('appointments/detail.html', appointment=a)

@app.route('/appointments/<int:appointment_id>/edit')
def edit_appointment(appointment_id):
    a = db.get_or_404(Appointment, appointment_id)
    if not appointment_allowed(a): return 'Forbidden', 403
    return render_template('appointments/form.html', appointment=a, patients=Patient.query.all(), doctors=Doctor.query.all(), action=url_for('update_appointment', appointment_id=a.id))

@app.route('/appointments/<int:appointment_id>', methods=['PUT', 'PATCH', 'POST'])
def update_appointment(appointment_id):
    a = db.get_or_404(Appointment, appointment_id)
    if not appointment_allowed(a): return jsonify(error='Forbidden'), 403 if request.is_json else ('Forbidden', 403)
    data = request.get_json(silent=True) if request.is_json else request.form
    try:
        if 'patient_id' in data: a.patient_id = int(data['patient_id'])
        if 'doctor_id' in data:
            if current_user().role != 'admin': return jsonify(error='Doctors cannot reassign appointments'), 403
            a.doctor_id = int(data['doctor_id'])
        if 'date' in data: a.date = datetime.fromisoformat(data['date'])
        if 'diagnosis' in data: a.diagnosis = str(data['diagnosis']).strip()
        if 'status' in data:
            if data['status'] not in ALLOWED_STATUSES: raise ValueError('Invalid status')
            a.status = data['status']
        db.session.commit()
    except Exception as e:
        db.session.rollback(); return jsonify(error=str(e)), 400
    if request.is_json: return jsonify(message='Appointment updated', data=appointment_payload(a))
    flash('Appointment updated.', 'success'); return redirect(url_for('appointment_detail', appointment_id=a.id))

@app.route('/appointments/<int:appointment_id>', methods=['DELETE', 'POST'])
@admin_required
def delete_appointment(appointment_id):
    if request.method == 'POST' and request.form.get('_method', '').upper() != 'DELETE':
        return 'Method Not Allowed', 405
    a = db.get_or_404(Appointment, appointment_id); db.session.delete(a); db.session.commit()
    if request.is_json: return jsonify(message='Appointment cancelled')
    flash('Appointment cancelled.', 'success'); return redirect(url_for('appointments'))


# -------------------- ANALYTICS --------------------
def analytics_dataframe():
    rows = Appointment.query.all()
    data = [{
        'id': a.id, 'patient_id': a.patient_id, 'patient': a.patient.name if a.patient else '',
        'doctor_id': a.doctor_id, 'doctor': a.doctor.name if a.doctor else '',
        'date': a.date, 'diagnosis': a.diagnosis, 'status': a.status
    } for a in rows]
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=['id','patient_id','patient','doctor_id','doctor','date','diagnosis','status'])
    df['date'] = pd.to_datetime(df['date'])
    return df


def analytics_payload():
    df = analytics_dataframe()
    if df.empty:
        return {'diagnoses': {}, 'statuses': {}, 'doctors': [], 'trends': [], 'summary': {'total': 0, 'recovered': 0, 'recovery_rate': 0}}
    diagnosis_counts = df.groupby('diagnosis').size().sort_values(ascending=False)
    status_counts = df.groupby('status').size()
    doctor_group = df.groupby(['doctor_id', 'doctor']).agg(patients_treated=('patient_id','nunique'), appointments=('id','count')).reset_index()
    recovery = df.assign(recovered=(df['status'] == 'Recovered').astype(int)).groupby(['doctor_id','doctor']).agg(recovered=('recovered','sum'), total=('id','count')).reset_index()
    doctor_group = doctor_group.merge(recovery, on=['doctor_id','doctor'])
    doctor_group['recovery_rate'] = np.round((doctor_group['recovered'] / doctor_group['total']) * 100, 2)
    trend = df.groupby(df['date'].dt.to_period('M')).size().reset_index(name='appointments')
    trend['month'] = trend['date'].astype(str)
    recovered = int((df['status'] == 'Recovered').sum())
    return {
        'diagnoses': diagnosis_counts.to_dict(),
        'statuses': status_counts.to_dict(),
        'doctors': doctor_group.to_dict(orient='records'),
        'trends': trend[['month','appointments']].to_dict(orient='records'),
        'summary': {'total': int(len(df)), 'recovered': recovered, 'recovery_rate': round(recovered / len(df) * 100, 2)}
    }

@app.route('/analytics')
@admin_required
def analytics():
    return render_template('analytics.html', analytics=analytics_payload())

@app.route('/analytics/upload', methods=['POST'])
@admin_required
def upload_csv():
    file = request.files.get('file')
    if not file or not file.filename.lower().endswith('.csv'):
        flash('Please upload a .csv file.', 'danger'); return redirect(url_for('analytics'))
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename); file.save(path)
    try:
        df = pd.read_csv(path)
        required = {'patient_id','doctor_id','date','diagnosis','status'}
        missing = required - set(df.columns)
        if missing: raise ValueError('Missing columns: ' + ', '.join(sorted(missing)))
        imported = 0
        for _, row in df.iterrows():
            if not Patient.query.get(int(row['patient_id'])) or not Doctor.query.get(int(row['doctor_id'])): continue
            if str(row['status']) not in ALLOWED_STATUSES: continue
            db.session.add(Appointment(patient_id=int(row['patient_id']), doctor_id=int(row['doctor_id']), date=pd.to_datetime(row['date']).to_pydatetime(), diagnosis=str(row['diagnosis']), status=str(row['status'])))
            imported += 1
        db.session.commit(); flash(f'CSV uploaded. {imported} appointment(s) imported.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'CSV import failed: {e}', 'danger')
    return redirect(url_for('analytics'))

@app.route('/analytics/export/<fmt>')
@admin_required
def export_analytics(fmt):
    df = analytics_dataframe()
    if fmt == 'csv':
        path = os.path.join(app.config['EXPORT_FOLDER'], 'hospital_analytics.csv'); df.to_csv(path, index=False); return send_from_directory(app.config['EXPORT_FOLDER'], 'hospital_analytics.csv', as_attachment=True)
    if fmt == 'xlsx':
        path = os.path.join(app.config['EXPORT_FOLDER'], 'hospital_analytics.xlsx')
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Appointments')
            pd.DataFrame(list(analytics_payload()['diagnoses'].items()), columns=['Diagnosis','Count']).to_excel(writer, index=False, sheet_name='Diagnoses')
        return send_from_directory(app.config['EXPORT_FOLDER'], 'hospital_analytics.xlsx', as_attachment=True)
    return 'Unsupported format', 400


# -------------------- API AUTH --------------------
@app.post('/api/auth/login')
def api_login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or not check_password_hash(user.password_hash, data.get('password', '')):
        return jsonify(error='Invalid credentials'), 401
    token = create_access_token(identity=str(user.id), additional_claims={'role': user.role, 'doctor_id': user.doctor_id})
    return jsonify(access_token=token, user={'id': user.id, 'username': user.username, 'role': user.role, 'doctor_id': user.doctor_id})


# -------------------- API PATIENTS --------------------
@app.get('/api/patients')
@jwt_required()
def api_patients(): return jsonify(data=[patient_payload(p) for p in Patient.query.order_by(Patient.id).all()])

@app.post('/api/patients')
@api_role_required({'admin'})
def api_create_patient():
    data = request.get_json(silent=True) or {}; errors = validate_patient(data)
    if errors: return jsonify(errors=errors), 400
    p = Patient(name=data['name'].strip(), age=int(data['age']), gender=data['gender'], contact=data['contact'].strip())
    db.session.add(p)
    try: db.session.commit()
    except Exception: db.session.rollback(); return jsonify(error='Contact must be unique'), 409
    return jsonify(message='Patient created', data=patient_payload(p)), 201

@app.get('/api/patients/<int:patient_id>')
@jwt_required()
def api_get_patient(patient_id): return jsonify(data=patient_payload(db.get_or_404(Patient, patient_id)))

@app.put('/api/patients/<int:patient_id>')
@api_role_required({'admin'})
def api_put_patient(patient_id):
    p = db.get_or_404(Patient, patient_id); data = request.get_json(silent=True) or {}; errors = validate_patient(data)
    if errors: return jsonify(errors=errors), 400
    p.name = data['name'].strip(); p.age = int(data['age']); p.gender = data['gender']; p.contact = data['contact'].strip()
    try: db.session.commit()
    except Exception: db.session.rollback(); return jsonify(error='Contact must be unique'), 409
    return jsonify(message='Patient replaced', data=patient_payload(p))

@app.patch('/api/patients/<int:patient_id>')
@api_role_required({'admin'})
def api_patch_patient(patient_id):
    p = db.get_or_404(Patient, patient_id); data = request.get_json(silent=True) or {}; errors = validate_patient(data, partial=True)
    if errors: return jsonify(errors=errors), 400
    for field in ['name','gender','contact']:
        if field in data: setattr(p, field, str(data[field]).strip())
    if 'age' in data: p.age = int(data['age'])
    try: db.session.commit()
    except Exception: db.session.rollback(); return jsonify(error='Contact must be unique'), 409
    return jsonify(message='Patient patched', data=patient_payload(p))

@app.delete('/api/patients/<int:patient_id>')
@api_role_required({'admin'})
def api_delete_patient(patient_id):
    db.session.delete(db.get_or_404(Patient, patient_id)); db.session.commit(); return jsonify(message='Patient deleted')


# -------------------- API DOCTORS --------------------
@app.get('/api/doctors')
@jwt_required()
def api_doctors(): return jsonify(data=[doctor_payload(d) for d in Doctor.query.order_by(Doctor.id).all()])

@app.post('/api/doctors')
@api_role_required({'admin'})
def api_create_doctor():
    data = request.get_json(silent=True) or {}
    if not data.get('name') or not data.get('specialization'): return jsonify(error='name and specialization are required'), 400
    d = Doctor(name=data['name'].strip(), specialization=data['specialization'].strip()); db.session.add(d); db.session.commit()
    return jsonify(message='Doctor created', data=doctor_payload(d)), 201

@app.get('/api/doctors/<int:doctor_id>')
@jwt_required()
def api_get_doctor(doctor_id): return jsonify(data=doctor_payload(db.get_or_404(Doctor, doctor_id)))

@app.put('/api/doctors/<int:doctor_id>')
@api_role_required({'admin'})
def api_put_doctor(doctor_id):
    d = db.get_or_404(Doctor, doctor_id); data = request.get_json(silent=True) or {}
    d.name = str(data.get('name', '')).strip(); d.specialization = str(data.get('specialization', '')).strip()
    if not d.name or not d.specialization: return jsonify(error='name and specialization are required'), 400
    db.session.commit(); return jsonify(message='Doctor updated', data=doctor_payload(d))

@app.patch('/api/doctors/<int:doctor_id>')
@api_role_required({'admin'})
def api_patch_doctor(doctor_id):
    d = db.get_or_404(Doctor, doctor_id); data = request.get_json(silent=True) or {}
    if 'name' in data: d.name = str(data['name']).strip()
    if 'specialization' in data: d.specialization = str(data['specialization']).strip()
    db.session.commit(); return jsonify(message='Doctor patched', data=doctor_payload(d))

@app.delete('/api/doctors/<int:doctor_id>')
@api_role_required({'admin'})
def api_delete_doctor(doctor_id):
    db.session.delete(db.get_or_404(Doctor, doctor_id)); db.session.commit(); return jsonify(message='Doctor deleted')


# -------------------- API APPOINTMENTS --------------------
def api_visible_appointments():
    claims = get_jwt(); query = Appointment.query.order_by(Appointment.date.desc())
    if claims.get('role') == 'doctor': query = query.filter_by(doctor_id=claims.get('doctor_id'))
    doctor_id = request.args.get('doctor_id', type=int)
    if doctor_id is not None:
        query = query.filter_by(doctor_id=doctor_id)
    return query.all()

@app.get('/api/appointments')
@jwt_required()
def api_appointments(): return jsonify(data=[appointment_payload(a) for a in api_visible_appointments()])

@app.post('/api/appointments')
@api_role_required({'admin'})
def api_create_appointment():
    data = request.get_json(silent=True) or {}
    required = ['patient_id','doctor_id','date','diagnosis','status']
    missing = [x for x in required if x not in data]
    if missing: return jsonify(error='Missing fields', fields=missing), 400
    if data['status'] not in ALLOWED_STATUSES: return jsonify(error='Invalid status'), 400
    try:
        a = Appointment(patient_id=int(data['patient_id']), doctor_id=int(data['doctor_id']), date=datetime.fromisoformat(data['date']), diagnosis=str(data['diagnosis']).strip(), status=data['status'])
        db.session.add(a); db.session.commit()
        return jsonify(message='Appointment created', data=appointment_payload(a)), 201
    except Exception as e: db.session.rollback(); return jsonify(error=str(e)), 400

@app.get('/api/appointments/<int:appointment_id>')
@jwt_required()
def api_get_appointment(appointment_id):
    a = db.get_or_404(Appointment, appointment_id); claims = get_jwt()
    if claims.get('role') == 'doctor' and claims.get('doctor_id') != a.doctor_id: return jsonify(error='Forbidden'), 403
    return jsonify(data=appointment_payload(a))

@app.put('/api/appointments/<int:appointment_id>')
@jwt_required()
def api_put_appointment(appointment_id):
    a = db.get_or_404(Appointment, appointment_id); claims = get_jwt()
    if claims.get('role') == 'doctor' and claims.get('doctor_id') != a.doctor_id: return jsonify(error='Forbidden'), 403
    data = request.get_json(silent=True) or {}
    try:
        a.patient_id = int(data['patient_id']); a.doctor_id = int(data['doctor_id']); a.date = datetime.fromisoformat(data['date']); a.diagnosis = str(data['diagnosis']).strip(); a.status = data['status']
        if a.status not in ALLOWED_STATUSES: raise ValueError('Invalid status')
        if claims.get('role') == 'doctor' and a.doctor_id != claims.get('doctor_id'): raise ValueError('Doctors cannot reassign appointments')
        db.session.commit(); return jsonify(message='Appointment updated', data=appointment_payload(a))
    except Exception as e: db.session.rollback(); return jsonify(error=str(e)), 400

@app.patch('/api/appointments/<int:appointment_id>')
@jwt_required()
def api_patch_appointment(appointment_id):
    a = db.get_or_404(Appointment, appointment_id); claims = get_jwt()
    if claims.get('role') == 'doctor' and claims.get('doctor_id') != a.doctor_id: return jsonify(error='Forbidden'), 403
    data = request.get_json(silent=True) or {}
    try:
        for field in ['patient_id','doctor_id']:
            if field in data:
                if field == 'doctor_id' and claims.get('role') == 'doctor': raise ValueError('Doctors cannot reassign appointments')
                setattr(a, field, int(data[field]))
        if 'date' in data: a.date = datetime.fromisoformat(data['date'])
        if 'diagnosis' in data: a.diagnosis = str(data['diagnosis']).strip()
        if 'status' in data:
            if data['status'] not in ALLOWED_STATUSES: raise ValueError('Invalid status')
            a.status = data['status']
        db.session.commit(); return jsonify(message='Appointment patched', data=appointment_payload(a))
    except Exception as e: db.session.rollback(); return jsonify(error=str(e)), 400

@app.delete('/api/appointments/<int:appointment_id>')
@api_role_required({'admin'})
def api_delete_appointment(appointment_id):
    db.session.delete(db.get_or_404(Appointment, appointment_id)); db.session.commit(); return jsonify(message='Appointment cancelled')

@app.get('/api/analytics')
@api_role_required({'admin'})
def api_analytics(): return jsonify(data=analytics_payload())


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'): return jsonify(error='Resource not found'), 404
    return render_template('error.html', code=404, message='Page not found.'), 404

@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    if request.path.startswith('/api/'): return jsonify(error='Internal server error'), 500
    return render_template('error.html', code=500, message='Internal server error.'), 500


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
