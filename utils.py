import wave
import numpy as np
from datetime import datetime
import os

def save_audio_to_wav(filename, audio_data, sample_rate=16000):
    """
    Guarda audio en formato WAV
    
    Args:
        filename: Nombre del archivo de salida
        audio_data: Array numpy con datos de audio
        sample_rate: Frecuencia de muestreo (default 16kHz)
    """
    audio_array = np.array(audio_data, dtype=np.int16)
    
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16 bits
        wf.setframerate(sample_rate)
        wf.writeframes(audio_array.tobytes())

def get_greeting():
    """
    Retorna un saludo apropiado según la hora del día
    
    Returns:
        str: Saludo personalizado
    """
    hour = datetime.now().hour
    
    if 6 <= hour < 12:
        return "Buenos días, señor"
    elif 12 <= hour < 20:
        return "Buenas tardes, señor"
    else:
        return "Buenas noches, señor"

def get_current_time():
    """Retorna la hora actual en formato hablado"""
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    
    # Formato: "Son las 14:30" o "Es la 1:15"
    if hour == 1 or hour == 13:
        return f"Es la {hour % 12 if hour > 12 else hour}:{minute:02d}"
    else:
        hour_12 = hour % 12 if hour > 12 else hour
        if hour_12 == 0:
            hour_12 = 12
        return f"Son las {hour_12}:{minute:02d}"

def get_current_date():
    """Retorna la fecha actual en formato hablado"""
    now = datetime.now()
    
    # Nombres de días y meses en español
    days = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
    months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
              'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    
    day_name = days[now.weekday()]
    month_name = months[now.month - 1]
    
    return f"Hoy es {day_name}, {now.day} de {month_name} de {now.year}"

def is_local_command(text):
    """
    Verifica si es un comando local (no necesita búsqueda en internet)
    
    Args:
        text: Texto transcrito del usuario
        
    Returns:
        str or None: Respuesta si es comando local, None si necesita búsqueda
    """
    text_lower = text.lower()
    
    # ✅ MEJORADO: Comandos de hora MÁS ESPECÍFICOS
    # Solo si pregunta directamente la hora actual
    hour_patterns = [
        'qué hora es',
        'que hora es',
        'dime la hora',
        'hora actual',
        'cuál es la hora',
        'cual es la hora'
    ]
    
    # Verificar que pregunta la hora Y NO habla de otros conceptos
    if any(pattern in text_lower for pattern in hour_patterns):
        # Excluir si menciona conceptos astronómicos o específicos
        excluded_words = ['mediodía solar', 'mediodia solar', 'salida', 'puesta', 'amanecer', 'atardecer']
        
        if not any(word in text_lower for word in excluded_words):
            return get_current_time()
    
    # Comandos de fecha
    if any(word in text_lower for word in ['fecha', 'día es', 'qué día', 'hoy es']):
        return get_current_date()
    
    # Despedidas
    if any(word in text_lower for word in ['adiós', 'hasta luego', 'chao', 'bye']):
        return "Hasta luego, señor. Que tenga un buen día"
    
    # Agradecimientos
    if any(word in text_lower for word in ['gracias', 'thank you']):
        return "De nada, señor. Para eso estoy"
    
    # Estado de Jarvis
    if any(word in text_lower for word in ['cómo estás', 'qué tal']):
        return "Todos los sistemas funcionando correctamente, señor"
    
    return None

def clean_text_for_speech(text):
    """
    Limpia el texto de Markdown y citas para TTS
    
    Args:
        text: Texto con formato Markdown
        
    Returns:
        str: Texto limpio para hablar
    """
    import re
    
    # Eliminar citas entre corchetes [1], [2][3], [4][9][10]
    text = re.sub(r'\[\d+\](?:\[\d+\])*', '', text)
    
    # Eliminar negritas **texto** → texto
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    
    # Eliminar cursivas *texto* → texto
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    
    # Eliminar guiones bajos __texto__ → texto
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Eliminar enlaces [texto](url) → texto
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Eliminar múltiples espacios
    text = re.sub(r'\s+', ' ', text)
    
    # Eliminar espacios antes de puntuación
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    
    return text.strip()

def clean_temp_files(directory='.', pattern='*.wav'):
    """
    Limpia archivos temporales
    
    Args:
        directory: Directorio donde buscar
        pattern: Patrón de archivos a eliminar
    """
    import glob
    
    for file in glob.glob(os.path.join(directory, pattern)):
        try:
            os.remove(file)
        except Exception as e:
            print(f"⚠️ No se pudo eliminar {file}: {e}")

def format_citations(citations):
    """
    Formatea las citas de Perplexity para mostrarlas
    
    Args:
        citations: Lista de URLs de fuentes
        
    Returns:
        str: Texto formateado con las fuentes
    """
    if not citations:
        return ""
    
    formatted = "\n\n📚 Fuentes consultadas:"
    for i, citation in enumerate(citations[:3], 1):  # Máximo 3 fuentes
        formatted += f"\n  {i}. {citation}"
    
    return formatted
