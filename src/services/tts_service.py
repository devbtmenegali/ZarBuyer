import os
import logging
from io import BytesIO
import re
import asyncio
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class ZarVoiceService:
    def __init__(self):
        # Inicializa a Carga Analytica da Voz Neural do Google (Gemini Pro)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY não foi encontrada no ambiente. Sintetização auditiva desabilitada.")
            self.client = None
        else:
            self.client = genai.Client(api_key=api_key)

    async def generate_speech(self, text: str) -> BytesIO:
        """
        Recebe a carga de texto processada pela Inteligencia Artificial ZAR,
        Muta formatações e aciona a síntese de tom de voz feminino nativa do Gemini 2.5.
        """
        if not self.client:
            return None
            
        try:
            # Remoção tática de marcação Markdown e Emojis para o Robô não pronunciar bizarramente
            clean_text = text.replace('*', '').replace('_', '').replace('🧠', '').replace('📦', '').replace('⏳', '').replace('⚖️', '')
            clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', clean_text)
            
            truncated_text = clean_text[:4000]
            if not truncated_text.strip():
                return None
                
            # O serviço de API Python do Gemini é majoritariamente Síncrono no SDK novo.
            # Vamos rodá-lo na ThreadPool assíncrona para não travar o bot do Telegram:
            def _sync_gemini_tts():
                # O comando ideal para o modelo Gemini 2.0 falar:
                prompt_speak = f"Por favor, leia exatamente o texto a seguir com tom executivo, pragmático e direto em português brasileiro:\n\n{truncated_text}"
                
                response = self.client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt_speak,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_modalities=["AUDIO"], # Força o retorno multimodal de áudio
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name="Aoede" # Voz Feminina madura nativa do Gemini
                                )
                            )
                        )
                    )
                )
                
                # Busca o primeiro segmento de dados inline que seja Áudio (formato OGG ou WAV)
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                            return part.inline_data.data
                return None

            audio_bytes = await asyncio.to_thread(_sync_gemini_tts)
            
            if audio_bytes:
                audio_io = BytesIO(audio_bytes)
                audio_io.name = "zar_executive_summary.ogg"
                return audio_io
            return None
            
        except Exception as e:
            logger.error(f"Erro vital ao processar motor fonético nativo do Gemini: {e}")
            return None
