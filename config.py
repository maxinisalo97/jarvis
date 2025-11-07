import os
from pathlib import Path
from dotenv import load_dotenv

# Obtener directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent

# Cargar variables de entorno desde .env
load_dotenv()

class Config:
    """Configuración centralizada del proyecto Jarvis"""
    
    # ==================== API KEYS ====================
    PICOVOICE_KEY = os.getenv('PICOVOICE_ACCESS_KEY')
    PERPLEXITY_KEY = os.getenv('PERPLEXITY_API_KEY')
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    
    # Google Credentials - Convertir a ruta absoluta si es relativa
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if credentials_path:
        if not os.path.isabs(credentials_path):
            # Ruta relativa → convertir a absoluta
            GOOGLE_CREDENTIALS = str(BASE_DIR / credentials_path)
        else:
            # Ya es absoluta
            GOOGLE_CREDENTIALS = credentials_path
    else:
        GOOGLE_CREDENTIALS = None
    
    # ==================== WAKE WORD ====================
    WAKE_WORD = os.getenv('WAKE_WORD', 'jarvis')
    
    # ==================== AUDIO CONFIG ====================
    SAMPLE_RATE = 16000  # Hz (16kHz es estándar para voz)
    CHUNK_SIZE = 512     # Tamaño de frame para Porcupine
    
    # ==================== SPEECH-TO-TEXT ====================
    LANGUAGE = os.getenv('LANGUAGE', 'es-ES')
    
    # ==================== TEXT-TO-SPEECH ====================
    VOICE_NAME = os.getenv('VOICE_NAME', 'es-ES-Neural2-G')
    TTS_SPEAKING_RATE = 1.0  # Velocidad (0.25 - 4.0)
    TTS_PITCH = 0.0          # Tono (-20.0 - 20.0)
    
    # ==================== VAD (Voice Activity Detection) ====================
    VAD_AGGRESSIVENESS = 1   # 0-3 (3 = más agresivo filtrando ruido)
    
    # ==================== RECORDING CONFIG ====================
    SILENCE_DURATION = 1.0      # Segundos de silencio para terminar grabación
    MAX_RECORDING_TIME = 15     # Máximo tiempo de grabación en segundos
    SILENCE_THRESHOLD = 500     # Umbral de audio (ajustar según micrófono)
    
    # ==================== PERPLEXITY CONFIG ====================
    PERPLEXITY_MODEL = "sonar"
    PERPLEXITY_TEMPERATURE = 0.2
    PERPLEXITY_MAX_TOKENS = 250
    
    # ==================== SYSTEM PROMPTS ====================
    SYSTEM_PROMPT = """Eres Jarvis, el asistente personal de Iron Man. 
Responde de forma concisa, clara y útil, como si hablaras con Tony Stark (no de forma literal). 
Usa un tono formal pero cercano. Máximo 3-4 frases por respuesta."""
    
    @classmethod
    def validate(cls):
        """Valida que todas las credenciales necesarias estén configuradas"""
        missing = []
        
        if not cls.PICOVOICE_KEY:
            missing.append("PICOVOICE_ACCESS_KEY")
        
        if not cls.GOOGLE_API_KEY:
            missing.append("GOOGLE_API_KEY")
        
        if not cls.PERPLEXITY_KEY:
            missing.append("PERPLEXITY_API_KEY")
        
        if not cls.GOOGLE_CREDENTIALS:
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")
        elif not os.path.exists(cls.GOOGLE_CREDENTIALS):
            missing.append(f"Archivo no encontrado: {cls.GOOGLE_CREDENTIALS}")
        
        if missing:
            raise ValueError(
                f"❌ Faltan las siguientes configuraciones en .env:\n" + 
                "\n".join(f"  - {key}" for key in missing)
            )
        
        return True
