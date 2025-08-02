from flask import Flask, request, jsonify, Blueprint,abort
from flask_cors import CORS
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import google.generativeai as genai
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import os
import pickle
from datetime import datetime
import logging
import os
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
        
        processing_time = (datetime.now() - start_time).total_seconds()
        return answer, relevant_docs, similarity_scores, processing_time

# Gemini API'yi yapılandır
genai.configure(api_key="AIzaSyC29VH13ZDaAwIepdefoqWnVzl3ommWqAk")  # Gerçek API key'inizi buraya koyun
model = genai.GenerativeModel('gemini-2.0-flash')

@chat.before_app_request
def load_rag():
    global rag_system
    try:
        if os.path.exists(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\three.json'):
            rag_system = EnhancedRAGSystem(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\three.json')
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
