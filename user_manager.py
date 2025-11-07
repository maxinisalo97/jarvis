"""
Sistema de reconocimiento y gestión de usuarios por voz
"""

import os
import json
import numpy as np
import hashlib
from pathlib import Path


class UserManager:
    """Gestiona el registro y reconocimiento de usuarios por características de voz"""
    
    def __init__(self, data_file='users_data.json'):
        self.data_file = data_file
        self.users = {}
        self.current_user = None
        self.load_users()
    
    def load_users(self):
        """Carga usuarios guardados desde archivo"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.users = json.load(f)
                print(f"✅ {len(self.users)} usuarios cargados")
            except Exception as e:
                print(f"⚠️ Error cargando usuarios: {e}")
                self.users = {}
        else:
            print("📝 Creando nuevo archivo de usuarios")
            self.users = {}
    
    def save_users(self):
        """Guarda usuarios en archivo"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            print(f"💾 Usuarios guardados")
        except Exception as e:
            print(f"❌ Error guardando usuarios: {e}")
    
    def extract_voice_features(self, audio_file):
        """
        Extrae características simples de voz del archivo de audio
        (Versión simplificada sin ML pesado)
        
        Args:
            audio_file: Path del archivo WAV
            
        Returns:
            dict: Características de voz
        """
        try:
            import wave
            
            with wave.open(audio_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16)
            
            # Características básicas (pitch, energía, etc.)
            features = {
                'mean': float(np.mean(audio_data)),
                'std': float(np.std(audio_data)),
                'max': float(np.max(audio_data)),
                'min': float(np.min(audio_data)),
                'energy': float(np.sum(audio_data**2) / len(audio_data))
            }
            
            return features
            
        except Exception as e:
            print(f"⚠️ Error extrayendo características: {e}")
            return None
    
    def calculate_similarity(self, features1, features2):
        """
        Calcula similitud entre dos conjuntos de características
        
        Returns:
            float: Puntuación de similitud (0-100)
        """
        if not features1 or not features2:
            return 0
        
        try:
            # Calcular diferencias normalizadas
            diffs = []
            for key in features1.keys():
                if key in features2:
                    val1 = features1[key]
                    val2 = features2[key]
                    
                    # Normalizar diferencia
                    if val1 == 0 and val2 == 0:
                        diff = 0
                    else:
                        diff = abs(val1 - val2) / (abs(val1) + abs(val2) + 1e-10)
                    
                    diffs.append(diff)
            
            # Similitud inversa (1 - diferencia promedio)
            avg_diff = np.mean(diffs)
            similarity = (1 - avg_diff) * 100
            
            return max(0, min(100, similarity))
            
        except Exception as e:
            print(f"⚠️ Error calculando similitud: {e}")
            return 0
    
    def register_user(self, name, audio_file):
        """
        Registra o actualiza un usuario
        
        Args:
            name: Nombre del usuario
            audio_file: Path del archivo de audio de muestra
            
        Returns:
            bool: True si el registro fue exitoso
        """
        print(f"👤 Registrando usuario: {name}")
        
        features = self.extract_voice_features(audio_file)
        
        if not features:
            return False
        
        self.users[name] = {
            'name': name,
            'features': features,
            'registered_count': self.users.get(name, {}).get('registered_count', 0) + 1
        }
        
        self.save_users()
        self.current_user = name
        
        print(f"✅ Usuario '{name}' registrado exitosamente")
        return True
    
    def identify_user(self, audio_file, threshold=60):
        """
        Identifica el usuario basándose en las características de voz
        
        Args:
            audio_file: Path del archivo de audio
            threshold: Umbral mínimo de similitud (0-100)
            
        Returns:
            tuple: (nombre_usuario, confianza) o (None, 0) si no reconoce
        """
        if not self.users:
            return None, 0
        
        features = self.extract_voice_features(audio_file)
        
        if not features:
            return None, 0
        
        best_match = None
        best_score = 0
        
        for user_name, user_data in self.users.items():
            similarity = self.calculate_similarity(features, user_data['features'])
            
            if similarity > best_score:
                best_score = similarity
                best_match = user_name
        
        print(f"🔍 [DEBUG] Mejor coincidencia: {best_match} ({best_score:.1f}%)")
        
        if best_score >= threshold:
            self.current_user = best_match
            return best_match, best_score
        else:
            self.current_user = None
            return None, 0
    
    def get_current_user(self):
        """Retorna el nombre del usuario actual o None"""
        return self.current_user
    
    def get_greeting_for_user(self, user_name=None):
        """
        Genera saludo personalizado para el usuario
        
        Args:
            user_name: Nombre del usuario (None para actual)
            
        Returns:
            str: Saludo personalizado
        """
        name = user_name or self.current_user
        
        if name:
            return f"señor {name}"
        else:
            return "señor"
