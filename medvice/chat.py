from flask import Flask, request, jsonify, Blueprint,abort,session
from flask_cors import CORS
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import google.generativeai as genai
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import pickle
from datetime import datetime, timedelta
import logging
import os
import re
import random
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Gemini API anahtarını al
gemini_api_key = os.getenv("GEMINI_API_KEY")
# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

chat = Blueprint('chat', __name__)
CORS(chat)

# Gemini API config
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

# Pydantic modelleri
class QuestionRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    similarity_threshold: Optional[float] = 0.3

class QuestionResponse(BaseModel):
    question: str
    answer: str
    relevant_docs: List[Dict]
    similarity_scores: List[float]
    processing_time: float
    success: bool
    message: Optional[str] = None

# ==================== MEDVİCE RANDEVU SİSTEMİ ====================
# Bu kodu chat.py dosyanıza, import'lardan sonra, class EnhancedRAGSystem'den önce ekleyin

class MedviceAppointmentSystem:
    """Medvice randevu sistemi - AI model ve hospital.py entegreli"""
    
    def __init__(self):
        # Session bazlı randevu takibi
        self.appointment_sessions = {}
        
        # Randevu akış durumları
        self.STATES = {
            'IDLE': 'idle',
            'DEPARTMENT_SUGGESTED': 'department_suggested', 
            'HOSPITAL_SELECTION': 'hospital_selection',
            'DOCTOR_SELECTION': 'doctor_selection',
            'DATE_SELECTION': 'date_selection',
            'TIME_SELECTION': 'time_selection',
            'CONFIRMATION': 'confirmation'
        }
    
    def get_session_id(self):
        """Session ID al veya oluştur"""
        if 'medvice_session' not in session:
            session['medvice_session'] = f"medvice_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        return session['medvice_session']
    
    def get_session_data(self, session_id):
        """Session verilerini al"""
        return self.appointment_sessions.get(session_id, {
            'state': self.STATES['IDLE'],
            'data': {},
            'last_ai_response': ''
        })
    
    def update_session_data(self, session_id, data):
        """Session verilerini güncelle"""
        self.appointment_sessions[session_id] = data
    
    def detect_appointment_intent(self, user_message, ai_response):
        """Randevu niyeti tespit et"""
        message_lower = user_message.lower()
        ai_lower = (ai_response or "").lower()
        
        # Randevu keywords
        appointment_keywords = [
            'randevu', 'randevu al', 'randevu istiyorum',
            'doktora git', 'muayene ol', 'hastaneye git',
            'doktor bul', 'randevu ayarla'
        ]
        
        # Aciliyet keywords
        urgency_keywords = ['acil', 'derhal', 'hemen', 'acele']
        
        intent_score = 0
        urgency_level = 'normal'
        
        # Randevu niyeti kontrolü
        for keyword in appointment_keywords:
            if keyword in message_lower:
                intent_score += 3
                break
        
        # AI yanıtında bölüm önerisi var mı?
        if any(word in ai_lower for word in ['başvuru birimi:', 'bölüm:', 'önerilen']):
            intent_score += 2
        
        # Aciliyet kontrolü
        for keyword in urgency_keywords:
            if keyword in message_lower or keyword in ai_lower:
                urgency_level = 'urgent'
                intent_score += 2
                break
        
        return {
            'has_intent': intent_score >= 2,
            'score': intent_score,
            'urgency': urgency_level,
            'should_start_flow': intent_score >= 3 or urgency_level == 'urgent'
        }
    
    def extract_department_from_ai_response(self, ai_response):
        """AI yanıtından bölüm çıkar"""
        if not ai_response:
            return None
        
        ai_lower = ai_response.lower()
        
        # Pattern'lerle ara
        patterns = [
            r'başvuru birimi:\s*([^\n]+)',
            r'bölüm:\s*([^\n]+)', 
            r'önerilen bölüm[:\s]*([^\n]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ai_lower)
            if match:
                suggested = match.group(1).strip()
                # AI'nin önerdiği bölümü temizle
                suggested = suggested.replace('[', '').replace(']', '').strip()
                return suggested
        
        return None
    
    def get_hospitals_for_department(self, department):
        """Hospital.py'den bölüm için hastaneleri getir"""
        try:
            # Hospital.py modellerini import et
            from hospital import Hospital, Doctor, Department, db
            
            # Department'ı bul
            dept_obj = Department.query.filter_by(name=department).first()
            if not dept_obj:
                # Eğer tam eşleşme yoksa, benzer aramaya geç
                dept_obj = Department.query.filter(Department.name.contains(department)).first()
            
            if not dept_obj:
                logger.warning(f"Bölüm bulunamadı: {department}")
                return []
            
            # Bu bölümde doktoru olan hastaneleri bul
            hospital_ids = db.session.query(Doctor.hospital_id).filter_by(
                department_id=dept_obj.id
            ).distinct().all()
            
            if not hospital_ids:
                return []
            
            hospital_ids = [hid[0] for hid in hospital_ids]
            hospitals = Hospital.query.filter(Hospital.id.in_(hospital_ids)).all()
            
            # Hastane verilerini dönüştür
            result = []
            for hospital in hospitals:
                result.append({
                    'id': hospital.id,
                    'name': hospital.name,
                    'address': hospital.location,
                    'distance': hospital.distance,
                    'rating': float(hospital.rating) if hospital.rating else 4.0
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Hastane listesi alınamadı: {e}")
            # Fallback: Mock data
            return [{
                'id': 1,
                'name': 'Adapazarı Devlet Hastanesi',
                'address': 'Yağcılar Mah. Atatürk Bulvarı No:123',
                'distance': '2.3 km',
                'rating': 4.2
            }]
    
    def get_doctors_for_hospital_department(self, hospital_id, department):
        """Hospital.py'den doktorları getir"""
        try:
            from hospital import Doctor, Department, db
            
            # Department ID'sini bul
            dept_obj = Department.query.filter_by(name=department).first()
            if not dept_obj:
                dept_obj = Department.query.filter(Department.name.contains(department)).first()
            
            if not dept_obj:
                return []
            
            # Doktorları al
            doctors = Doctor.query.filter_by(
                hospital_id=hospital_id,
                department_id=dept_obj.id
            ).all()
            
            result = []
            for doctor in doctors:
                # Experience'dan yıl sayısını çıkar
                experience_years = 5  # varsayılan
                if doctor.experience:
                    exp_match = re.search(r'(\d+)', doctor.experience)
                    if exp_match:
                        experience_years = int(exp_match.group(1))
                
                result.append({
                    'id': doctor.id,
                    'name': doctor.name,
                    'experience': experience_years,
                    'rating': float(doctor.rating) if doctor.rating else 4.5
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Doktor listesi alınamadı: {e}")
            # Fallback: Mock data
            return [{'id': 1, 'name': 'Dr. Mehmet Yılmaz', 'experience': 12, 'rating': 4.7}]
    
    def get_available_times(self, doctor_id, date):
        """Müsait saatleri getir"""
        all_times = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", 
                    "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
        
        # Rastgele bazılarını çıkar (gerçek sistemde veritabanından gelecek)
        available = all_times.copy()
        remove_count = random.randint(2, 5)
        for _ in range(remove_count):
            if available:
                available.pop(random.randint(0, len(available)-1))
        
        return available
    
    def enhance_ai_response_with_appointment(self, session_id, user_message, ai_response):
        """AI yanıtını randevu sistemiyle geliştir"""
        session_data = self.get_session_data(session_id)
        current_state = session_data['state']
        
        # Eğer aktif randevu akışı varsa, onu devam ettir
        if current_state != self.STATES['IDLE']:
            return self.handle_appointment_flow(session_id, user_message)
        
        # Yeni randevu niyeti kontrolü
        intent = self.detect_appointment_intent(user_message, ai_response)
        
        if not intent['has_intent']:
            return ai_response
        
        # AI yanıtından bölüm çıkar
        suggested_department = self.extract_department_from_ai_response(ai_response)
        
        if suggested_department:
            # Randevu akışını başlat
            session_data['state'] = self.STATES['DEPARTMENT_SUGGESTED']
            session_data['data'] = {
                'suggested_department': suggested_department,
                'original_ai_response': ai_response,
                'urgency': intent['urgency']
            }
            session_data['last_ai_response'] = ai_response
            
            self.update_session_data(session_id, session_data)
            
            # AI yanıtını geliştir
            enhanced_response = ai_response + f"""

🏥 **Randevu Alma Sistemi Aktif**

Analizime göre size **{suggested_department}** bölümünü öneriyorum.

Randevu almak ister misiniz?
• ✅ **Evet, randevu al**
• 🔄 **Başka bölüm öner** 
• ❌ **Hayır, sadece bilgi istiyorum**

Randevu almak için yukarıdaki seçeneklerden birini yazın."""
            
            return enhanced_response
        
        return ai_response
    
    def handle_appointment_flow(self, session_id, user_message):
        """Randevu akışını yönet"""
        session_data = self.get_session_data(session_id)
        current_state = session_data['state']
        
        message_lower = user_message.lower()
        
        try:
            if current_state == self.STATES['DEPARTMENT_SUGGESTED']:
                return self._handle_department_confirmation(session_id, message_lower, session_data)
            
            elif current_state == self.STATES['HOSPITAL_SELECTION']:
                return self._handle_hospital_selection(session_id, message_lower, session_data)
            
            elif current_state == self.STATES['DOCTOR_SELECTION']:
                return self._handle_doctor_selection(session_id, message_lower, session_data)
            
            elif current_state == self.STATES['DATE_SELECTION']:
                return self._handle_date_selection(session_id, user_message, session_data)
            
            elif current_state == self.STATES['TIME_SELECTION']:
                return self._handle_time_selection(session_id, message_lower, session_data)
            
            elif current_state == self.STATES['CONFIRMATION']:
                return self._handle_final_confirmation(session_id, message_lower, session_data)
            
            else:
                self._reset_session(session_id)
                return "Randevu akışında bir hata oluştu. Tekrar başlayabilirsiniz."
                
        except Exception as e:
            self._reset_session(session_id)
            return f"Randevu işlemi sırasında hata: {str(e)}"
    
    def _handle_department_confirmation(self, session_id, message_lower, session_data):
        """Bölüm onayını işle"""
        appointment_data = session_data['data']
        
        if any(word in message_lower for word in ['evet', 'tamam', 'randevu al', 'istiyorum']):
            department = appointment_data['suggested_department']
            hospitals = self.get_hospitals_for_department(department)
            
            if not hospitals:
                self._reset_session(session_id)
                return f"Üzgünüm, {department} bölümünde şu anda hastane bulunamadı."
            
            appointment_data['confirmed_department'] = department
            appointment_data['available_hospitals'] = hospitals
            session_data['state'] = self.STATES['HOSPITAL_SELECTION']
            
            response = f"✅ **{department}** bölümü seçildi.\n\n"
            response += "**En yakın hastaneler:**\n\n"
            
            for i, hospital in enumerate(hospitals, 1):
                response += f"**{i}. {hospital['name']}**\n"
                response += f"📍 {hospital['address']}\n"
                response += f"📏 {hospital['distance']} • ⭐ {hospital['rating']}/5\n\n"
            
            response += "Hangi hastaneyi seçmek istersiniz? (Numara veya hastane adını yazın)"
            
            self.update_session_data(session_id, session_data)
            return response
        
        elif any(word in message_lower for word in ['başka', 'farklı', 'değiştir']):
            self._reset_session(session_id)
            return "Hangi bölümden randevu almak istiyorsunuz? Semptomlarınızı tekrar belirtin."
        
        elif any(word in message_lower for word in ['hayır', 'istemiyorum', 'iptal']):
            self._reset_session(session_id)
            return "Anladım. Başka bir konuda yardımcı olabilir miyim?"
        
        else:
            return "Lütfen 'Evet', 'Hayır' veya 'Başka bölüm' seçeneklerinden birini seçin."
    
    def _handle_hospital_selection(self, session_id, message_lower, session_data):
        """Hastane seçimi"""
        appointment_data = session_data['data']
        hospitals = appointment_data['available_hospitals']
        
        selected_hospital = None
        
        # Numara ile seçim
        if message_lower.isdigit():
            idx = int(message_lower) - 1
            if 0 <= idx < len(hospitals):
                selected_hospital = hospitals[idx]
        
        # İsimle seçim
        if not selected_hospital:
            for hospital in hospitals:
                if any(word in hospital['name'].lower() for word in message_lower.split()):
                    selected_hospital = hospital
                    break
        
        if not selected_hospital:
            hospital_list = "\n".join([f"{i+1}. {h['name']}" for i, h in enumerate(hospitals)])
            return f"Lütfen geçerli bir hastane seçin:\n{hospital_list}"
        
        # Doktorları getir
        department = appointment_data['confirmed_department']
        doctors = self.get_doctors_for_hospital_department(selected_hospital['id'], department)
        
        if not doctors:
            return f"Üzgünüm, {selected_hospital['name']} hastanesinde {department} bölümünde doktor bulunmuyor."
        
        appointment_data['selected_hospital'] = selected_hospital
        appointment_data['available_doctors'] = doctors
        session_data['state'] = self.STATES['DOCTOR_SELECTION']
        
        response = f"✅ **{selected_hospital['name']}** seçildi.\n\n"
        response += f"**{department}** bölümündeki doktorlar:\n\n"
        
        for i, doctor in enumerate(doctors, 1):
            response += f"**{i}. {doctor['name']}**\n"
            response += f"👨‍⚕️ {doctor['experience']} yıl deneyim • ⭐ {doctor['rating']}/5\n\n"
        
        response += "Hangi doktoru seçmek istersiniz?"
        
        self.update_session_data(session_id, session_data)
        return response
    
    def _handle_doctor_selection(self, session_id, message_lower, session_data):
        """Doktor seçimi"""
        appointment_data = session_data['data']
        doctors = appointment_data['available_doctors']
        
        selected_doctor = None
        
        # Numara ile seçim
        if message_lower.isdigit():
            idx = int(message_lower) - 1
            if 0 <= idx < len(doctors):
                selected_doctor = doctors[idx]
        
        # İsimle seçim
        if not selected_doctor:
            for doctor in doctors:
                if any(word in doctor['name'].lower() for word in message_lower.split()):
                    selected_doctor = doctor
                    break
        
        if not selected_doctor:
            doctor_list = "\n".join([f"{i+1}. {d['name']}" for i, d in enumerate(doctors)])
            return f"Lütfen geçerli bir doktor seçin:\n{doctor_list}"
        
        appointment_data['selected_doctor'] = selected_doctor
        session_data['state'] = self.STATES['DATE_SELECTION']
        
        response = f"✅ **{selected_doctor['name']}** doktoru seçildi.\n\n"
        response += "Randevu tarihi seçin:\n"
        response += "• **Bugün**\n"
        response += "• **Yarın**\n"
        response += "• **Bu hafta** (otomatik uygun gün)\n"
        response += "• Belirli tarih (örn: 15 Ağustos)\n\n"
        response += "Ne zaman randevu almak istersiniz?"
        
        self.update_session_data(session_id, session_data)
        return response
    
    def _handle_date_selection(self, session_id, user_message, session_data):
        """Tarih seçimi"""
        appointment_data = session_data['data']
        message_lower = user_message.lower()
        
        today = datetime.now()
        selected_date = None
        
        if 'bugün' in message_lower:
            selected_date = today
        elif 'yarın' in message_lower:
            selected_date = today + timedelta(days=1)
        elif 'bu hafta' in message_lower:
            selected_date = today + timedelta(days=1)
        else:
            # Basit tarih parsing
            selected_date = today + timedelta(days=1)  # Varsayılan yarın
        
        date_str = selected_date.strftime('%Y-%m-%d')
        doctor_id = appointment_data['selected_doctor']['id']
        available_times = self.get_available_times(doctor_id, date_str)
        
        if not available_times:
            return f"{selected_date.strftime('%d.%m.%Y')} tarihinde müsait saat yok. Başka bir tarih seçin."
        
        appointment_data['selected_date'] = date_str
        appointment_data['available_times'] = available_times
        session_data['state'] = self.STATES['TIME_SELECTION']
        
        response = f"✅ **{selected_date.strftime('%d.%m.%Y')}** tarihi seçildi.\n\n"
        response += "Müsait saatler:\n\n"
        
        for i, time in enumerate(available_times, 1):
            response += f"**{i}.** {time}\n"
        
        response += "\nHangi saati tercih edersiniz?"
        
        self.update_session_data(session_id, session_data)
        return response
    
    def _handle_time_selection(self, session_id, message_lower, session_data):
        """Saat seçimi"""
        appointment_data = session_data['data']
        times = appointment_data['available_times']
        
        selected_time = None
        
        # Numara ile seçim
        if message_lower.isdigit():
            idx = int(message_lower) - 1
            if 0 <= idx < len(times):
                selected_time = times[idx]
        
        # Saat ile seçim
        if not selected_time:
            for time in times:
                if time in message_lower:
                    selected_time = time
                    break
        
        if not selected_time:
            time_list = "\n".join([f"{i+1}. {t}" for i, t in enumerate(times)])
            return f"Lütfen geçerli bir saat seçin:\n{time_list}"
        
        appointment_data['selected_time'] = selected_time
        session_data['state'] = self.STATES['CONFIRMATION']
        
        # Özet
        summary = "📋 **Randevu Özeti:**\n\n"
        summary += f"🏥 Hastane: {appointment_data['selected_hospital']['name']}\n"
        summary += f"👨‍⚕️ Doktor: {appointment_data['selected_doctor']['name']}\n"
        summary += f"🏥 Bölüm: {appointment_data['confirmed_department']}\n"
        summary += f"📅 Tarih: {appointment_data['selected_date']}\n"
        summary += f"🕐 Saat: {selected_time}\n\n"
        summary += "Onaylıyor musunuz?\n"
        summary += "• ✅ **Evet, oluştur**\n"
        summary += "• ❌ **Hayır, iptal et**"
        
        self.update_session_data(session_id, session_data)
        return summary
    
    def _handle_final_confirmation(self, session_id, message_lower, session_data):
        """Final onay"""
        appointment_data = session_data['data']
        
        if any(word in message_lower for word in ['evet', 'onay', 'oluştur', 'tamam']):
            # Randevu oluştur
            appointment_id = f"RDV{datetime.now().strftime('%Y%m%d')}{random.randint(1000,9999)}"
            
            success_msg = "🎉 **Randevunuz oluşturuldu!**\n\n"
            success_msg += f"📋 **Randevu No:** {appointment_id}\n"
            success_msg += f"🏥 **Hastane:** {appointment_data['selected_hospital']['name']}\n"
            success_msg += f"👨‍⚕️ **Doktor:** {appointment_data['selected_doctor']['name']}\n"
            success_msg += f"📅 **Tarih:** {appointment_data['selected_date']}\n"
            success_msg += f"🕐 **Saat:** {appointment_data['selected_time']}\n\n"
            success_msg += "📞 Randevu günü hastaneyi arayarak doğrulama yapabilirsiniz.\n"
            success_msg += "💡 Randevu saatinden 15 dakika önce hastanede olmanız önerilir.\n\n"
            success_msg += "Başka bir konuda yardımcı olabilir miyim?"
            
            self._reset_session(session_id)
            return success_msg
        
        elif any(word in message_lower for word in ['hayır', 'iptal']):
            self._reset_session(session_id)
            return "Randevu iptal edildi. Başka nasıl yardımcı olabilirim?"
        
        else:
            return "Lütfen 'Evet' veya 'Hayır' olarak yanıtlayın."
    
    def _reset_session(self, session_id):
        """Session'ı sıfırla"""
        self.appointment_sessions[session_id] = {
            'state': self.STATES['IDLE'],
            'data': {},
            'last_ai_response': ''
        }
    
    def is_in_appointment_flow(self, session_id):
        """Randevu akışında mı kontrol et"""
        session_data = self.get_session_data(session_id)
        return session_data['state'] != self.STATES['IDLE']


medvice_system = MedviceAppointmentSystem()



class EnhancedRAGSystem:
    def __init__(self, json_file_path: str, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Gelişmiş RAG sistemi - FAISS + Sentence Embeddings
        
        Args:
            json_file_path: JSON veri dosyası yolu
            model_name: Kullanılacak sentence transformer modeli
        """
        self.json_file_path = json_file_path
        self.model_name = model_name
        self.embedding_dim = None
        self.faiss_index = None
        self.sentence_model = None
        
        # Cache dosyaları
        self.embeddings_cache_file = f"{json_file_path}_embeddings.pkl"
        self.index_cache_file = f"{json_file_path}_faiss.index"
        self.metadata_cache_file = f"{json_file_path}_metadata.pkl"
        
        # Veri yükleme ve işleme
        self.load_data()
        self.load_or_create_embeddings()
        
    def load_data(self):
        """JSON verilerini yükle"""
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            self.data = [
                dict({"anahtar": key}, **value) for key, value in raw_data.items()
            ]
        
        # Metinleri hazırla
        self.texts = []
        self.metadata = []
        
        for item in self.data:
            text = self.extract_text_from_item(item)
            self.texts.append(text)
            self.metadata.append(item)
        
    
    def extract_text_from_item(self, item: Dict) -> str:
        """JSON öğesinden aranabilir metin çıkar"""
        text_parts = []
        
        # Önemli alanları önceliklendir
        priority_fields = ['hastalık_adı', 'belirtiler', 'semptomlar', 'açıklama', 'tanı', 'tedavi']
        
        # Önce öncelikli alanları ekle
        for field in priority_fields:
            if field in item:
                value = item[field]
                if isinstance(value, (str, int, float)):
                    text_parts.append(f"{field}: {value}")
                elif isinstance(value, list):
                    text_parts.append(f"{field}: {' '.join(map(str, value))}")
        
        # Sonra diğer alanları ekle
        for key, value in item.items():
            if key not in priority_fields and key != 'anahtar':
                if isinstance(value, (str, int, float)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, list):
                    text_parts.append(f"{key}: {' '.join(map(str, value))}")
        
        return " ".join(text_parts)
    
    def load_sentence_model(self):
        """Sentence transformer modelini yükle"""
        if self.sentence_model is None:
            self.sentence_model = SentenceTransformer(self.model_name)
            self.embedding_dim = self.sentence_model.get_sentence_embedding_dimension()
    
    def load_or_create_embeddings(self):
        """Embeddings'leri yükle veya oluştur"""
        self.load_sentence_model()
        
        # Cache dosyalarının varlığını kontrol et
        cache_exists = (
            os.path.exists(self.embeddings_cache_file) and 
            os.path.exists(self.index_cache_file) and 
            os.path.exists(self.metadata_cache_file)
        )
        
        if cache_exists:
            self.load_from_cache()
        else:
            self.create_embeddings()
            self.save_to_cache()
    
    def create_embeddings(self):
        """Embeddings oluştur ve FAISS index'i hazırla"""
        
        # Batch processing ile embeddings oluştur
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(self.texts), batch_size):
            batch_texts = self.texts[i:i+batch_size]
            batch_embeddings = self.sentence_model.encode(
                batch_texts, 
                convert_to_numpy=True,
                show_progress_bar=True if i == 0 else False
            )
            all_embeddings.append(batch_embeddings)
            
            if i % (batch_size * 10) == 0:
                logger.info(f"İşlenen: {i}/{len(self.texts)}")
        
        self.embeddings = np.vstack(all_embeddings).astype('float32')
        
        # FAISS index oluştur
        self.create_faiss_index()
    
    def create_faiss_index(self):
        """FAISS index oluştur"""
        
        # Index tipi seç (dataset boyutuna göre)
        if len(self.embeddings) < 10000:
            # Küçük dataset için exact search
            self.faiss_index = faiss.IndexFlatIP(self.embedding_dim)  # Cosine similarity
        else:
            # Büyük dataset için approximate search
            nlist = min(100, len(self.embeddings) // 100)  # cluster sayısı
            quantizer = faiss.IndexFlatIP(self.embedding_dim)
            self.faiss_index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, nlist)
            
        # Embeddings'leri normalize et (cosine similarity için)
        faiss.normalize_L2(self.embeddings)
        
        # Index'i train et (IVF için gerekli)
        if hasattr(self.faiss_index, 'train'):
            self.faiss_index.train(self.embeddings)
        
        # Embeddings'leri index'e ekle
        self.faiss_index.add(self.embeddings)
        
    
    def save_to_cache(self):
        """Cache dosyalarını kaydet"""
        
        # Embeddings'leri kaydet
        with open(self.embeddings_cache_file, 'wb') as f:
            pickle.dump(self.embeddings, f)
        
        # FAISS index'i kaydet
        faiss.write_index(self.faiss_index, self.index_cache_file)
        
        # Metadata'yı kaydet
        with open(self.metadata_cache_file, 'wb') as f:
            pickle.dump({
                'metadata': self.metadata,
                'texts': self.texts,
                'model_name': self.model_name,
                'embedding_dim': self.embedding_dim,
                'created_at': datetime.now().isoformat()
            }, f)
        
    
    def load_from_cache(self):
        """Cache dosyalarından yükle"""
        try:
            # Embeddings'leri yükle
            with open(self.embeddings_cache_file, 'rb') as f:
                self.embeddings = pickle.load(f)
            
            # FAISS index'i yükle
            self.faiss_index = faiss.read_index(self.index_cache_file)
            
            # Metadata'yı yükle
            with open(self.metadata_cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                self.metadata = cache_data['metadata']
                self.texts = cache_data['texts']
                self.embedding_dim = cache_data['embedding_dim']
            
            
        except Exception as e:
            self.create_embeddings()
            self.save_to_cache()
    
    def search_similar(self, query: str, top_k: int = 5, similarity_threshold: float = 0.3) -> tuple[List[Dict], List[float]]:
        """Sorguya en benzer belgeleri bul"""
        start_time = datetime.now()
        
        # Query embedding'i oluştur
        query_embedding = self.sentence_model.encode([query], convert_to_numpy=True).astype('float32')
        faiss.normalize_L2(query_embedding)
        
        # FAISS ile arama yap
        similarities, indices = self.faiss_index.search(query_embedding, top_k)
        
        results = []
        similarity_scores = []
        
        for score, idx in zip(similarities[0], indices[0]):
            if idx != -1 and score >= similarity_threshold:  # -1 = not found
                results.append({
                    'content': self.metadata[idx],
                    'text': self.texts[idx],
                    'index': int(idx)
                })
                similarity_scores.append(float(score))
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return results, similarity_scores
    
    def ask_question(self, question: str, top_k: int = 5, similarity_threshold: float = 0.3) -> tuple[str, List[Dict], List[float], float]:
        """RAG ile soru cevapla"""
        start_time = datetime.now()
        
        session_id = medvice_system.get_session_id()

        if medvice_system.is_in_appointment_flow(session_id):
            medvice_response = medvice_system.handle_appointment_flow(session_id, question)
            processing_time = (datetime.now() - start_time).total_seconds()
            return medvice_response, [], [], processing_time
        # İlgili belgeleri bul
        relevant_docs, similarity_scores = self.search_similar(question, top_k, similarity_threshold)
        
        if not relevant_docs:
            processing_time = (datetime.now() - start_time).total_seconds()
            return "Üzgünüm, sorunuzla ilgili yeterli bilgi bulamadım. Lütfen daha detaylı belirtiler yazın.\n Örneğin 24 yaşındayım, baş ağrım ve mide bulantım var", [], [], processing_time
        
        # Kontekst oluştur - en benzer belgeleri öncelikle
        context_parts = []
        for i, doc in enumerate(relevant_docs):
            score = similarity_scores[i]
            context_parts.append(f"[Benzerlik: {score:.2f}] {doc['text'][:500]}...")
        
        context = "\n\n".join(context_parts)
        
        # Gelişmiş prompt
        prompt = f"""
        Sen deneyimli bir tıbbi asistan AI'sın. Aşağıdaki yapılandırılmış tıbbi bilgiler ışığında kullanıcının belirtilerini analiz et.

        **ÖNEMLİ KURALLAR:**
        1. SADECE verilen konteksteki bilgileri kullan
        2. Kesin tanı koyma, sadece olasılıkları belirt
        3. Aciliyet seviyesini net bir şekilde belirt
        4. Hangi tıbbi birime başvurması gerektiğini söyle
        5. Hastalığın acileyet seviyesini belirtirken acile hemen gidilmeli mi gidilmememli mi sorusuna cevap verecek şekilde düzenlemelisin.

        **KONTEKST (Benzerlik skorlarıyla sıralanmış):**
        {context}

        **KULLANICI BELİRTİLERİ:**
        {question}

        **YANIT FORMATI:**
        🔍 Olası Durum(lar): [En olası 1-2 hastalık]
        
        ⚠️ Aciliyet Seviyesi: [Düşük/Orta/Yüksek/ACİL]
        
        🏥 Başvuru Birimi: [Hangi bölüm/uzman]
        
        📝 Açıklama: [Kısa değerlendirme ve öneriler]
        
        ⚡ Eğer ACİL: Derhal hastaneye başvurun!

        Eğer verilen bilgilerle eşleşme bulamazsan: "Bu belirtilerle tam eşleşen bilgi yok, genel tıbbi değerlendirme öneriyorum."
        """
        
        try:
            response = model.generate_content(prompt)
            answer = response.text
        except Exception as e:
            answer = f"AI yanıt oluşturma hatası: {str(e)}"
        

        enhanced_answer = medvice_system.enhance_ai_response_with_appointment(
            session_id, question, answer
        )

        processing_time = (datetime.now() - start_time).total_seconds()
        return enhanced_answer, relevant_docs, similarity_scores, processing_time

# Gemini API'yi yapılandır
genai.configure(api_key="AIzaSyC29VH13ZDaAwIepdefoqWnVzl3ommWqAk")  # Gerçek API key'inizi buraya koyun
model = genai.GenerativeModel('gemini-2.0-flash')

@chat.before_app_request
def load_rag():
    global rag_system
    try:
        if os.path.exists(r'C:\\Users\\Acer Nitro\\Desktop\\akademi__proje\\yzta_team_forty2\\medvice\\three.json'):
            rag_system = EnhancedRAGSystem(r'C:\\Users\\Acer Nitro\\Desktop\\akademi__proje\\yzta_team_forty2\\medvice\\three.json')
        else:
            abort(500, description="Veri dosyası eksik.")
    except Exception as e:
        abort(500, description=f"RAG sistemi yüklenemedi: {str(e)}")


@chat.route("/ask", methods=["POST"])
def ask_question():
    if rag_system is None:
        return jsonify({"success": False, "message": "RAG sistemi yüklenmedi."}), 500

    data = request.get_json()
    question = data.get("question")
    top_k = data.get("top_k", 5)
    similarity_threshold = data.get("similarity_threshold", 0.3)

    try:
        answer, relevant_docs, similarity_scores, processing_time = rag_system.ask_question(
            question, top_k, similarity_threshold
        )
        return jsonify({
            "question": question,
            "answer": answer,
            "relevant_docs": relevant_docs,
            "similarity_scores": similarity_scores,
            "processing_time": processing_time,
            "success": True
        })
    except Exception as e:
        logger.error(f"Soru cevaplama hatası: {e}")
        return jsonify({
            "question": question,
            "answer": "",
            "relevant_docs": [],
            "similarity_scores": [],
            "processing_time": 0.0,
            "success": False,
            "message": str(e)
        }), 500

@chat.route("/health", methods=["GET"])
def health_check():
    if rag_system is None:
        return jsonify({
            "status": "unhealthy",
            "rag_loaded": False,
            "error": "RAG sistemi yüklenmedi"
        })
    return jsonify({
        "status": "healthy",
        "rag_loaded": True,
        "data_count": len(rag_system.data),
        "model_name": rag_system.model_name,
        "embedding_dimension": rag_system.embedding_dim,
        "faiss_total_vectors": rag_system.faiss_index.ntotal if rag_system.faiss_index else 0,
        "cache_files_exist": {
            "embeddings": os.path.exists(rag_system.embeddings_cache_file),
            "index": os.path.exists(rag_system.index_cache_file),
            "metadata": os.path.exists(rag_system.metadata_cache_file)
        }
    })

@chat.route("/search/<query>", methods=["GET"])
def search_similar_docs(query):
    if rag_system is None:
        return jsonify({"error": "RAG sistemi yüklenmedi"}), 500

    top_k = int(request.args.get("top_k", 5))
    similarity_threshold = float(request.args.get("similarity_threshold", 0.3))

    try:
        results, similarity_scores = rag_system.search_similar(query, top_k, similarity_threshold)
        return jsonify({
            "query": query,
            "results": results,
            "similarity_scores": similarity_scores,
            "count": len(results),
            "parameters": {
                "top_k": top_k,
                "similarity_threshold": similarity_threshold
            }
        })
    except Exception as e:
        return jsonify({"error": f"Arama hatası: {str(e)}"}), 500

@chat.route("/cache", methods=["DELETE"])
def clear_cache():
    if rag_system is None:
        return jsonify({"error": "RAG sistemi yüklenmedi"}), 500

    try:
        cache_files = [
            rag_system.embeddings_cache_file,
            rag_system.index_cache_file,
            rag_system.metadata_cache_file
        ]
        deleted_files = []
        for file_path in cache_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_files.chatend(file_path)
        return jsonify({
            "message": "Cache temizlendi",
            "deleted_files": deleted_files,
            "note": "Yeni embeddings oluşturmak için uygulamayı yeniden başlatın"
        })
    except Exception as e:
        return jsonify({"error": f"Cache temizleme hatası: {str(e)}"}), 500

