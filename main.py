import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import datetime

# Use a biblioteca oficial (nova) do google-genai
from google import genai
from google.genai import types

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("ERRO: Credenciais do Supabase ausentes no .env")
    supabase = None

# Inicializa o Gemini
if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("ERRO: GEMINI_API_KEY ausente.")
    ai_client = None

# --- Ferramentas do Agente (Para consultar a Nuvem em Tempo Real) ---

async def buscar_resumo_estoque() -> str:
    """Consulta o Supabase (tabela mercadoria_cad) e retorna um texto pro Gemini processar"""
    if not supabase: return "Banco de dados indisponível."
    try:
        res = supabase.table("mercadoria_cad").select("*").limit(2000).execute()
        mercadorias = [m.get("dados", {}) for m in res.data]
        
        # Filtra os que tem saldo
        em_estoque = [m for m in mercadorias if float(m.get('saldo1', '0')) > 0]
        
        relatorio = f"Temos {len(em_estoque)} itens diferentes em estoque.\n"
        
        # Monta amostra dos 20 com maior estoque
        top_produtos = sorted(em_estoque, key=lambda x: float(x.get('saldo1', '0')), reverse=True)[:20]
        for p in top_produtos:
            relatorio += f"- Produto: {p.get('descricao', '?')} | Qtd: {p.get('saldo1')} | Custo: R${p.get('preco_custo')} | Venda: R${p.get('preco_venda_varejo')}\n"
            
        return relatorio + "\n\n(Amostra resumida baseada nos itens de maior volume)."
    except Exception as e:
        return f"Erro ao acessar ERP: {e}"

async def buscar_vendas_hoje() -> str:
    """Busca os ultimos 100 pedidos na tabela pv_movto"""
    if not supabase: return "Banco de dados indisponível."
    try:
        # Pega as últimas 100 linhas (que são os pedidos mais recentes graças ao trigger do ERP)
        res = supabase.table("pv_movto").select("*").order("ultima_atualizacao", desc=True).limit(100).execute()
        pedidos = [p.get("dados", {}) for p in res.data]
        
        if not pedidos: return "Nenhum pedido recente registrado."
        
        faturamento = sum((float(p.get('preco_total', '0')) for p in pedidos))
        
        relatorio = f"Foram lidos {len(pedidos)} itens de pedido nas últimas atualizações.\n"
        relatorio += f"Valor total listado bruto: R$ {faturamento:.2f}\n"
        relatorio += "Listagem simplificada dos produtos vendidos recentemente:\n"
        for p in pedidos[:20]: # Mostra log dos ultimos 20
            relatorio += f"Pedido #{p.get('numero_do_pedido')} | Qtd {p.get('quantidade')} | Total: R${p.get('preco_total')}\n"
            
        return relatorio
    except Exception as e:
        return f"Erro ao acessar PV: {e}"

# --- Ferramentas de Alertas Proativos e Autenticação de Fornecedores ---

async def disparar_alertas_semanais(context: ContextTypes.DEFAULT_TYPE):
    """Uma rotina assíncrona que envia mensagem para os fornecedores toda semana."""
    while True:
        agora = datetime.datetime.now()
        # Exemplo: Disparar toda Segunda-Feira às 09:00
        # Adaptaremos para o intervalo de teste se for necessário
        if agora.weekday() == 0 and agora.hour == 9 and agora.minute == 0:
            if not supabase: continue
            print("Executando Job de Alerta Semanal para Fornecedores!")
            
            try:
                res = supabase.table("suppliers").select("*").not_is("telegram_chat_id", "null").execute()
                fornels = res.data
                for f in fornels:
                    # Raciocínio Gemini customizado para o 'f'
                    brand = f.get("brand")
                    chat_id = f.get("telegram_chat_id")
                    
                    # Logica crua (simulada) para construir os alertas
                    prompt_alerta = (
                        f"Aja como ZAR. Escreva uma notificação proativa curta e impactante para o fornecedor {f.get('name')} "
                        f"dizendo o resumo das vendas semanais da marca {brand} e listando repor os itens abaixo de 5 un da marca dele."
                    )
                    
                    resp = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_alerta
                    )
                    
                    await context.bot.send_message(chat_id=chat_id, text=resp.text)
            except Exception as e:
                print(f"Erro no job de fornecedores: {e}")
                
            await asyncio.sleep(65) # Espera 1 min pra não disparar duplo
        else:
            await asyncio.sleep(30) # Checa a cada 30 segundos

