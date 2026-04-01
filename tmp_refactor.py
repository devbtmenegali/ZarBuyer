import codecs

def refactor():
    file_path = "src/bot/handlers.py"
    with codecs.open(file_path, "r", "utf-8") as f:
        code = f.read()
        
    # Remove the monkey patch
    old_patch = """            # --- ZAR VOICE ENGINE: MONKEY PATCHING ---
            # Se o usuário enviou uma mensagem de áudio, a ZAR DEVE responder em áudio!
            if context.user_data.get("reply_as_voice"):
                original_reply_text = update.message.reply_text
                import types
                
                async def augmented_voice_reply(*args, **kwargs):
                    # 1. Envia o texto limpo para o chefe poder ler se preferir
                    msg_text = args[0] if args else kwargs.get('text', '')
                    await original_reply_text(*args, **kwargs)
                    
                    # 2. Sintetiza a voz no background e dispara o Player de Áudio Oficial do Telegram
                    try:
                        from src.services.tts_service import ZarVoiceService
                        tts = ZarVoiceService()
                        audio_stream = await tts.generate_speech(msg_text)
                        if audio_stream:
                            await update.message.reply_voice(voice=audio_stream)
                    except Exception as tts_e:
                        logger.error(f"Erro TTS Motor: {tts_e}")
                        
                update.message.reply_text = types.MethodType(augmented_voice_reply, update.message)
            # ------------------------------------------

            await target_cmd(update, context)"""
            
    if old_patch in code:
        code = code.replace(old_patch, "            await target_cmd(update, context)")
        print("Removido o Monkey Patch antigo com sucesso.")
    else:
        print("AVISO: Patch antigo nao encontrado! Isso pode gerar codigo duplo.")

    # Insere reply_zar perto do top
    reply_zar_code = """
async def reply_zar(update, context, text, **kwargs):
    await update.message.reply_text(text, **kwargs)
    if context.user_data.get("reply_as_voice"):
        try:
            from src.services.tts_service import ZarVoiceService
            import logging
            tts = ZarVoiceService()
            audio_stream = await tts.generate_speech(text)
            if audio_stream:
                await update.message.reply_voice(voice=audio_stream)
        except Exception as e:
            logging.getLogger(__name__).error(f"Erro Interno no TTS: {e}")
"""
    if "async def reply_zar" not in code:
        code = code.replace("from telegram import Update\n", "from telegram import Update\n" + reply_zar_code + "\n")
        print("Injetado funcao reply_zar no topo.")

    # Substitui em todos os lugares EXCETO dentro de reply_zar
    lines = code.split("\n")
    in_reply_zar = False
    for i, line in enumerate(lines):
        if line.startswith("async def reply_zar"):
            in_reply_zar = True
        elif in_reply_zar and not line.startswith(" ") and line.strip() != "":
            in_reply_zar = False
            
        if not in_reply_zar:
            if "await update.message.reply_text(" in line:
                lines[i] = line.replace("await update.message.reply_text(", "await reply_zar(update, context, ")

    code = "\n".join(lines)
    
    with codecs.open(file_path, "w", "utf-8") as f:
        f.write(code)
    print("Refatoração de Handlers.py concluida.")

if __name__ == "__main__":
    refactor()
