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
from datetime import datetime, timedelta

load_dotenv()

def sisgem_to_date(sisgem_val):
    """Converte o inteiro do Sisgem (Dias desde 1800 ou similar) para data real"""
    try:
        val = int(float(str(sisgem_val)))
        # Base descoberta por engenharia reversa: 82295 = 23/04/2024
        # Referencia fixa: 23/04/2024 (82295)
        base_date = datetime(2024, 4, 23)
        offset = val - 82295
        return (base_date + timedelta(days=offset)).strftime("%Y-%m-%d")
    except:
        return str(sisgem_val)

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
    """Consulta o estoque real por GRADE (cor/tamanho) e cruza com o cadastro"""
    if not supabase: return "Banco de dados indisponível."
    try:
        # 1. Puxa o Cadastro Geral (Estoque Master)
        res_cad = supabase.table("mercadoria_cad").select("*").limit(4000).execute()
        produtos = [p.get("dados", {}) for p in res_cad.data]
        
        # Filtra quem tem estoque no cadastro geral
        com_estoque = [p for p in produtos if float(p.get('saldo1', '0')) > 0]
        
        relatorio = f"ESTOQUE GERAL DISPONÍVEL (Dados do Cadastro Master):\n"
        for p in com_estoque[:400]:
            relatorio += f"- {p.get('descricao')} | Saldo Total: {p.get('saldo1')} | R$ {p.get('preco_venda_varejo')}\n"
            
        # 2. Tenta puxar grades como detalhamento (Se houver)
        try:
            res_grade = supabase.table("mercadoria_grade").select("*").limit(500).execute()
            if res_grade.data:
                relatorio += "\nDETALHAMENTO POR GRADE (Cores/Tamanhos):\n"
                for g in res_grade.data[:100]:
                    d = g.get("dados", {})
                    if float(d.get("saldo1", "0")) > 0:
                        relatorio += f"  - Item {d.get('cod_mercadoria')} | Tam: {d.get('tamanho')} | Saldo: {d.get('saldo1')}\n"
        except: pass

        return relatorio if len(com_estoque) > 0 else "Estoque zerado no cadastro global."
    except Exception as e:
        return f"Erro ao acessar Grade/Estoque: {e}"

async def buscar_pedidos_compra() -> str:
    """Busca o que está vindo da fábrica (Pedidos de Compra)"""
    if not supabase: return "Sem dados de fábrica."
    try:
        # Puxa itens de pedidos de compra ativos (pendentes de recebimento)
        res = supabase.table("pedido_compra_item").select("*").order("ultima_atualizacao", desc=True).limit(500).execute()
        itens = [i.get("dados", {}) for i in res.data]
        
        pendentes = [i for i in itens if float(i.get('quantidade_pedida', '0')) > float(i.get('quantidade_recebida', '0'))]
        
        if not pendentes: return "Nenhum pedido de compra pendente na fábrica."
        
        relatorio = "MERCADORIAS A CAMINHO (FÁBRICA):\n"
        for i in pendentes[:100]:
            faltam = float(i.get('quantidade_pedida', 0)) - float(i.get('quantidade_recebida', 0))
            relatorio += f"- Cód:{i.get('cod_mercadoria')} | Faltam chegar: {faltam} un | Pedido Ref:{i.get('fk_pc')}\n"
            
        return relatorio
    except Exception as e:
        return f"Erro ao acessar Pedidos Compra: {e}"

