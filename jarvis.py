#!/usr/bin/env python3
"""
Jarvis - Asistente de voz estilo Iron Man
Raspberry Pi / Windows con APIs de Google y Perplexity
"""

import pvporcupine
import pyaudio
import struct
import threading
import numpy as np
import speech_recognition as sr
import webrtcvad
from google.cloud import texttospeech
import google.generativeai as genai
import requests
import pygame
import os
import sys
import tempfile
import time

from config import Config
from utils import (
    save_audio_to_wav, 
    get_greeting, 
    is_local_command,
    format_citations,
    clean_text_for_speech
)
from user_manager import UserManager

class JarvisAssistant:
    """Asistente de voz Jarvis con detección de wake word y procesamiento de consultas"""
    
    def __init__(self):
        self.user_manager = UserManager()
        print("=" * 60)
        print("🤖 INICIANDO JARVIS")
        print("=" * 60)
        
        # Verificar y validar configuración
        try:
            Config.validate()
            print("✅ Configuración validada")
        except ValueError as e:
            print(str(e))
            sys.exit(1)
        
        # Inicializar componentes
        self._init_wake_word()
        self._init_stt()
        self._init_llm()
        self._init_tts()
        self._init_audio()
        
        # Estado interno
        self.is_recording = False
        self.audio_buffer = []
        self.silence_frames = 0
        #  Estado de sesión
        self.session_greeted = False  # Para saber si ya saludó
        self.last_greeting_time = None
        #  Control de interrupción
        self.is_speaking = False
        self.should_stop_speaking = False
        print("\n" + "=" * 60)
        print("✅ JARVIS LISTO PARA SERVIR")
        print("=" * 60)
        print(f"📢 Di '{Config.WAKE_WORD.upper()}' seguido de tu pregunta")
        print("🛑 Presiona Ctrl+C para salir\n")
    
    def _init_wake_word(self):
        """Inicializa detección de wake word con Porcupine"""
        try:
            self.porcupine = pvporcupine.create(
                access_key=Config.PICOVOICE_KEY,
                keywords=[Config.WAKE_WORD],
                sensitivities=[0.7]  #  0.0-1.0 (más alto = más sensible)
            )
            print(f"✅ Wake word '{Config.WAKE_WORD}' configurado (sensibilidad: 0.7)")
        except Exception as e:
            print(f"❌ Error inicializando Porcupine: {e}")
            print("💡 Verifica tu PICOVOICE_ACCESS_KEY en .env")
            sys.exit(1)

    
    def _init_stt(self):
        """Inicializa Speech-to-Text con Google"""
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        print("✅ Google Speech-to-Text configurado")
    
    def _init_llm(self):
        """Inicializa Gemini LLM (opcional, se usa Perplexity principalmente)"""
        try:
            genai.configure(api_key=Config.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            print("✅ Gemini LLM configurado")
        except Exception as e:
            print(f"⚠️ Gemini no disponible: {e}")
            self.model = None
    
    def _init_tts(self):
        """Inicializa Text-to-Speech con Google"""
        try:
            # Configurar credenciales
            if Config.GOOGLE_CREDENTIALS:
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = Config.GOOGLE_CREDENTIALS
            
            self.tts_client = texttospeech.TextToSpeechClient()
            
            self.voice = texttospeech.VoiceSelectionParams(
                language_code=Config.LANGUAGE,
                name=Config.VOICE_NAME,
                ssml_gender=texttospeech.SsmlVoiceGender.MALE
            )
            
            self.audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=Config.TTS_SPEAKING_RATE,
                pitch=Config.TTS_PITCH
            )
            print("✅ Google Text-to-Speech configurado")
        except Exception as e:
            print(f"❌ Error inicializando TTS: {e}")
            print("💡 Verifica google-credentials.json")
            sys.exit(1)
    
    def _init_audio(self):
        """Inicializa sistema de audio (PyAudio y pygame)"""
        try:
            self.pa = pyaudio.PyAudio()
            pygame.mixer.init()
            self.vad = webrtcvad.Vad(Config.VAD_AGGRESSIVENESS)
            print("✅ Sistema de audio configurado")
        except Exception as e:
            print(f"❌ Error inicializando audio: {e}")
            print("💡 Verifica que tu micrófono esté conectado")
            sys.exit(1)
    def smart_greeting(self):
        """
        Genera un saludo inteligente según el contexto y usuario
        
        Returns:
            str: Saludo apropiado
        """
        import datetime
        
        #  Obtener nombre de usuario
        user_name = self.user_manager.get_current_user()
        user_suffix = f" {user_name}" if user_name else ""
        
        # Si nunca ha saludado en esta sesión
        if not self.session_greeted:
            self.session_greeted = True
            self.last_greeting_time = datetime.datetime.now()
            
            # Saludo completo la primera vez
            hour = datetime.datetime.now().hour
            if 6 <= hour < 12:
                return f"Buenos días, señor{user_suffix}"
            elif 12 <= hour < 20:
                return f"Buenas tardes, señor{user_suffix}"
            else:
                return f"Buenas noches, señor{user_suffix}"
        
        # Si ya saludó hace menos de 5 minutos
        if self.last_greeting_time:
            time_diff = (datetime.datetime.now() - self.last_greeting_time).seconds
            if time_diff < 300:
                return f"Señor{user_suffix}"
        
        # Si pasaron más de 5 minutos
        return f"Señor{user_suffix}"


    def listen_for_wake_word_and_capture(self):
        """
        Escucha el wake word Y captura automáticamente lo que viene después
        """
        from collections import deque
        
        audio_stream = self.pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )
        
        print(f"\n🎤 Escuchando '{Config.WAKE_WORD}'...")
        
        buffer_seconds = 2
        buffer_size = int(buffer_seconds * self.porcupine.sample_rate / self.porcupine.frame_length)
        audio_buffer = deque(maxlen=buffer_size)
        
        try:
            while True:
                pcm = audio_stream.read(
                    self.porcupine.frame_length, 
                    exception_on_overflow=False
                )
                pcm_unpacked = struct.unpack_from(
                    "h" * self.porcupine.frame_length, 
                    pcm
                )
                
                audio_buffer.append(pcm)
                keyword_index = self.porcupine.process(pcm_unpacked)
                
                if keyword_index >= 0:
                    print(f"✅ '{Config.WAKE_WORD.upper()}' detectado!")
                    self.play_confirmation_sound()
                    print("🎧 Capturando pregunta...")
                    
                    post_wake_frames = []
                    speech_detected = False
                    
                    # Usar tiempo real 
                    max_wait_time = 5  # Máximo 5 segundos de espera
                    silence_duration = 2  # 2 segundos de silencio para terminar
                    
                    last_speech_time = time.time()
                    start_time = time.time()
                    
                    vad_stream = self.pa.open(
                        rate=16000,
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=480
                    )
                    
                    while True:
                        frame = vad_stream.read(480, exception_on_overflow=False)
                        post_wake_frames.append(frame)
                        
                        # Detectar si hay voz
                        try:
                            is_speech = self.vad.is_speech(frame, 16000)
                        except:
                            is_speech = False
                        
                        if is_speech:
                            speech_detected = True
                            last_speech_time = time.time()
                        
                        # Tiempo transcurrido desde última voz
                        silence_time = time.time() - last_speech_time
                        total_time = time.time() - start_time
                        
                        # Si detectó voz y luego 2 segundos de silencio, terminar
                        if speech_detected and silence_time >= silence_duration:
                            print("🛑 Pregunta capturada (2 segundos de silencio)")
                            break
                        
                        # Si pasaron 5 segundos sin detectar voz, asumir que no dijo nada
                        if not speech_detected and total_time >= max_wait_time:
                            print("⏸️ No se detectó pregunta continua")
                            break
                        
                        # Timeout máximo de 10 segundos total
                        if total_time >= 10:
                            print("⏱️ Tiempo máximo alcanzado")
                            break
                    
                    vad_stream.close()
                    audio_stream.close()
                    
                    if not speech_detected:
                        return True, None
                    
                    audio_data = b''.join(post_wake_frames)
                    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                    temp_filename = temp_file.name
                    temp_file.close()
                    
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    save_audio_to_wav(temp_filename, audio_array, 16000)
                    
                    return True, temp_filename
                    
        except KeyboardInterrupt:
            print("\n\n👋 Apagando Jarvis...")
            audio_stream.close()
            return False, None
        
    def capture_question(self):
        """
        Captura la pregunta del usuario después del wake word usando VAD
        """
        audio_stream = self.pa.open(
            rate=Config.SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=480
        )
        
        print("🎧 Escuchando tu pregunta...")
        
        frames = []
        speech_started = False
        
        # ✅ NUEVO: Usar tiempo real
        silence_duration = 2.0  # 2 segundos de silencio
        max_recording_time = 15  # Máximo 10 segundos
        min_speech_duration = 0.3  # Mínimo 0.3 segundos de voz
        
        last_speech_time = time.time()
        start_time = time.time()
        speech_start_time = None
        
        try:
            while True:
                frame = audio_stream.read(480, exception_on_overflow=False)
                
                # Detectar si hay voz
                try:
                    is_speech = self.vad.is_speech(frame, Config.SAMPLE_RATE)
                except:
                    is_speech = False
                
                if is_speech:
                    if not speech_started:
                        speech_started = True
                        speech_start_time = time.time()
                    last_speech_time = time.time()
                    frames.append(frame)
                elif speech_started:
                    frames.append(frame)
                
                # Calcular tiempos
                current_time = time.time()
                silence_time = current_time - last_speech_time
                total_time = current_time - start_time
                
                # Si hay suficiente silencio después de hablar, terminar
                if speech_started:
                    speech_duration = current_time - speech_start_time
                    
                    if silence_time >= silence_duration and speech_duration >= min_speech_duration:
                        print("🛑 Pregunta capturada (2 segundos de silencio)")
                        break
                
                # Timeout máximo
                if total_time >= max_recording_time:
                    print("⏱️ Tiempo máximo alcanzado")
                    break
            
            audio_stream.close()
            
            # Verificar que hubo suficiente voz
            if not speech_started or (speech_start_time and (time.time() - speech_start_time) < min_speech_duration):
                print("⚠️ No se detectó suficiente voz")
                return None
            
            # Convertir frames a audio
            audio_data = b''.join(frames)
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_filename = temp_file.name
            temp_file.close()
            
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            save_audio_to_wav(temp_filename, audio_array, Config.SAMPLE_RATE)
            
            return temp_filename
            
        except Exception as e:
            print(f"❌ Error capturando audio: {e}")
            audio_stream.close()
            return None



    def classify_intent(self, text):
        """
        Clasifica la intención del texto para decidir si buscar o no
        """
        text_lower = text.lower()
        words = text_lower.split()
        # Detectar comando de registro de usuario de forma más específica
        # Solo si la frase es CORTA y directa
        if len(words) <= 8:  # Máximo 5 palabras
            if 'soy' in text_lower or 'me llamo' in text_lower or 'mi nombre es' in text_lower:
                import re
                
                patterns = [
                    r'^soy\s+([a-záéíóúñ]+)$',  # "soy Maxi"
                    r'^me llamo\s+([a-záéíóúñ]+)$',  # "me llamo Maxi"
                    r'^mi nombre es\s+([a-záéíóúñ]+)$'  # "mi nombre es Maxi"
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text_lower.strip())
                    if match:
                        name = match.group(1).capitalize()
                        return 'register_user', name
        
        # Detectar preguntas sobre identidad propia
        if len(words) <= 6:  # Solo frases cortas
            identity_patterns = [
                'cómo me llamo', 'como me llamo',
                'cuál es mi nombre', 'cual es mi nombre',
                'quién soy yo', 'quien soy yo',  
                'quién soy', 'quien soy',  # Mantener pero solo en frases cortas
                'cómo me dices', 'como me dices',
                'mi nombre'
            ]
            
            # Verificar que el patrón sea la pregunta principal, no parte de algo más grande
            if any(text_lower == pattern or text_lower.startswith(pattern + ' ') for pattern in identity_patterns):
                user_name = self.user_manager.get_current_user()
                
                if user_name:
                    return 'identity_query', f"Su nombre es {user_name}, señor"
                else:
                    return 'identity_query', "Disculpe, aún no me ha dicho su nombre. Puede decirme 'me llamo [su nombre]'"
        
        # COMANDOS DE PARADA
        stop_patterns = [
            'para', 'detente', 'cállate', 'basta', 'silencio', 'stop', 'calla',
            'nada', 'olvida', 'déjalo', 'vale', 'ok', 'está bien',
            'no hace falta', 'no necesito', 'no importa', 'no pasa nada',
            'ya está', 'suficiente', 'no más', 'no sigas', 'no continues'
        ]
        
        if any(pattern in text_lower for pattern in stop_patterns):
            return 'stop', 'Entendido, señor'
        
        # SALUDOS
        greeting_patterns = [
            'hola', 'buenos días', 'buenas tardes', 'buenas noches', 
            'qué tal', 'cómo estás', 'hey', 'buenas'
        ]
        
        if any(pattern in text_lower for pattern in greeting_patterns):
            greeting = self.smart_greeting()
            return 'greeting', f"{greeting}. ¿En qué puedo ayudarle?"
        
        # COMANDOS LOCALES (hora, fecha, etc.)
        local_response = is_local_command(text)
        if local_response:
            return 'local', local_response
        
        # AFIRMACIONES/NEGACIONES SIMPLES
        simple_responses = [
            'sí', 'si', 'no', 'claro', 'por supuesto', 'evidentemente',
            'tal vez', 'quizás', 'puede ser'
        ]
        
        if len(words) <= 2 and any(word in simple_responses for word in words):
            return 'stop', 'Entendido, señor'
        
        # DETECTAR PREGUNTAS REALES
        question_words = [
            'qué', 'que', 'quién', 'quien', 'cuál', 'cual', 'cuáles', 'cuales',
            'cómo', 'como', 'cuándo', 'cuando', 'cuánto', 'cuanto', 'cuánta', 'cuanta',
            'dónde', 'donde', 'por qué', 'por que', 'para qué', 'para que'
        ]
        
        search_verbs = [
            'busca', 'buscar', 'dime', 'cuéntame', 'explícame', 'háblame',
            'necesito saber', 'quiero saber', 'investiga', 'averigua', 'quiero que'
        ]
        
        has_question_word = any(word in text_lower for word in question_words)
        has_search_verb = any(verb in text_lower for verb in search_verbs)
        
        if has_question_word or has_search_verb:
            return 'question', None
        
        # RESPUESTAS SIMPLES
        if len(words) <= 4:
            return 'stop', 'Entendido, señor'
        
        # POR DEFECTO: pregunta
        return 'question', None

    
    def transcribe(self, audio_file, delete_after=True):
        """
        Transcribe audio a texto usando Google Speech-to-Text
        
        Args:
            audio_file: Path del archivo de audio
            delete_after: Si eliminar el archivo después de transcribir
            
        Returns:
            str: Texto transcrito, o None si falla
        """
        try:
            with sr.AudioFile(audio_file) as source:
                audio = self.recognizer.record(source)
            
            text = self.recognizer.recognize_google(
                audio, 
                language=Config.LANGUAGE
            )
            print(f"📝 Transcripción: '{text}'")
            
            #  Solo eliminar si se indica
            if delete_after:
                try:
                    os.remove(audio_file)
                except:
                    pass
            
            return text
            
        except sr.UnknownValueError:
            print("⚠️ No pude entender el audio")
            return None
        except sr.RequestError as e:
            print(f"❌ Error en Google STT: {e}")
            return None
        except Exception as e:
            print(f"❌ Error en transcripción: {e}")
            return None

    
    def search_perplexity(self, query):
        """
        Busca información usando Perplexity API
        
        Args:
            query: Pregunta del usuario
            
        Returns:
            tuple: (respuesta, citations) o (None, []) si falla
        """
        url = "https://api.perplexity.ai/chat/completions"
        
        payload = {
            "model": "sonar",  # Modelo más pequeño y estable
            "messages": [
                {
                    "role": "system",
                    "content": Config.SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            "temperature": Config.PERPLEXITY_TEMPERATURE,
            "max_tokens": Config.PERPLEXITY_MAX_TOKENS
        }
        
        headers = {
            "Authorization": f"Bearer {Config.PERPLEXITY_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            print("🔍 Buscando información...")
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                timeout=15
            )
            
            # Debug: mostrar respuesta si hay error
            if response.status_code != 200:
                print(f"❌ Status code: {response.status_code}")
                print(f"❌ Response: {response.text}")
            
            response.raise_for_status()
            
            result = response.json()
            answer = result['choices'][0]['message']['content']
            citations = result.get('citations', [])
            
            print("💡 Respuesta obtenida")
            return answer, citations
            
        except requests.exceptions.Timeout:
            print("⏱️ Timeout en Perplexity")
            return "Disculpe señor, la búsqueda está tardando demasiado", []
        except requests.exceptions.RequestException as e:
            print(f"❌ Error en Perplexity API: {e}")
            return "Lo siento señor, no puedo acceder a la búsqueda en este momento", []
        except Exception as e:
            print(f"❌ Error procesando respuesta: {e}")
            return "Lo siento señor, hubo un error al procesar la respuesta", []
    
    def speak(self, text, interruptible=True):
        """
        Convierte texto a voz y lo reproduce
        
        Args:
            text: Texto a sintetizar
            interruptible: Si se puede interrumpir con "Jarvis para"
        """
        try:
            # Limpiar texto
            clean_text = clean_text_for_speech(text)
            
            print(f"\n🗣️  Jarvis: {clean_text}\n")
            
            synthesis_input = texttospeech.SynthesisInput(text=clean_text)
            
            response = self.tts_client.synthesize_speech(
                input=synthesis_input,
                voice=self.voice,
                audio_config=self.audio_config
            )
            
            # Guardar audio
            temp_filename = "jarvis_temp_audio.mp3"
            
            with open(temp_filename, 'wb') as out:
                out.write(response.audio_content)
            
            time.sleep(0.1)
            
            #  Iniciar escucha de interrupción en paralelo
            self.is_speaking = True
            self.should_stop_speaking = False
            
            if interruptible:
                interrupt_thread = threading.Thread(target=self.listen_for_interruption, daemon=True)
                interrupt_thread.start()
            
            # Reproducir
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            
            # Esperar mientras reproduce (o hasta interrupción)
            while pygame.mixer.music.get_busy():
                if self.should_stop_speaking:
                    pygame.mixer.music.stop()
                    print("⏹️ Reproducción detenida")
                    break
                pygame.time.Clock().tick(10)
            
            # Finalizar
            self.is_speaking = False
            pygame.mixer.music.unload()
            
            time.sleep(0.1)
            
            try:
                os.remove(temp_filename)
            except:
                pass
            
            # Si fue interrumpido, confirmar
            if self.should_stop_speaking:
                # No usar speak() aquí para evitar recursión
                print("✅ Detenido")
            
        except Exception as e:
            self.is_speaking = False
            print(f"❌ Error en TTS: {e}")
            import traceback
            traceback.print_exc()


    
    def process_query(self, query):
        """
        Procesa la consulta del usuario
        
        Args:
            query: Pregunta transcrita
            
        Returns:
            str: Respuesta a devolver
        """
        # Verificar comandos locales primero (más rápido)
        local_response = is_local_command(query)
        if local_response:
            print(f"⚡ Comando local detectado")
            return local_response
        
        # Si no es comando local, buscar en Perplexity
        answer, citations = self.search_perplexity(query)
        
        # Mostrar fuentes si están disponibles
        if citations:
            print(format_citations(citations))
        
        return answer
    def play_confirmation_sound(self):
        """Reproduce confirmación al detectar wake word"""
        try:
            # Opción simple: solo decir "Señor" sin saludar
            confirmation_text = "¿Señor?"
            
            synthesis_input = texttospeech.SynthesisInput(text=confirmation_text)
            
            response = self.tts_client.synthesize_speech(
                input=synthesis_input,
                voice=self.voice,
                audio_config=self.audio_config
            )
            
            temp_file = "confirmation_audio.mp3"
            with open(temp_file, 'wb') as out:
                out.write(response.audio_content)
            
            time.sleep(0.05)
            
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            
            pygame.mixer.music.unload()
            
            try:
                os.remove(temp_file)
            except:
                pass
                
        except Exception as e:
            print(f"⚠️ Error en confirmación: {e}")

    def listen_for_interruption(self):
        """
        Escucha en segundo plano mientras habla para detectar el wake word "Jarvis" y detener la reproducción inmediatamente.
        """
        try:
            stream = self.pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            
            print("🎧 [DEBUG] Thread de interrupción iniciado")
            
            while self.is_speaking and not self.should_stop_speaking:
                pcm = stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                pcm_unpacked = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                
                keyword_index = self.porcupine.process(pcm_unpacked)
                
                if keyword_index >= 0:
                    print("\n⏸️ Wake word 'Jarvis' detectado durante reproducción, deteniendo...")
                    self.should_stop_speaking = True
                    break
            
            stream.close()
            print("🔇 [DEBUG] Thread de interrupción terminado")
            
        except Exception as e:
            print(f"⚠️ Error en detección de interrupción: {e}")

    def handle_interruption(self):
        """
        Maneja el flujo cuando se interrumpe la reproducción con 'Jarvis'
        """
        try:
            # Resetear flag de interrupción
            self.should_stop_speaking = False
            
            # Preguntar qué necesita
            print("\n💬 Jarvis fue interrumpido, esperando nueva instrucción...")
            self.speak("¿Señor?", interruptible=False)
            
            # Capturar nueva pregunta
            audio_file = self.capture_question()
            
            if not audio_file:
                self.speak("Entendido, señor", interruptible=False)
                return
            
            # Transcribir
            query = self.transcribe(audio_file)
            
            if not query:
                self.speak("Disculpe, no le he entendido", interruptible=False)
                return
            
            #  Clasificar intención antes de buscar
            intent_type, response = self.classify_intent(query)
            
            print(f"🧠 [DEBUG] Intención detectada: {intent_type}")
            
            if intent_type == 'stop':
                # Comando de parada → responder directamente
                self.speak(response, interruptible=False)
                return
            
            elif intent_type == 'greeting':
                # Saludo → responder y esperar otra pregunta
                self.speak(response, interruptible=False)
                
                # Esperar nueva pregunta
                audio_file = self.capture_question()
                if audio_file:
                    query = self.transcribe(audio_file)
                    if query:
                        # Recursión con la nueva pregunta
                        intent_type, response = self.classify_intent(query)
                        
                        if intent_type in ['stop', 'greeting', 'local']:
                            self.speak(response, interruptible=False)
                        else:
                            # Es pregunta real → procesar
                            answer = self.search_perplexity(query)
                            if answer[0]:
                                prefix = self.smart_greeting()
                                full_answer = f"{prefix}. {answer[0]}"
                                self.speak(full_answer, interruptible=True)
                                
                                if self.should_stop_speaking:
                                    self.handle_interruption()
                return
            
            elif intent_type == 'local':
                # Comando local (hora, fecha) → responder directamente
                prefix = self.smart_greeting()
                full_answer = f"{prefix}, {response.lower()}"
                self.speak(full_answer, interruptible=False)
                return
            
            elif intent_type == 'question':
                # Pregunta real → buscar en web
                answer, citations = self.search_perplexity(query)
                
                if answer:
                    prefix = self.smart_greeting()
                    full_answer = f"{prefix}. {answer}"
                    self.speak(full_answer, interruptible=True)
                    
                    # Si vuelven a interrumpir, recursión
                    if self.should_stop_speaking:
                        self.handle_interruption()
                else:
                    self.speak("Lo siento señor, no he podido obtener una respuesta", interruptible=False)
                return
                
        except Exception as e:
            print(f"❌ Error manejando interrupción: {e}")
            import traceback
            traceback.print_exc()
            self.speak("Disculpe señor, hubo un error", interruptible=False)



    def run(self):
        """Loop principal del asistente"""
        try:
            while True:
                # 1. Esperar wake word Y capturar audio simultáneamente
                detected, audio_file = self.listen_for_wake_word_and_capture()
                
                if not detected:
                    break  # Ctrl+C presionado
                
                # 2. Si NO capturó audio después del wake word, saludar y esperar
                if not audio_file:
                    greeting = self.smart_greeting() + ". Dígame"
                    self.speak(greeting, interruptible=False)
                    
                    audio_file = self.capture_question()
                    
                    if not audio_file:
                        self.speak("No he recibido ninguna pregunta, señor", interruptible=False)
                        continue
                
                # 3. Transcribir con reintentos
                max_retries = 2
                retry_count = 0
                query = None
                
                while retry_count < max_retries and not query:
                    # NO eliminar el archivo aún (delete_after=False)
                    query = self.transcribe(audio_file, delete_after=False)
                    
                    if not query:
                        retry_count += 1
                        if retry_count < max_retries:
                            self.speak("Disculpe, no le he entendido bien. Por favor, repita", interruptible=False)
                            
                            # Eliminar el archivo anterior
                            try:
                                os.remove(audio_file)
                            except:
                                pass
                            
                            # Capturar nueva pregunta
                            audio_file = self.capture_question()
                            
                            if not audio_file:
                                print("⏸️ Usuario no respondió, volviendo a esperar wake word")
                                break
                        else:
                            self.speak("Lo siento señor, sigo sin entenderle", interruptible=False)
                            # Eliminar archivo
                            try:
                                os.remove(audio_file)
                            except:
                                pass
                            break
                
                if not query:
                    continue
                if audio_file and os.path.exists(audio_file):
                    user_name, confidence = self.user_manager.identify_user(audio_file, threshold=50)
                    
                    if user_name:
                        print(f"👤 Usuario identificado: {user_name} ({confidence:.1f}%)")
                    else:
                        print(f"👤 Usuario no identificado")
                
                # Clasificar intención
                intent_type, response = self.classify_intent(query)
                
                print(f"🧠 [DEBUG] Intención detectada: {intent_type}")
                
                # Manejar registro de usuario (el archivo AÚN EXISTE)
                if intent_type == 'register_user':
                    name = response
                    
                    try:
                        if self.user_manager.register_user(name, audio_file):
                            greeting = self.smart_greeting()
                            self.speak(f"Encantado de conocerle, {greeting}", interruptible=False)
                        else:
                            self.speak("Disculpe señor, hubo un error al registrarle", interruptible=False)
                    
                    except Exception as e:
                        print(f"❌ Error registrando usuario: {e}")
                        self.speak("Disculpe señor, hubo un error al registrarle", interruptible=False)
                    
                    finally:
                        # Limpiar archivo
                        try:
                            os.remove(audio_file)
                        except:
                            pass
                    
                    continue
                
                # Para todos los demás casos, eliminar el archivo AHORA
                try:
                    os.remove(audio_file)
                except:
                    pass
                
                if intent_type == 'identity_query':
                    prefix = self.smart_greeting()
                    full_answer = f"{prefix}. {response}"
                    
                    try:
                        os.remove(audio_file)
                    except:
                        pass
                    
                    self.speak(full_answer, interruptible=False)
                    continue
                # 4. Procesar según el tipo de intención
                if intent_type == 'stop':
                    self.speak(response, interruptible=False)
                    continue
                
                elif intent_type == 'greeting':
                    self.speak(response, interruptible=False)
                    
                    audio_file = self.capture_question()
                    if audio_file:
                        query = self.transcribe(audio_file)  # Aquí sí eliminar (default)
                        if query:
                            intent_type, response = self.classify_intent(query)
                            
                            if intent_type in ['stop', 'greeting']:
                                self.speak(response, interruptible=False)
                            elif intent_type == 'local':
                                prefix = self.smart_greeting()
                                full_answer = f"{prefix}, {response.lower()}"
                                self.speak(full_answer, interruptible=False)
                            else:  # question
                                answer, citations = self.search_perplexity(query)
                                if answer:
                                    prefix = self.smart_greeting()
                                    full_answer = f"{prefix}. {answer}"
                                    self.speak(full_answer, interruptible=True)
                                    
                                    if self.should_stop_speaking:
                                        self.handle_interruption()
                    continue
                
                elif intent_type == 'local':
                    prefix = self.smart_greeting()
                    
                    if any(word in query.lower() for word in ['hora', 'horas', 'qué hora']):
                        full_answer = f"{prefix}, {response.lower()}"
                    elif any(word in query.lower() for word in ['fecha', 'día', 'qué día']):
                        full_answer = f"{prefix}, {response.lower()}"
                    else:
                        full_answer = f"{prefix}. {response}"
                    
                    self.speak(full_answer, interruptible=False)
                
                elif intent_type == 'question':
                    answer, citations = self.search_perplexity(query)
                    
                    if answer:
                        prefix = self.smart_greeting()
                        full_answer = f"{prefix}. {answer}"
                        
                        self.speak(full_answer, interruptible=True)
                        
                        if self.should_stop_speaking:
                            self.handle_interruption()
                    else:
                        self.speak("Lo siento señor, no he podido obtener una respuesta", interruptible=False)
                
                print("\n" + "-" * 60 + "\n")
                
        except KeyboardInterrupt:
            print("\n\n👋 Apagando Jarvis...")
        finally:
            self.cleanup()

    def cleanup(self):
        """Libera recursos al cerrar"""
        print("\n🧹 Liberando recursos...")
        
        if hasattr(self, 'porcupine'):
            self.porcupine.delete()
        
        if hasattr(self, 'pa'):
            self.pa.terminate()
        
        pygame.mixer.quit()
        
        print("✅ Recursos liberados")
        print("\n" + "=" * 60)
        print("👋 Hasta luego, señor")
        print("=" * 60 + "\n")

def main():
    """Punto de entrada principal"""
    try:
        jarvis = JarvisAssistant()
        jarvis.run()
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
