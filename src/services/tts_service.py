import os
import logging
from io import BytesIO
import re
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class ZarVoiceService:
    def __init__(self):
        # Motor Fonético Oficial da ZAR (Voz Feminina Executiva)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY não foi encontrada. Sintetização desabilitada.")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=api_key)

    async def generate_speech(self, text: str) -> BytesIO:
        if not self.client:
            return None
            
        try:
            # Limpeza cirúrgica de marcação Markdown e visual (Para ZAR não ler asteriscos)
            clean_text = text.replace('*', '').replace('_', '').replace('🧠', '').replace('📦', '').replace('⏳', '').replace('⚖️', '').replace('💎', '').replace('📊', '').replace('⚠️', '')
            clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', clean_text)
            
            truncated_text = clean_text[:4000]
            if not truncated_text.strip():
                return None
                
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice="nova", # Voz Executiva Feminina
                input=truncated_text,
                response_format="opus"
            )
            
            audio_io = BytesIO(response.content)
            audio_io.name = "zar_executive_summary.ogg"
            return audio_io
            
        except Exception as e:
            logger.error(f"Erro vital ao processar motor fonético (OpenAI): {e}")
            return None