async def buscar_vendas_hoje() -> str:
    """Busca as vendas registradas recentemente para análise de giro"""
    if not supabase: return "Banco de dados indisponível."
    try:
        res = supabase.table("pv_movto").select("*").order("ultima_atualizacao", desc=True).limit(1000).execute()
        # Aplica a tradução de data do Sisgem antes de processar
        pedidos = []
        hoje = datetime.now().strftime("%Y-%m-%d")
        
        for p in todos_pedidos:
            # Tenta traduzir a data_inclusao (numerica) para data real
            p["data_real"] = sisgem_to_date(p.get("data_inclusao", p.get("data", "")))
            if p["data_real"] == hoje:
                pedidos.append(p)
        
        if not pedidos: 
            pedidos = todos_pedidos[:100] # Fallback apenas se não houver faturamento hoje
        
        faturamento = sum((float(p.get('preco_total', p.get('val_liquido', '0'))) for p in pedidos))
        
        relatorio = f"VENDAS RECENTES:\nTotal listed: R$ {faturamento:.2f}\n"
        for p in pedidos[:15]:
            relatorio += f"Ped #{p.get('numero_do_pedido')} | Qtd {p.get('quantidade')} | R${p.get('preco_total')}\n"
            
        return relatorio
    except Exception as e:
        return f"Erro ao acessar Vendas: {e}"

async def buscar_mercadoria_por_termo(termo: str) -> str:
    """Busca específica no banco por nome da marca ou produto (A Lupa)"""
    if not supabase or not termo or len(termo) < 3: return ""
    try:
        # Busca no cadastro pelo termo (Case Insensitive via ilike no Supabase)
        # Como o dado está dentro de JSON, fazemos um filtro inteligente
        res = supabase.table("mercadoria_cad").select("*").execute()
        
        # Filtro em Python para garantir precisão no campo 'dados'
        encontrados = []
        for r in res.data:
            dados = r.get("dados", {})
            if termo.upper() in str(dados.get("descricao", "")).upper() or termo.upper() in str(dados.get("cod_marca", "")).upper():
                encontrados.append(dados)
        
        if not encontrados: return f"\n(Busca por '{termo}': Nenhum item encontrado em toda a base)."
        
        relatorio = f"\nRESULTADOS DA LUPA PARA '{termo}':\n"
        for p in encontrados[:50]: # Retorna até 50 correspondencias exatas
            relatorio += f"- {p.get('descricao')} | R$ {p.get('preco_venda_varejo')} | Cód:{p.get('cod_mercadoria')}\n"
        
        return relatorio
    except Exception as e:
        return f"\n(Erro na busca profunda: {e})"

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
            "SEU RACIOCÍNIO DEVE SER: Vendas (Giro) vs Estoque Real vs Compras em Trânsito. "
            "Se o giro é alto e o estoque é baixo, sugira compra. Se já houver pedido de compra pendente, apenas informe a previsão."
            "Sempre destaque números com emojis estratégicos 💰, 📦, 📈. Evite conversas longas e vá direto ao ponto."
        )
        
        # 3. ZAR decide se precisa consultar o banco baseado na mensagem
        dados_contexto = ""
        texto_lower = texto_usuario.lower()
        
        # Para saudações muito simples, ele não carrega banco, mas para o resto sim.
        if texto_lower not in ["oi", "olá", "bom dia", "boa noite", "tudo bem"]:
            # Ele SEMPRE carrega os dados básicos
            dados_contexto += "--- DADOS DE ESTOQUE REAL (GRADE) ---\n" + await buscar_resumo_estoque() + "\n"
            dados_contexto += "--- DADOS DE VENDAS (HOJE) ---\n" + await buscar_vendas_hoje() + "\n"
            dados_contexto += "--- PEDIDOS DE COMPRA ATIVOS (FÁBRICA) ---\n" + await buscar_pedidos_compra() + "\n"
            
            # 💡 A LUPA: Se o usuário citar nomes (ex: Bella Janela, Altenburg, Tapete), o ZAR faz busca profunda
            palavras = texto_usuario.split()
            keywords = [p for p in palavras if len(p) > 3 and p.lower() not in ["venda", "estoque", "resumo", "hoje", "quanto"]]
            for kw in keywords[:2]: # Pega as 2 palavras principais pra não sobrecarregar
                dados_contexto += await buscar_mercadoria_por_termo(kw)

        prompt_final = f"INSTRUÇÕES AO ZAR: Analise o pedido do usuário combinando Giro x Estoque x Compras. Preste atenção especial aos resultados da LUPA se houver.\n\n"
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
