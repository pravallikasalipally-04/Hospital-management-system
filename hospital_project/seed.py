from werkzeug.security import generate_password_hash
from app import app, db, User, Patient, Doctor, Appointment
from datetime import datetime, timedelta

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin123'), role='admin'))

    if Doctor.query.count() == 0:
        doctors = [
            Doctor(name='Dr. Rajesh Kumar', specialization='Neurology'),
            Doctor(name='Dr. Priya Sharma', specialization='Cardiology'),
            Doctor(name='Dr. Anil Rao', specialization='General Medicine')
        ]
        db.session.add_all(doctors)
        db.session.flush()
    else:
        doctors = Doctor.query.order_by(Doctor.id).all()

    if Patient.query.count() == 0:
        patients = [
            Patient(name='Ananya Reddy', age=28, gender='Female', contact='9876500001'),
            Patient(name='Rahul Varma', age=35, gender='Male', contact='9876500002'),
            Patient(name='Sneha Rao', age=42, gender='Female', contact='9876500003'),
            Patient(name='Kiran Kumar', age=51, gender='Male', contact='9876500004'),
            Patient(name='Meena Devi', age=31, gender='Female', contact='9876500005')
        ]
        db.session.add_all(patients)
        db.session.flush()
    else:
        patients = Patient.query.order_by(Patient.id).all()

    if Appointment.query.count() == 0:
        rows = [
            (0, 0, 'Migraine', 'Recovered', 12),
            (1, 1, 'Hypertension', 'Under Treatment', 7),
            (2, 2, 'Fever', 'Recovered', 10),
            (3, 1, 'Chest Pain', 'Critical', 3),
            (4, 2, 'Diabetes', 'Under Treatment', 5),
            (0, 2, 'Viral Fever', 'Recovered', 20),
            (1, 0, 'Headache', 'Recovered', 25),
            (2, 1, 'Hypertension', 'Under Treatment', 15),
        ]
        now = datetime.now()
        for p, d, diagnosis, status, days in rows:
            db.session.add(Appointment(
                patient_id=patients[p].id,
                doctor_id=doctors[d].id,
                date=now - timedelta(days=days),
                diagnosis=diagnosis,
                status=status
            ))

    # Link a doctor user to the first doctor for RBAC testing.
    if not User.query.filter_by(username='doctor1').first() and doctors:
        db.session.add(User(username='doctor1', password_hash=generate_password_hash('doctor123'), role='doctor', doctor_id=doctors[0].id))

    db.session.commit()
    print('Seed complete.')
    print('Admin login  : admin / admin123')
    print('Doctor login : doctor1 / doctor123')
