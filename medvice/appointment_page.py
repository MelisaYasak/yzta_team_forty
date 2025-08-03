from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import sqlite3
from datetime import datetime, timedelta
import json
import os
import random  # Bu satırı ekleyin

def get_db_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "db", "db.db")
    
appointment_page = Blueprint('appointment_page', __name__)

@appointment_page.route('/appointment')  # Route decorator ekleyin
def appointment():
    return render_template('appointment.html')

def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row  # Dict-like erişim için
    return conn

# Tüm poliklinikleri getir
@appointment_page.route('/api/departments')
def get_departments():
    conn = get_db_connection()
    departments = conn.execute('SELECT id, name, icon FROM department ORDER BY name').fetchall()
    conn.close()
    
    return jsonify([{
        'id': dept['id'],
        'name': dept['name'],
        'icon': dept['icon']
    } for dept in departments])

# Seçilen poliklinikle ilgili hastaneleri getir
@appointment_page.route('/api/hospitals/<department_id>')  # <int:department_id> yerine <department_id>
def get_hospitals_by_department(department_id):
    conn = get_db_connection()
    
    try:
        # Önce poliklinik var mı kontrol et
        dept_check = conn.execute('SELECT name FROM department WHERE id = ?', (department_id,)).fetchone()
        if not dept_check:
            conn.close()
            return jsonify({'error': 'Poliklinik bulunamadı'}), 404
        
        # Doktor tablosundan, seçilen poliklinikteki doktorların bulunduğu hastaneleri getir
        query = '''
            SELECT DISTINCT h.id, h.name, h.location, h.distance, h.rating
            FROM hospital h
            JOIN doctor d ON h.id = d.hospital_id
            WHERE d.department_id = ? AND d.hospital_id IS NOT NULL
            ORDER BY h.rating DESC
        '''
        
        hospitals = conn.execute(query, (department_id,)).fetchall()
        
        # Debug için log ekle
        print(f"Department ID: {department_id}, Found hospitals: {len(hospitals)}")
        
        # Eğer hiç hastane bulunamazsa, tüm hastaneleri döndür (geçici çözüm)
        if len(hospitals) == 0:
            print("No hospitals found for department, returning all hospitals")
            all_hospitals = conn.execute('SELECT id, name, location, distance, rating FROM hospital ORDER BY rating DESC').fetchall()
            conn.close()
            return jsonify([{
                'id': hospital['id'],
                'name': hospital['name'],
                'location': hospital['location'] if hospital['location'] else 'Merkez',
                'distance': hospital['distance'] if hospital['distance'] else '1 km',
                'rating': hospital['rating'] if hospital['rating'] else 4.5
            } for hospital in all_hospitals])
        
        conn.close()
        
        return jsonify([{
            'id': hospital['id'],
            'name': hospital['name'],
            'location': hospital['location'] if hospital['location'] else 'Merkez',
            'distance': hospital['distance'] if hospital['distance'] else '1 km',
            'rating': hospital['rating'] if hospital['rating'] else 4.5
        } for hospital in hospitals])
        
    except Exception as e:
        conn.close()
        print(f"Error in get_hospitals_by_department: {str(e)}")
        return jsonify({'error': 'Hastaneler yüklenirken hata oluştu'}), 500

# Seçilen hastane ve poliklinikle ilgili doktorları getir
@appointment_page.route('/api/doctors/<department_id>/<int:hospital_id>')  # department_id string
def get_doctors(department_id, hospital_id):
    conn = get_db_connection()
    
    query = '''
        SELECT d.id, d.name, d.experience, d.rating
        FROM doctor d
        WHERE d.department_id = ? AND d.hospital_id = ?
        ORDER BY d.rating DESC
    '''
    
    doctors = conn.execute(query, (department_id, hospital_id)).fetchall()
    
    print(f"Looking for doctors - Department: {department_id}, Hospital: {hospital_id}")
    print(f"Found doctors: {len(doctors)}")
    
    # Eğer bu kombinasyonda doktor yoksa, aynı departmandaki diğer doktorları döndür
    if len(doctors) == 0:
        print("No doctors found for this hospital, trying other hospitals...")
        alternative_query = '''
            SELECT d.id, d.name, d.experience, d.rating, h.name as hospital_name
            FROM doctor d
            JOIN hospital h ON d.hospital_id = h.id
            WHERE d.department_id = ?
            ORDER BY d.rating DESC
            LIMIT 5
        '''
        alt_doctors = conn.execute(alternative_query, (department_id,)).fetchall()
        print(f"Alternative doctors found: {len(alt_doctors)}")
        
        if len(alt_doctors) > 0:
            conn.close()
            return jsonify([{
                'id': doctor['id'],
                'name': f"{doctor['name']} ({doctor['hospital_name']})",
                'experience': doctor['experience'],
                'rating': doctor['rating']
            } for doctor in alt_doctors])
    
    conn.close()
    
    return jsonify([{
        'id': doctor['id'],
        'name': doctor['name'],
        'experience': doctor['experience'],
        'rating': doctor['rating']
    } for doctor in doctors])

