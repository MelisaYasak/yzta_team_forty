from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json


appointment_page = Blueprint('appointment_page',__name__)
db = SQLAlchemy(appointment_page)

# Veritabanı Modelleri
class Department(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=False)
    
    # İlişkiler
    doctors = db.relationship('Doctor', backref='department_ref', lazy=True)

class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    distance = db.Column(db.String(20), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    
    # İlişkiler
    doctors = db.relationship('Doctor', backref='hospital_ref', lazy=True)
    appointments = db.relationship('Appointment', backref='hospital_ref', lazy=True)

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    experience = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    department_id = db.Column(db.String(50), db.ForeignKey('department.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
    
    # İlişkiler
    appointments = db.relationship('Appointment', backref='doctor_ref', lazy=True)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(200), nullable=False)
    department_id = db.Column(db.String(50), db.ForeignKey('department.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, cancelled, completed

# Ana Sayfa Route'ları
@appointment_page.route('/')
def index():
    return redirect(url_for('welcome', username='user'))

@appointment_page.route('/welcome/<username>')
def welcome(username):
    return render_template('welcome.html', username=username)

@appointment_page.route('/appointment/<username>')
def appointment_page(username):
    return render_template('appointment.html', username=username)

# API Endpoints

@appointment_page.route('/api/departments')
def get_departments():
    """Tüm poliklinikleri getir"""
    departments = Department.query.all()
    return jsonify([{
        'id': dept.id,
        'name': dept.name,
        'icon': dept.icon
    } for dept in departments])

@appointment_page.route('/api/hospitals/<department_id>')
def get_hospitals_by_department(department_id):
    """Belirli bir poliklinik için hastaneleri getir"""
    # Department'a sahip hastaneleri bul
    hospitals = db.session.query(Hospital).join(Doctor).filter(
        Doctor.department_id == department_id
    ).distinct().all()
    
    return jsonify([{
        'id': hospital.id,
        'name': hospital.name,
        'location': hospital.location,
        'distance': hospital.distance,
        'rating': hospital.rating
    } for hospital in hospitals])

@appointment_page.route('/api/doctors/<department_id>/<int:hospital_id>')
def get_doctors(department_id, hospital_id):
    """Belirli poliklinik ve hastane için doktorları getir"""
    doctors = Doctor.query.filter_by(
        department_id=department_id,
        hospital_id=hospital_id
    ).all()
    
    return jsonify([{
        'id': doctor.id,
        'name': doctor.name,
        'experience': doctor.experience,
        'rating': doctor.rating
    } for doctor in doctors])

@appointment_page.route('/api/available-dates/<int:doctor_id>')
def get_available_dates(doctor_id):
    """Doktor için müsait tarihleri getir"""
    today = datetime.now().date()
    available_dates = []
    
    # 14 gün ileriye kadar kontrol et
    for i in range(1, 15):
        check_date = today + timedelta(days=i)
        
        # Pazar günleri hariç
        if check_date.weekday() == 6:  # Pazar = 6
            continue
            
        # O gün için randevu sayısını kontrol et
        existing_appointments = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=check_date,
            status='active'
        ).count()
        
        # Günde maksimum 20 randevu (örnek)
        if existing_appointments < 20:
            available_dates.append(check_date.isoformat())
    
    return jsonify(available_dates)

@appointment_page.route('/api/available-times/<int:doctor_id>/<date>')
def get_available_times(doctor_id, date):
    """Belirli tarih için müsait saatleri getir"""
    appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Mevcut randevuları al
    existing_appointments = Appointment.query.filter_by(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        status='active'
    ).all()
    
    booked_times = [apt.appointment_time.strftime('%H:%M') for apt in existing_appointments]
    
    # Tüm müsait saatler
    morning_times = ['09:00', '09:20', '09:40', '10:00', '10:20', '10:40', '11:00', '11:20', '11:40']
    afternoon_times = ['13:00', '13:20', '13:40', '14:00', '14:20', '14:40', '15:00', '15:20', '15:40', '16:00', '16:20', '16:40']
    
    all_times = morning_times + afternoon_times
    available_times = [time for time in all_times if time not in booked_times]
    
    return jsonify(available_times)

@appointment_page.route('/api/appointments', methods=['POST'])
def create_appointment():
    """Yeni randevu oluştur"""
    data = request.get_json()
    
    try:
        # Verileri validate et
        required_fields = ['patient_name', 'department_id', 'hospital_id', 'doctor_id', 'date', 'time']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} gerekli'}), 400
        
        # Tarih ve saat parsing
        appointment_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        appointment_time = datetime.strptime(data['time'], '%H:%M').time()
        
        # Çakışma kontrolü
        existing = Appointment.query.filter_by(
            doctor_id=data['doctor_id'],
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            status='active'
        ).first()
        
        if existing:
            return jsonify({'error': 'Bu saat dolu'}), 400
        
        # Yeni randevu oluştur
        new_appointment = Appointment(
            patient_name=data['patient_name'],
            department_id=data['department_id'],
            hospital_id=data['hospital_id'],
            doctor_id=data['doctor_id'],
            appointment_date=appointment_date,
            appointment_time=appointment_time
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'appointment_id': new_appointment.id,
            'message': 'Randevu başarıyla oluşturuldu'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@appointment_page.route('/api/appointments/<username>')
def get_user_appointments(username):
    """Kullanıcının randevularını getir"""
    appointments = db.session.query(Appointment, Department, Hospital, Doctor).join(
        Department, Appointment.department_id == Department.id
    ).join(
        Hospital, Appointment.hospital_id == Hospital.id
    ).join(
        Doctor, Appointment.doctor_id == Doctor.id
    ).filter(
        Appointment.patient_name == username,
        Appointment.status == 'active'
    ).all()
    
    result = []
    for apt, dept, hospital, doctor in appointments:
        result.append({
            'id': apt.id,
            'department': dept.name,
            'hospital': hospital.name,
            'doctor': doctor.name,
            'date': apt.appointment_date.isoformat(),
            'time': apt.appointment_time.strftime('%H:%M'),
            'created_at': apt.created_at.isoformat()
        })
    
    return jsonify(result)

# Veritabanını başlat ve örnek veri ekle
def init_database():
    """Veritabanını başlat ve örnek verileri ekle"""
    with appointment_page.app_context():
        db.create_all()
        
        # Eğer veri yoksa örnek verileri ekle
        if Department.query.count() == 0:
            # Poliklinikler
            departments = [
                Department(id='kardiyoloji', name='Kardiyoloji', icon='❤️'),
                Department(id='ortopedi', name='Ortopedi', icon='🦴'),
                Department(id='noroloji', name='Nöroloji', icon='🧠'),
                Department(id='dahiliye', name='Dahiliye', icon='🩺'),
                Department(id='goz', name='Göz Hastalıkları', icon='👁️'),
                Department(id='kulak', name='Kulak Burun Boğaz', icon='👂')
            ]
            
            for dept in departments:
                db.session.add(dept)
            
            # Hastaneler
            hospitals = [
                Hospital(id=1, name='Ankara Şehir Hastanesi', location='Bilkent, Ankara', 
                        distance='2.5 km', rating=4.8),
                Hospital(id=2, name='Hacettepe Üniversitesi Hastanesi', location='Sıhhiye, Ankara', 
                        distance='3.2 km', rating=4.9),
                Hospital(id=3, name='Gazi Üniversitesi Hastanesi', location='Beşevler, Ankara', 
                        distance='4.1 km', rating=4.7),
                Hospital(id=4, name='Ankara Üniversitesi Hastanesi', location='Cebeci, Ankara', 
                        distance='3.8 km', rating=4.6)
            ]
            
            for hospital in hospitals:
                db.session.add(hospital)
            
            db.session.commit()
            
            # Doktorlar
            doctors_data = [
                # Kardiyoloji
                ('Prof. Dr. Mehmet Kardiyak', '25 yıl', 4.9, 'kardiyoloji', 1),
                ('Doç. Dr. Ayşe Kalp', '15 yıl', 4.8, 'kardiyoloji', 1),
                ('Uz. Dr. Ali Damar', '12 yıl', 4.7, 'kardiyoloji', 2),
                ('Prof. Dr. Fatma Ritim', '20 yıl', 4.8, 'kardiyoloji', 2),
                
                # Ortopedi
                ('Prof. Dr. Fatma Kemik', '20 yıl', 4.8, 'ortopedi', 1),
                ('Doç. Dr. Emre Eklem', '18 yıl', 4.9, 'ortopedi', 2),
                ('Uz. Dr. Zeynep Kas', '10 yıl', 4.6, 'ortopedi', 3),
                ('Prof. Dr. Ahmet Omurga', '22 yıl', 4.7, 'ortopedi', 1),
                
                # Nöroloji
                ('Prof. Dr. Selim Beyin', '28 yıl', 4.9, 'noroloji', 2),
                ('Doç. Dr. Elif Sinir', '16 yıl', 4.8, 'noroloji', 3),
                ('Uz. Dr. Can Refleks', '14 yıl', 4.7, 'noroloji', 4),
                
                # Dahiliye
                ('Prof. Dr. Hasan İç', '25 yıl', 4.8, 'dahiliye', 1),
                ('Doç. Dr. Merve Genel', '18 yıl', 4.7, 'dahiliye', 2),
                ('Uz. Dr. Kemal Sistem', '12 yıl', 4.6, 'dahiliye', 3)
            ]
            
            for name, exp, rating, dept_id, hospital_id in doctors_data:
                doctor = Doctor(
                    name=name,
                    experience=exp,
                    rating=rating,
                    department_id=dept_id,
                    hospital_id=hospital_id
                )
                db.session.add(doctor)
            
            db.session.commit()
            print("Örnek veriler başarıyla eklendi!")

