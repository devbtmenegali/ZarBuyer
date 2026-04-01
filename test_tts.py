import asyncio
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    print(f"Buscando chave: {os.environ.get('GEMINI_API_KEY')[:5]}***")
    
    try:
        from src.services.tts_service import ZarVoiceService
        tts = ZarVoiceService()
        audio = await tts.generate_speech("Teste básico de síntese de voz nativa da Google. Por favor fale esta frase.")
        if audio:
            print(f"SUCESSO ABSOLUTO! O arquivo foi gerado com {len(audio.getvalue())} bytes.")
        else:
            print("FALHA: O objeto retornado foi nulo.")
    except Exception as e:
        print(f"ERRO EXCEPCIONAL CRÍTICO: {e}")

if __name__ == "__main__":
    asyncio.run(main())