# Müsait randevu saatlerini getir
@appointment_page.route('/api/available-times/<int:doctor_id>/<date>')
def get_available_times(doctor_id, date):
    conn = get_db_connection()
    
    try:
        print(f"Getting available times for doctor {doctor_id} on {date}")
        
        # Appointments tablosu var mı kontrol et
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='appointments'"
        ).fetchone()
        
        occupied_time_list = []
        if table_check:
            # Appointments tablosu varsa, bu tarih ve doktor için alınmış randevuları getir
            occupied_times = conn.execute('''
                SELECT appointment_time FROM appointments 
                WHERE doctor_id = ? AND appointment_date = ? AND status = 'active'
            ''', (doctor_id, date)).fetchall()
            occupied_time_list = [row['appointment_time'] for row in occupied_times]
        else:
            print("Appointments table doesn't exist, creating sample data")
            # Tablo yoksa boş liste kullan
            occupied_time_list = []
        
        conn.close()
        
        print(f"Occupied times: {occupied_time_list}")
        
        # Tüm muhtemel saatler
        morning_times = ['09:00', '09:20', '09:40', '10:00', '10:20', '10:40', '11:00', '11:20', '11:40']
        afternoon_times = ['13:00', '13:20', '13:40', '14:00', '14:20', '14:40', '15:00', '15:20', '15:40', '16:00', '16:20', '16:40']
        all_times = morning_times + afternoon_times
        
        # Müsait saatleri belirle
        available_times = []
        for time in all_times:
            if time not in occupied_time_list:
                # Rastgele bazı saatleri müsait olmayan olarak işaretle (%20 şans)
                if random.random() > 0.2:
                    available_times.append({
                        'time': time,
                        'available': True
                    })
                else:
                    available_times.append({
                        'time': time,
                        'available': False
                    })
            else:
                available_times.append({
                    'time': time,
                    'available': False
                })
        
        print(f"Returning {len(available_times)} time slots")
        return jsonify(available_times)
        
    except Exception as e:
        if conn:
            conn.close()
        print(f"Error in get_available_times: {str(e)}")
        # Hata durumunda basit bir saat listesi döndür
        simple_times = [
            {'time': '09:00', 'available': True},
            {'time': '09:20', 'available': True},
            {'time': '10:00', 'available': False},
            {'time': '10:20', 'available': True},
            {'time': '11:00', 'available': True},
            {'time': '14:00', 'available': True},
            {'time': '14:20', 'available': False},
            {'time': '15:00', 'available': True},
            {'time': '15:20', 'available': True},
            {'time': '16:00', 'available': True}
        ]
        return jsonify(simple_times)

# Randevu oluştur
@appointment_page.route('/api/create-appointment', methods=['POST'])
def create_appointment():
    data = request.json
    
    conn = get_db_connection()
    
    try:
        # Appointments tablosu var mı kontrol et, yoksa oluştur
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='appointments'"
        ).fetchone()
        
        if not table_check:
            print("Creating appointments table...")
            conn.execute('''
                CREATE TABLE appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_name TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    hospital_id INTEGER NOT NULL,
                    doctor_id INTEGER NOT NULL,
                    appointment_date TEXT NOT NULL,
                    appointment_time TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        
        # Randevuyu veritabanına ekle
        cursor = conn.execute('''
            INSERT INTO appointments (patient_name, department_id, hospital_id, doctor_id, appointment_date, appointment_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data.get('patient_name', 'Hasta'),
            str(data['department_id']),  # String olarak kaydet
            data['hospital_id'],
            data['doctor_id'],
            data['appointment_date'],
            data['appointment_time']
        ))
        
        conn.commit()
        appointment_id = cursor.lastrowid  # cursor'dan al, conn'den değil
        
        conn.close()
        
        return jsonify({
            'success': True,
            'appointment_id': appointment_id,
            'message': 'Randevunuz başarıyla oluşturuldu!',
            'details': {
                'id': appointment_id,
                'department': data.get('department_name', 'Seçilen Poliklinik'),
                'hospital': data.get('hospital_name', 'Seçilen Hastane'),
                'doctor': data.get('doctor_name', 'Seçilen Doktor'),
                'date': data['appointment_date'],
                'time': data['appointment_time']
            }
        })
        
    except Exception as e:
        if conn:
            conn.close()
        print(f"Create appointment error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Randevu oluşturulurken hata: {str(e)}'
        }), 400

# Randevu detaylarını getir
@appointment_page.route('/api/appointment/<int:appointment_id>')
def get_appointment(appointment_id):
    conn = get_db_connection()
    
    appointment = conn.execute('''
        SELECT a.*, d.name as department_name, d.icon as department_icon,
               h.name as hospital_name, h.location as hospital_location,
               doc.name as doctor_name
        FROM appointments a
        JOIN department d ON a.department_id = d.id
        JOIN hospital h ON a.hospital_id = h.id
        JOIN doctor doc ON a.doctor_id = doc.id
        WHERE a.id = ?
    ''', (appointment_id,)).fetchone()
    
    conn.close()
    
    if appointment:
        return jsonify({
            'id': appointment['id'],
            'patient_name': appointment['patient_name'],
            'department': {
                'name': appointment['department_name'],
                'icon': appointment['department_icon']
            },
            'hospital': {
                'name': appointment['hospital_name'],
                'location': appointment['hospital_location']
            },
            'doctor': {
                'name': appointment['doctor_name']
            },
            'appointment_date': appointment['appointment_date'],
            'appointment_time': appointment['appointment_time'],
            'status': appointment['status'],
            'created_at': appointment['created_at']
        })
    else:
        return jsonify({'error': 'Randevu bulunamadı'}), 404