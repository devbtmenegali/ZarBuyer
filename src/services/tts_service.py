import os
import logging
from io import BytesIO
from openai import AsyncOpenAI
import re

logger = logging.getLogger(__name__)

class ZarVoiceService:
    def __init__(self):
         # Inicializa a Carga Analytica da Voz Neural Feminina da OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY não foi encontrada no ambiente. Sintetização auditiva desabilidade.")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=api_key)

    async def generate_speech(self, text: str) -> BytesIO:
        """
        Recebe a carga de texto processada pela Inteligencia Artificial ZAR, 
        Muta formatações e aciona a síntese de tom de voz feminino (nova).
        """
        if not self.client:
            return None
            
        try:
            # Remoção tática de marcação Markdown e Emojis para o Robô não pronunciar coisas bizarras
            clean_text = text.replace('*', '').replace('_', '').replace('🧠', '').replace('📦', '').replace('⏳', '').replace('⚖️', '')
            clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', clean_text)
            
            # OpenAI limita a síntese por request
            truncated_text = clean_text[:4000]
            if not truncated_text.strip():
                return None
                
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice="nova", # A voz executiva, analítica, feminina e de impacto
                input=truncated_text,
                response_format="opus" # Formato nativo perfeito do App Telegram
            )
            
            audio_io = BytesIO(response.content)
            audio_io.name = "zar_executive_summary.ogg"
            return audio_io
        except Exception as e:
            logger.error(f"Erro vital ao processar motor fonético (TTS): {e}")
            return None
