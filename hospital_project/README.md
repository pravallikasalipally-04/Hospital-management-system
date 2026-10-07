# Hospital Patient Record and Treatment Tracking System

A complete Flask + MySQL + Pandas + NumPy hospital management project based on the supplied Module 8 project specification.

## 1. Features
- Patients CRUD
- Doctors CRUD
- Appointment scheduling and management
- Primary keys, foreign keys, NOT NULL, UNIQUE and status constraints
- Admin and doctor login
- JWT API authentication and role-based authorization
- Doctors can view/edit only their own appointments
- Pandas + NumPy analytics dashboard
- Common diagnoses
- Recovery rate and doctor performance
- Appointment status distribution
- Monthly appointment trend
- CSV upload for appointments
- CSV and Excel analytics export
- Jinja2 HTML frontend
- REST API for Postman
- Method override hidden field for browser forms

## 2. Requirements
- Python 3.11+ recommended
- MySQL Server 8.x
- MySQL Workbench (recommended)
- Postman (for API testing)

## 3. Windows installation
Open Command Prompt in this project folder:

```bat
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. MySQL setup
Open MySQL Workbench, create/open a SQL tab and run `schema.sql`.

Then create `.env` from `.env.example` and replace the password:

```env
SECRET_KEY=change-this-secret-key
JWT_SECRET_KEY=change-this-jwt-secret-key
DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@localhost:3306/hospital_db
UPLOAD_FOLDER=uploads
EXPORT_FOLDER=exports
```

If your MySQL root account has no password, use:
`mysql+pymysql://root:@localhost:3306/hospital_db`

## 5. Create demo data
After `.env` is ready:

```bat
python seed.py
```

Demo users:
- Admin: `admin` / `admin123`
- Doctor: `doctor1` / `doctor123`

## 6. Run

```bat
python app.py
```

Open:
`http://127.0.0.1:5000`

## 7. Web flow
1. Login as admin.
2. Open Patients and add/edit/delete records.
3. Open Doctors and manage doctors.
4. Open Appointments and schedule an appointment.
5. Open Analytics to see charts and doctor performance.
6. Upload `sample_appointments.csv` from the project folder if you want to test CSV import.
7. Export CSV or Excel from Analytics.
8. Logout and login as `doctor1` to verify doctor-only appointment access.

## 8. API flow in Postman
### Login
POST `http://127.0.0.1:5000/api/auth/login`
Body -> raw -> JSON:
```json
{
  "username": "admin",
  "password": "admin123"
}
```
Copy `access_token`.

For protected requests use Authorization -> Bearer Token -> paste the token.

### Get patients
GET `http://127.0.0.1:5000/api/patients`

### Create patient
POST `http://127.0.0.1:5000/api/patients`
```json
{
  "name": "Test Patient",
  "age": 25,
  "gender": "Female",
  "contact": "9999999999"
}
```

### Get doctors
GET `http://127.0.0.1:5000/api/doctors`

### Create appointment
POST `http://127.0.0.1:5000/api/appointments`
```json
{
  "patient_id": 1,
  "doctor_id": 1,
  "date": "2026-10-10T10:30:00",
  "diagnosis": "Migraine",
  "status": "Under Treatment"
}
```

### Filter appointments by doctor
GET `http://127.0.0.1:5000/api/appointments?doctor_id=1`

### Full and partial update
PUT/PATCH `http://127.0.0.1:5000/api/patients/1`

PATCH example:
```json
{
  "contact": "8888888888"
}
```

### Delete
DELETE `http://127.0.0.1:5000/api/patients/1`

## 9. CSV format
Required columns:
`patient_id,doctor_id,date,diagnosis,status`

See `sample_appointments.csv`.

## 10. Troubleshooting
- `ModuleNotFoundError`: activate venv and run `pip install -r requirements.txt`.
- MySQL connection error: verify MySQL Server is running and `.env` password/database name are correct.
- `Access denied for user root`: correct the MySQL password in `.env`.
- `Unknown database hospital_db`: run `schema.sql` in MySQL Workbench.
- Port 5000 busy: change `app.run(debug=True, port=5001)` in app.py and use port 5001.
