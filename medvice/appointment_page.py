from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import sqlite3
from datetime import datetime, timedelta
import json


appointment_page= Blueprint('appointment_page',__name__)
def appointment():
    return render_template('appointment.html')

def get_db_connection():
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\web\\yzta_team_forty\\medvice\\db\\db.db')
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
@appointment_page.route('/api/hospitals/<int:department_id>')
def get_hospitals_by_department(department_id):
    conn = get_db_connection()
    
    query = '''
        SELECT DISTINCT h.id, h.name, h.location, h.distance, h.rating
        FROM hospital h
        JOIN hospital_departments hd ON h.id = hd.hospital_id
        WHERE hd.department_id = ?
        ORDER BY h.rating DESC
    '''
    
    hospitals = conn.execute(query, (department_id,)).fetchall()
    conn.close()
    
    return jsonify([{
        'id': hospital['id'],
        'name': hospital['name'],
        'location': hospital['location'],
        'distance': hospital['distance'],
        'rating': hospital['rating']
    } for hospital in hospitals])

# Seçilen hastane ve poliklinikle ilgili doktorları getir
@appointment_page.route('/api/doctors/<int:department_id>/<int:hospital_id>')
def get_doctors(department_id, hospital_id):
    conn = get_db_connection()
    
    query = '''
        SELECT d.id, d.name, d.experience, d.rating
        FROM doctor d
        WHERE d.department_id = ? AND d.hospital_id = ?
        ORDER BY d.rating DESC
    '''
    
    doctors = conn.execute(query, (department_id, hospital_id)).fetchall()
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
    
    # Bu tarih ve doktor için alınmış randevuları getir
    occupied_times = conn.execute('''
        SELECT appointment_time FROM appointments 
        WHERE doctor_id = ? AND appointment_date = ? AND status = 'active'
    ''', (doctor_id, date)).fetchall()
    
    conn.close()
    
    # Mevcut randevu saatleri
    occupied_time_list = [row['appointment_time'] for row in occupied_times]
    
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
    
    return jsonify(available_times)

# Randevu oluştur
@appointment_page.route('/api/create-appointment', methods=['POST'])
def create_appointment():
    data = request.json
    
    conn = get_db_connection()
    
    try:
        # Randevuyu veritabanına ekle
        conn.execute('''
            INSERT INTO appointments (patient_name, department_id, hospital_id, doctor_id, appointment_date, appointment_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data.get('patient_name', 'Hasta'),
            data['department_id'],
            data['hospital_id'],
            data['doctor_id'],
            data['appointment_date'],
            data['appointment_time']
        ))
        
        conn.commit()
        appointment_id = conn.lastrowid
        
        # Randevu detaylarını getir
        appointment_details = conn.execute('''
            SELECT a.id, a.appointment_date, a.appointment_time,
                   d.name as department_name,
                   h.name as hospital_name,
                   doc.name as doctor_name
            FROM appointments a
            JOIN department d ON a.department_id = d.id
            JOIN hospital h ON a.hospital_id = h.id
            JOIN doctor doc ON a.doctor_id = doc.id
            WHERE a.id = ?
        ''', (appointment_id,)).fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'appointment_id': appointment_id,
            'message': 'Randevunuz başarıyla oluşturuldu!',
            'details': {
                'id': appointment_details['id'],
                'department': appointment_details['department_name'],
                'hospital': appointment_details['hospital_name'],
                'doctor': appointment_details['doctor_name'],
                'date': appointment_details['appointment_date'],
                'time': appointment_details['appointment_time']
            }
        })
        
    except Exception as e:
        conn.close()
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
