# app.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random

db_page = Flask(__name__)

# SQLite veritabanı dosyası
db_path = r"C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db"
db_page.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
db_page.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(db_page)

# Departman Modeli
class Department(db.Model):
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=True)

    doctors = db.relationship('Doctor', backref='department', lazy=True)


# Hastane Modeli
class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    distance = db.Column(db.String(50), nullable=True)
    rating = db.Column(db.String(10), nullable=True)

    doctors = db.relationship('Doctor', backref='hospital', lazy=True)
    appointments = db.relationship('Appointment', backref='hospital_ref', lazy=True)


# Doktor Modeli
class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    experience = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.String(10), nullable=True)

    department_id = db.Column(db.String, db.ForeignKey('department.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
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

# 📌 User tablosu
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tc_no = db.Column(db.String(11), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(100), nullable=False)

    test_results = db.relationship('TestResult', backref='user', lazy=True)
    medicines = db.relationship('UserMedicine', back_populates='user')


class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    test_type = db.Column(db.String(50))  # örn: hemogram, biochemistry
    test_name = db.Column(db.String(100))  # örn: Hemoglobin
    value = db.Column(db.String(20))  # örn: "14.2"
    unit = db.Column(db.String(20))   # örn: "g/dL"
    status = db.Column(db.String(20)) # örn: normal, warning, critical
    range_info = db.Column(db.String(50))  # örn: "Normal: 12-16"
    test_date = db.Column(db.Date, default=datetime.utcnow)

# İlaç tablosu
class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    active_ingredient = db.Column(db.String(120))
    manufacturer = db.Column(db.String(120))
    price = db.Column(db.String(20))
    prescription = db.Column(db.Boolean)
    stock = db.Column(db.String(20))
    usage = db.Column(db.Text)
    warning = db.Column(db.Text)
    indication = db.Column(db.Text)

    users = db.relationship('UserMedicine', back_populates='medicine')

# Kullanıcı - İlaç ilişkisi tablosu
class UserMedicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'))
    favorited = db.Column(db.Boolean, default=False)
    ordered = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='medicines')
    medicine = db.relationship('Medicine', back_populates='users')



with db_page.app_context():
    db.drop_all()  # varsa eski tabloları siler
    db.create_all()  # yeni tabloları oluşturur

    # 20 Departman ekleyelim
    departman_isimleri = [
        "Kardiyoloji", "Nöroloji", "Ortopedi", "Dahiliye", "Çocuk Sağlığı",
        "Göz Hastalıkları", "Dermatoloji", "Psikiyatri", "KBB", "Genel Cerrahi",
        "Üroloji", "Göğüs Hastalıkları", "Radyoloji", "Fizik Tedavi", "Enfeksiyon",
        "Kadın Hastalıkları", "Nefroloji", "Endokrinoloji", "Beslenme ve Diyet", "Acil Servis"
    ]
    departmanlar = []
    for i, isim in enumerate(departman_isimleri, start=1):
        d = Department(id=str(i).zfill(3), name=isim, icon="🏥")
        db.session.add(d)
        departmanlar.append(d)

    # 5 Hastane ekleyelim
    hastane_isimleri = [
        "Şehir Hastanesi", 'Ankara Şehir Hastanesi', 'Hacettepe Üniversitesi Hastanesi', 'Gazi Üniversitesi Hastanesi', "Özel Medica", "Klinik Plus", "Sağlık Merkezi", "Devlet Hastanesi"
    ]
    hastaneler = []
    for i, isim in enumerate(hastane_isimleri, start=1):
        h = Hospital(
            id=i,
            name=isim,
            location=f"{i}. Cadde, Şehir Merkezi",
            distance=f"{random.randint(1,20)} km",
            rating=f"{random.uniform(3.5,5):.1f}"
        )
        db.session.add(h)
        hastaneler.append(h)

    # Her departman ve hastaneye 3'er doktor ekleyelim
    doktor_adlari = [ 'Prof. Dr. Ahmet Omurga', 'Prof. Dr. Selim Beyin', 'Doç. Dr. Elif Sinir', 'Uz. Dr. Can Refleks', 'Prof. Dr. Hasan İç', 'Doç. Dr. Merve Genel', 'Uz. Dr. Kemal Sistem', 
        "Dr. Ahmet Yılmaz", 'Prof. Dr. Mehmet Kardiyak', 'Uz. Dr. Ali Damar', 'Doç. Dr. Ayşe Kalp', "Dr. Ayşe Demir", "Dr. Mehmet Kaya", "Dr. Fatma Çelik",
        "Dr. Hasan Şahin", 'Prof. Dr. Fatma Ritim', "Dr. Elif Aydın", "Dr. Can Özkan", "Dr. Zeynep Korkmaz",
        "Dr. Ali Yıldız", "Dr. Selin Kurt", 'Prof. Dr. Fatma Kemik', "Dr. Emre Aksoy", "Dr. Derya Taş",
        "Dr. Murat Deniz", 'Doç. Dr. Emre Eklem', "Dr. Yasemin Öztürk", "Dr. Kerem Uysal", "Dr. Seda Polat",
        "Dr. Cem Sarı", 'Uz. Dr. Zeynep Kas', "Dr. Melis Kılıç", "Dr. Okan Acar", "Dr. Ebru Doğan"
    ]

    # Doktorları departmanlara ve hastanelere dağıt
    doktorlar = []
    idx = 0
    for d in departmanlar:
        for h in hastaneler:
            for _ in range(3):
                if idx >= len(doktor_adlari):
                    # Doktor isimleri biterse döngüyü kır
                    break
                doktor = Doctor(
                    name=doktor_adlari[idx],
                    experience=f"{random.randint(1,30)} yıl",
                    rating=f"{random.uniform(3.0,5.0):.1f}",
                    department=d,
                    hospital=h
                )
                db.session.add(doktor)
                doktorlar.append(doktor)
                idx += 1
            if idx >= len(doktor_adlari):
                break
        if idx >= len(doktor_adlari):
            break

    # 5 Kullanıcı ekleyelim
    kullanicilar = []
    for i in range(1, 6):
        kullanici = User(
            tc_no=f"1234567890{i}",
            name=f"Kullanıcı {i}",
            email=f"kullanici{i}@ornek.com",
            password="sifre123"  # örnek şifre
        )
        db.session.add(kullanici)
        kullanicilar.append(kullanici)

    # Kullanıcıların bazı test sonuçları
    test_tipleri = ["Hemogram", "Biyokimya"]
    test_ismi_ve_degerleri = [
        ("Hemoglobin", "14.2", "g/dL", "Normal", "12-16"),
        ("Glukoz", "110", "mg/dL", "Uyarı", "70-99"),
        ("Kolesterol", "190", "mg/dL", "Normal", "125-200"),
        ("Trombosit", "250", "10^3/uL", "Normal", "150-400"),
        ("Üre", "35", "mg/dL", "Normal", "10-50")
    ]
    for kullanici in kullanicilar:
        for _ in range(random.randint(1,3)):  # Her kullanıcıya 1-3 test sonucu
            test_ismi, deger, birim, durum, aralik = random.choice(test_ismi_ve_degerleri)
            test_sonucu = TestResult(
                user=kullanici,
                test_type=random.choice(test_tipleri),
                test_name=test_ismi,
                value=deger,
                unit=birim,
                status=durum,
                range_info=aralik,
                test_date=datetime.utcnow()
            )
            db.session.add(test_sonucu)

    # 2 İlaç ekleyelim
    ilaclar = [
        Medicine(
            name="Parol",
            active_ingredient="Parasetamol",
            manufacturer="ABC İlaç",
            price="15 TL",
            prescription=False,
            stock="Yeterli",
            usage="Ağrı kesici ve ateş düşürücü olarak kullanılır.",
            warning="Hamilelikte dikkatli kullanılmalı.",
            indication="Baş ağrısı, ateş, kas ağrıları"
        ),
        Medicine(
            name="Amoksilin",
            active_ingredient="Amoksisilin",
            manufacturer="XYZ İlaç",
            price="25 TL",
            prescription=True,
            stock="Orta",
            usage="Bakteriyel enfeksiyonlarda kullanılır.",
            warning="Alerjik reaksiyon riski vardır.",
            indication="Üst solunum yolu enfeksiyonları, idrar yolu enfeksiyonları"
        )
    ]
    for ilac in ilaclar:
        db.session.add(ilac)

    # Bazı kullanıcıların favori/aldığı ilaçları
    favori_ve_alanlar = [
        (kullanicilar[0], ilaclar[0], True, False),
        (kullanicilar[0], ilaclar[1], False, True),
        (kullanicilar[1], ilaclar[1], True, True),
        (kullanicilar[2], ilaclar[0], False, False)
    ]
    for kullanici, ilac, favori, aldi in favori_ve_alanlar:
        um = UserMedicine(
            user=kullanici,
            medicine=ilac,
            favorited=favori,
            ordered=aldi
        )
        db.session.add(um)

    db.session.commit()
    print("Veritabanı örnek verilerle dolduruldu.")