async def fornecedor_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso correto: /fornecedor [SUA CHAVE]")
        return
        
    chave = context.args[0]
    chat_id = update.message.chat_id
    
    if not supabase: return
    
    # 1. Busca se a chave existe na base admin 
    res = supabase.table("suppliers").select("*").eq("code", chave).execute()
    if not res.data:
        await update.message.reply_text("Chave de fornecedor inválida.")
        return
        
    forn = res.data[0]
    
    # 2. Atualiza o chat_id logado
    # Aqui criamos/atualizamos o chat_id pra essa marca (Nota: a coluna telegram_chat_id deve existir)
    try:
        supabase.table("suppliers").update({"telegram_chat_id": str(chat_id)}).eq("id", forn["id"]).execute()
        await update.message.reply_text(f"✅ Identidade confirmada! Bem-vindo, {forn['name']}.\nVocê está habilitado para monitorar a marca: {forn['brand']}.")
    except Exception as e:
        await update.message.reply_text(f"A plataforma não pôde registrar seu acesso. Verifique se o BD possui a coluna 'telegram_chat_id'. Erro: {e}")

# --- Funções do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⚡ *Sistema ZAR Reiniciado.*\n\n"
        "Eu sou o seu Agente ZAR de Inteligência Empresarial.\n"
        "Minha conexão com o banco espelhado do ERP está *Online*.\n"
        "Não preciso mais de planilhas. Você pode me perguntar agora mesmo: \n"
        "_\"Zar, resuma o que temos no estoque\"_\n"
        "_\"Zar, como foram as vendas recentes?\"_",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto_usuario = update.message.text
    
    # 1. Feedback inicial para mensagens longas
    await update.message.reply_chat_action(action='typing')
    
    try:
        # 2. Contexto do Sistema (A "Alma" do ZAR)
        system_instruction = (
            "Você é o ZAR Agent. Um executivo brilhante, analítico, formal, mas altamente direto e objetivo. "
            "Você analisa dados do ERP em tempo real para ajudar o comprador/gerente. "
            "Sempre destaque números com emojis estratégicos 💰, 📦, 📈. Evite conversas longas e vá direto ao ponto."
            "Diga a verdade nua e crua se o estoque estiver encalhado ou o lucro estiver ruim."
        )
        
        # 3. ZAR decide se precisa consultar o banco baseado na mensagem
        dados_contexto = ""
        texto_lower = texto_usuario.lower()
        if "estoque" in texto_lower or "produtos" in texto_lower or "temos" in texto_lower or "resumo" in texto_lower:
            dados_contexto += "--- DADOS DE ESTOQUE EXTRAÍDOS AGORA ---\n" + await buscar_resumo_estoque() + "\n"
        
        if "venda" in texto_lower or "lucro" in texto_lower or "pedido" in texto_lower or "hoje" in texto_lower:
            dados_contexto += "--- DADOS DE VENDAS RECENTES ---\n" + await buscar_vendas_hoje() + "\n"

        prompt_final = f"INSTRUÇÕES AO ZAR: Analise o pedido do usuário e utilize os dados extraídos do ERP se houverem.\n\n"
        prompt_final += f"{dados_contexto}\n\n"
        prompt_final += f"MENSAGEM DO USUÁRIO (SEU CHEFE): {texto_usuario}"
        
        # 4. Envia pro Gemini processar o raciocínio e escrever a mensagem
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_final,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3 # Baixa temperatura para ele ser objetivo e matemático
            )
        )
        
        # 5. Responde no Telegram
        await update.message.reply_text(response.text)
        
    except Exception as e:
        print(f"Erro no cérebro do Gemini: {e}")
        await update.message.reply_text(f"ZAR Encontrou uma anomalia em seus sistemas cognitivos.\nErro: {str(e)[:100]}...")

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
# --- Inicialização ---

async def disparar_roteiro_background(app: Application) -> None:
    # Esta função roda assim que o Telegram ligar, sem quebrar o loop do servidor principal.
    # Ela "desacopla" a rotina semanal e joga pro fundo.
    asyncio.create_task(disparar_alertas_semanais(app))

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Erro: TELEGRAM_BOT_TOKEN não configurado no .env")
        return

    # Construção certa do app pro Python 3.10+
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(disparar_roteiro_background).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fornecedor", fornecedor_login))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 O novo ZAR Agent está operante e conectado ao Telegram!")
    
    app.run_polling()

if __name__ == '__main__':
    main()
