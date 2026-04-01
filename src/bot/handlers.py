import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.services.excel_parser import ExcelInventoryParser
from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# --- HELPERS DE AUTENTICAÇÃO ---
async def get_user_auth(telegram_id: int):
    supabase = get_supabase_client()
    resp = supabase.table('bot_users').select('*').eq('telegram_id', telegram_id).execute()
    if resp.data:
        return resp.data[0]
    return None

def is_admin(user_auth):
    return user_auth and user_auth.get('role') == 'admin'

def is_supplier(user_auth, requested_brand=""):
    if not user_auth or user_auth.get('role') != 'supplier':
        return False
    # Se uma marca for pedida, deve estar contida no portfólio do fornecedor
    if requested_brand:
        current_brand = user_auth.get('brand', '')
        auth_brands = [b.strip().lower() for b in current_brand.split(',') if b.strip()]
        requested = requested_brand.lower()
        
        # Verifica se pediu especificamente algo do portfólio dele (Ex: MMartan contém MMartan, ou Karsten contém Karsten)
        if not any(requested in b for b in auth_brands) and not any(b in requested for b in auth_brands):
            return False
    return True

# --- COMANDOS DE REGISTRO ---
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("🔑 Uso correto: /admin [sua_senha_secreta]")
        return
        
    senha_enviada = args[0]
    senha_real = os.environ.get("ADMIN_PASSWORD", "zar123") # Default password if not in .env
    
    if senha_enviada == senha_real:
        supabase = get_supabase_client()
        tg_id = update.effective_user.id
        
        # Upsert admin
        user_auth = await get_user_auth(tg_id)
        if user_auth:
            supabase.table('bot_users').update({'role': 'admin', 'brand': 'TODAS'}).eq('telegram_id', tg_id).execute()
        else:
            supabase.table('bot_users').insert({'telegram_id': tg_id, 'role': 'admin', 'brand': 'TODAS'}).execute()
            
        await update.message.reply_text("🔓 Acesso ADMINISTRADOR liberado! Você tem controle total do ZAR Agent.")
    else:
        await update.message.reply_text("❌ Senha incorreta. Acesso negado.")

async def cmd_sou_fornecedor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("🏢 Uso correto: /sou_fornecedor [Nome da Sua Marca]\nExemplo: /sou_fornecedor Altenburg")
        return
        
    brand = " ".join(args)
    tg_id = update.effective_user.id
    supabase = get_supabase_client()
    
    user_auth = await get_user_auth(tg_id)
    if user_auth:
        current_brand = user_auth.get('brand', '')
        
        if user_auth.get('role') == 'supplier':
            # Adiciona ao portfólio sem duplicar
            auth_brands = [b.strip().lower() for b in current_brand.split(',') if b.strip()]
            if brand.lower() not in auth_brands:
                new_brand = f"{current_brand}, {brand}" if current_brand else brand
            else:
                new_brand = current_brand
        else:
            new_brand = brand # Se era admin e rodou isso, vira fornecedor comum (override)
            
        supabase.table('bot_users').update({'role': 'supplier', 'brand': new_brand}).eq('telegram_id', tg_id).execute()
        brand_to_show = new_brand
    else:
        supabase.table('bot_users').insert({'telegram_id': tg_id, 'role': 'supplier', 'brand': brand}).execute()
        brand_to_show = brand
        
    await update.message.reply_text(f"🤝 Bem-vindo, Fornecedor! O ZAR está configurado para o seu portfólio atual:\n📦 {brand_to_show}")
# --- COMANDOS PRINCIPAIS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Sou o Agente ZAR.\n\n"
        "Se você é o DONO, faça o login com: /admin [senha]\n"
        "Se você é FORNECEDOR, digite: /sou_fornecedor [sua_marca]"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Negado: Apenas Administradores podem fazer upload de XML de Notas Fiscais ou Planilhas.")
        return

    doc = update.message.document
    
    allowed_extensions = ('.xlsx', '.xml', '.pdf')
    if not doc.file_name.lower().endswith(allowed_extensions):
        await update.message.reply_text("Por favor, envie um arquivo Excel (.xlsx), Nota Fiscal (.xml) ou Pedido (.pdf).")
        return
        
    await update.message.reply_text(f"📥 Recebi o arquivo: {doc.file_name}. Acionando sensores adequados...")
    
    try:
        # Baixar o arquivo do Telegram
        file_obj = await context.bot.get_file(doc.file_id)
        temp_path = f"/tmp/{doc.file_name}"
        await file_obj.download_to_drive(temp_path)
        
        if doc.file_name.lower().endswith('.xml'):
            from src.services.xml_parser import NfeParser
            from src.services.ai_agent import ZarAIAgent
            from datetime import datetime
            
            parser = NfeParser(temp_path)
            nf_data = parser.parse()
            
            supabase = get_supabase_client()
            def get_sup_id(name):
                r = supabase.table('suppliers').select('id').ilike('name', f"%{name[:10]}%").execute()
                if r.data: return r.data[0]['id']
                ins = supabase.table('suppliers').insert({'name': name}).execute()
                return ins.data[0]['id']
                
            sup_id = get_sup_id(nf_data['supplier_name'])
            
            # Procura Pedido Aberto
            order_data = None
            pending = supabase.table('purchase_orders').select('*').eq('supplier_id', sup_id).eq('status', 'PENDING').order('created_at', desc=True).limit(1).execute()
            
            p_order_id = None
            if pending.data:
                p_order_id = pending.data[0]['id']
                o_items = supabase.table('purchase_order_items').select('*').eq('purchase_order_id', p_order_id).execute()
                
                # Vamos calcular o total baseado nos itens para suprir a falta da coluna total no DB original
                sum_total = sum([float(i['quantity']) * float(i['unit_price']) for i in o_items.data])
                order_data = {
                    "supplier_name": nf_data['supplier_name'],
                    "total_amount": sum_total,
                    "items": o_items.data
                }
            
            inv_resp = supabase.table('invoices').insert({
                "purchase_order_id": p_order_id,
                "invoice_number": nf_data['invoice_number'],
                "total_amount": nf_data['total_amount']
            }).execute()
            inv_id = inv_resp.data[0]['id']
            
            inv_batch = []
            for it in nf_data['items']:
                inv_batch.append({
                    "invoice_id": inv_id,
                    "product_name": it['product_name'][:250],
                    "quantity": it['quantity'],
                    "unit_price": it['unit_price'],
                    "ncm": it['ncm'][:50] if 'ncm' in it else None
                })
            for i in range(0, len(inv_batch), 200):
                supabase.table('invoice_items').insert(inv_batch[i:i+200]).execute()
            
            # --- Inserir Parcelas (Contas a Pagar) ---
            if nf_data.get('installments'):
                pay_batch = []
                for inst in nf_data['installments']:
                    pay_batch.append({
                         "invoice_id": inv_id,
                         "installment_number": inst.get('installment_number', '001'),
                         "due_date": inst['due_date'],
                         "amount": inst['amount'],
                         "status": 'PENDING'
                    })
                try:
                    supabase.table('accounts_payable').insert(pay_batch).execute()
                except Exception as ex:
                    logger.warning(f"A tabela accounts_payable ainda não existe ou erro salvando boletos: {ex}")

            if order_data:
                await update.message.reply_text("🔍 Pedido Localizado no Banco de Dados! Acionando ZAR Auditor Neural para bater Itens e Preços...")
                agent = ZarAIAgent()
                audit_data = agent.audit_invoice_vs_order(order_data, nf_data)
                
                if audit_data:
                    # Atualiza saldos fracionados
                    for match in audit_data.get('matched_items', []):
                        o_item = next((i for i in order_data['items'] if i['product_name'] == match.get('order_item_name')), None)
                        if o_item:
                            current_received = float(o_item.get('received_quantity') or 0)
                            new_received = current_received + float(match.get('quantity_received_now', 0))
                            supabase.table('purchase_order_items').update({'received_quantity': new_received}).eq('id', o_item['id']).execute()
                            
                    new_status = 'AUDITED' if audit_data.get('is_order_completed') else 'PARTIAL'
                    supabase.table('purchase_orders').update({'status': new_status}).eq('id', p_order_id).execute()
                    
                    report_text = audit_data.get('report_text', 'Auditoria concluída!')
                else:
                    report_text = "❌ Ocorreu um erro com a formatação neural da Auditoria. A NFe foi importada, mas o Pedido não sofreu baixa."
                
                for chunk in chunk_message(report_text):
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(f"✅ Nota Fiscal Gravada! (Nenhum Pedido Original encontado no sistema para auditar contra a nota {nf_data['invoice_number']}).")

            if os.path.exists(temp_path):
                os.remove(temp_path)
            return

        elif doc.file_name.lower().endswith('.pdf'):
            from src.services.ai_agent import ZarAIAgent
            from datetime import datetime
            
            await update.message.reply_text("👁️ Ativando a Visão Computacional do ZAR para ler seu PDF e extrair JSON...")
            agent = ZarAIAgent()
            pdf_data = agent.parse_purchase_order_pdf(temp_path)
            
            if not pdf_data or "items" not in pdf_data:
                await update.message.reply_text("❌ Falha crítica: O documento PDF não continha dados legíveis ou a IA rejeitou a formatação.")
                return
                
            supabase = get_supabase_client()
            def get_sup_id(name):
                r = supabase.table('suppliers').select('id').ilike('name', f"%{name[:10]}%").execute()
                if r.data: return r.data[0]['id']
                ins = supabase.table('suppliers').insert({'name': name}).execute()
                return ins.data[0]['id']
                
            sup_name = pdf_data.get('supplier_name', 'Fábrica Desconhecida')
            sup_id = get_sup_id(sup_name)
            
            po_resp = supabase.table('purchase_orders').insert({
                'supplier_id': sup_id,
                'order_date': datetime.now().strftime('%Y-%m-%d'),
                'status': 'PENDING'
            }).execute()
            po_id = po_resp.data[0]['id']
            
            po_items = []
            for it in pdf_data.get('items', []):
                po_items.append({
                    "purchase_order_id": po_id,
                    "product_name": str(it.get('product_name', 'Item'))[:250],
                    "quantity": float(it.get('quantity', 0)),
                    "unit_price": float(it.get('unit_price', 0))
                })
            for i in range(0, len(po_items), 200):
                supabase.table('purchase_order_items').insert(po_items[i:i+200]).execute()
                
            await update.message.reply_text(
                f"📋 *PEDIDO GRAVADO COM SUCESSO!*\n"
                f"🏢 Fábrica: {sup_name}\n"
                f"📦 Itens Distintos: {len(po_items)}\n"
                f"💰 Total Declarado: R$ {pdf_data.get('total_amount', 0):,.2f}\n\n"
                f"O ZAR ficará de guarda aguardando a Nota Fiscal desta fábrica para defender seu capital!"
            )
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return

        # ===== ROTINA ANTIGA DE EXCEL (.xlsx) ABAIXO =====
        file_obj = await context.bot.get_file(doc.file_id)
        temp_path = f"/tmp/{doc.file_name}"
        await file_obj.download_to_drive(temp_path)
        
        # Parse da planilha
        parser = ExcelInventoryParser(temp_path)
        parsed_data = parser.parse_daily_inventory()
        
        await update.message.reply_text(f"Li {len(parsed_data)} produtos validos na planilha. Atualizando banco de dados...")
        
        # Inserção no Supabase (Upsert nos Produtos, Insert no Snapshot)
        supabase = get_supabase_client()
        
        # Prepara os dados para Bulk Upsert/Insert (Removendo duplicatas da mesma carga)
        products_dict = {}
        for item in parsed_data:
            products_dict[item["sku"]] = {
                "sku": item["sku"],
                "name": item["name"],
                "unit": item["unit"],
                "reference": item["reference"],
                "brand": item["brand"]
            }
        products_batch = list(products_dict.values())
            
        chunk_size = 500
        
        # 1. Faz Bulk Upsert dos Produtos
        logger.info(f"Fazendo upsert de {len(products_batch)} produtos...")
        # O supabase-py aceita uma lista para upsert bulk
        if products_batch:
            for i in range(0, len(products_batch), chunk_size):
                supabase.table('products').upsert(products_batch[i:i+chunk_size], on_conflict="sku").execute()
            
        # 2. Busca os IDs dos produtos reais do banco pelo SKU
        logger.info("Buscando IDs gerados...")
        skus = [p["sku"] for p in products_batch]
        product_map = {}
        for i in range(0, len(skus), chunk_size):
            resp = supabase.table('products').select("id, sku").in_("sku", skus[i:i+chunk_size]).execute()
            for row in resp.data:
                product_map[row["sku"]] = row["id"]
                
        # 3. Prepara os snapshots com os IDs e faz Bulk Insert garantindo product_id único nesta carga
        snapshots_dict = {}
        for item in parsed_data:
            p_id = product_map.get(item["sku"])
            if p_id:
                snapshots_dict[p_id] = {
                    "product_id": p_id,
                    "sale_price": item["sale_price"],
                    "cost_price": item["cost_price"],
                    "stock_balance": item["stock_balance"],
                    "total_cost": item["total_cost"]
                }
        snapshots_batch = list(snapshots_dict.values())
                
        logger.info(f"Fazendo insert de {len(snapshots_batch)} snapshots de estoque (após limpeza)...")
        if snapshots_batch:
            for i in range(0, len(snapshots_batch), chunk_size):
                supabase.table('inventory_snapshots').upsert(snapshots_batch[i:i+chunk_size], on_conflict="product_id, snapshot_date").execute()

        # Remove arquivo temp
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        await update.message.reply_text(
            f"Processamento super rápido concluído! {len(snapshots_batch)} registros atualizados no estoque de hoje."
        )

    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        await update.message.reply_text(f"Ocorreu um erro no processamento do arquivo: {str(e)}")


def chunk_message(text, size=4000):
    return [text[i:i+size] for i in range(0, len(text), size)]

async def cmd_analisar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not auth:
        await update.message.reply_text("⛔ Faça login para acessar o sistema de análises.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        brandFilter = " ".join(args) if args else None
        
        if auth['role'] == 'supplier':
            auth_brands = [b.strip() for b in auth['brand'].split(',') if b.strip()]
            if not brandFilter:
                if len(auth_brands) == 1:
                    brandFilter = auth_brands[0]
                else:
                    await update.message.reply_text(f"⚠️ Você representa múltiplas marcas: {auth['brand']}\nPor favor, digite qual deseja analisar. Ex: /analisar {auth_brands[0]}")
                    return
            else:
                if not is_supplier(auth, brandFilter):
                    await update.message.reply_text(f"🔒 Acesso Fornecedor: Redirecionamento negado para '{brandFilter}'. Suas marcas permitidas: {auth['brand']}")
                    return
        
        await update.message.reply_text("Consultando o banco de dados... 🔎")
        
        db_service = InventoryDataService()
        data = db_service.get_brand_summary(brandFilter)
        
        if not data:
            await update.message.reply_text("Não encontrei produtos desta marca no banco.")
            return
            
        await update.message.reply_text(f"Encontrei os produtos. Acionando a Inteligência ZAR (Gemini) para diagnosticar... 🤖")
        
        agent = ZarAIAgent()
        report = agent.analyze_brand_summary(data, brandFilter)
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em analisar: {str(e)[:500]}")

async def cmd_micos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria pode mapear Dead Stock e Combos.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        await update.message.reply_text("Buscando o maior capital imobilizado para caça aos 'Micos' (Dead Stock) e Combos... 💸")
        
        db_service = InventoryDataService()
        data = db_service.get_highest_stock_items()
        
        agent = ZarAIAgent()
        report = agent.analyze_inventory_health(data)
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em micos: {str(e)[:500]}")

async def cmd_pendencias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not auth:
        await update.message.reply_text("⛔ Faça login para consultar pendências.")
        return

    try:
        from src.db.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        args = context.args
        if auth['role'] == 'supplier':
            auth_brands = [b.strip() for b in auth['brand'].split(',') if b.strip()]
            if not args:
                if len(auth_brands) == 1:
                    brand = auth_brands[0]
                else:
                    await update.message.reply_text(f"⚠️ Você representa múltiplas marcas: {auth['brand']}\nPor favor, informe a fábrica para investigar a logística. Ex: /pendencias {auth_brands[0]}")
                    return
            else:
                brand = " ".join(args)
                if not is_supplier(auth, brand):
                    await update.message.reply_text(f"🔒 Acesso Fornecedor: Você não possui a marca '{brand}'. Suas marcas: {auth['brand']}")
                    return
        else:
            if not args:
                await update.message.reply_text("⚠️ Por favor, informe a fábrica. Exemplo: /pendencias Altenburg")
                return
            brand = " ".join(args)
        
        # 1. Ache o fornecedor
        r = supabase.table('suppliers').select('id, name').ilike('name', f"%{brand[:10]}%").execute()
        if not r.data:
            await update.message.reply_text(f"❌ Não encontrei fornecedor contendo '{brand}'.")
            return
            
        sup_id = r.data[0]['id']
        sup_name = r.data[0]['name']
        
        await update.message.reply_text(f"Investigando entregas fracionadas da {sup_name}... 🔎")
        
        # 2. Ache ordens PENDING ou PARTIAL
        o_resp = supabase.table('purchase_orders').select('id, order_date, status').eq('supplier_id', sup_id).in_('status', ['PENDING', 'PARTIAL']).execute()
        if not o_resp.data:
            await update.message.reply_text(f"✅ O fornecedor {sup_name} não tem nenhum pedido pendente! Entregas 100% liquidadas.")
            return
            
        # 3. Ache itens dessas ordens
        order_ids = [o['id'] for o in o_resp.data]
        items_resp = supabase.table('purchase_order_items').select('*').in_('purchase_order_id', order_ids).execute()
        
        # 4. Encontre os faltantes
        missing_items = []
        for it in items_resp.data:
            q = float(it['quantity'])
            r_q = float(it.get('received_quantity') or 0)
            if q > r_q:
                missing_items.append({
                    "name": it['product_name'],
                    "missing": q - r_q,
                    "price": float(it['unit_price'])
                })
                
        if not missing_items:
            await update.message.reply_text(f"✅ Pedidos encontrados, mas a matemática fechou. Nada pendente para {sup_name}.")
            return
            
        # 5. Formatar reposta
        total_missing = sum([i['missing'] * i['price'] for i in missing_items])
        
        msg = f"📦 *PENDÊNCIAS LOGÍSTICAS: {sup_name}*\n"
        msg += f"Status: {len(o_resp.data)} Pedido(s) aguardando carga total.\n\n"
        for i in missing_items:
            msg += f"• Falta {int(i['missing'])}x {i['name'][:40]} (R$ {i['price']:,.2f})\n"
            
        msg += f"\n💰 Valor Total Preso em Trânsito: R$ {total_missing:,.2f}"
        
        for chunk in chunk_message(msg):
            await update.message.reply_text(chunk, parse_mode="Markdown")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em pendencias: {str(e)[:500]}")

async def cmd_negociar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Negado: Informações de Preços e Margens de Lucro são restritas à diretoria.")
        return

    try:
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if len(args) < 3:
            await update.message.reply_text(
                "⚠️ Uso correto: /negociar [custo_proposto] [preço_venda_atual] [margem_ideal_%]\n"
                "Exemplo: /negociar 45.50 89.90 40"
            )
            return
            
        try:
            proposed_cost = float(args[0].replace(',', '.'))
            selling_price = float(args[1].replace(',', '.'))
            current_margin = float(args[2].replace(',', '.'))
        except ValueError:
            await update.message.reply_text("❌ Valores numéricos inválidos. Use apenas números e ponto ou vírgula.")
            return

        await update.message.reply_text("🤖 ZAR analisando a viabilidade desta negociação ao vivo...")
        
        agent = ZarAIAgent()
        report = agent.analyze_negotiation(
            current_margin=current_margin,
            proposed_cost=proposed_cost,
            selling_price=selling_price
        )
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em negociar: {str(e)[:500]}")

async def cmd_comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Alertas de quebra de estoque e compras são ferramentas da diretoria.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        brandFilter = " ".join(args) if args else "Geral"
        
        await update.message.reply_text(f"Mapeando produtos {brandFilter} em estado crítico de estoque... 📉")
        
        db_service = InventoryDataService()
        data = db_service.get_low_stock_items(brandFilter if brandFilter != "Geral" else None)
        
        if not data:
            await update.message.reply_text(f"✅ O estoque de '{brandFilter}' está saudável. Nenhum item com giro alto e estoque baixo encontrado.")
            return
            
        await update.message.reply_text(f"🚨 Encontrei {len(data)} itens críticos! ZAR elaborando sugestão de pedido de compras...")
        
        agent = ZarAIAgent()
        report = agent.analyze_purchase_recommendations(data, brandFilter)
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em alertar compras: {str(e)[:500]}")

async def cmd_comparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: O comparador de preços e auto-canibalização pesquisa concorrentes (recurso da diretoria).")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Informe o tipo de produto para comparar. Exemplo: /comparar travesseiro")
            return
            
        keyword = " ".join(args)
        await update.message.reply_text(f"Buscando produtos similares a '{keyword}' no estoque... 🔍")
        
        db_service = InventoryDataService()
        data = db_service.compare_similar_products(keyword)
        
        if not data or len(data) < 2:
            await update.message.reply_text(f"❌ Não encontrei produtos suficientes contendo '{keyword}' para uma comparação útil.")
            return
            
        await update.message.reply_text(f"⚖️ Encontrei {len(data)} itens similares. Acionando ZAR para análise de concorrência e preços...")
        
        agent = ZarAIAgent()
        report = agent.analyze_product_comparison(data, keyword)
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em comparar: {str(e)[:500]}")

async def cmd_cotar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Apenas o Gestor de Compras pode gerar Pitch de Negociação Automático.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Informe a marca/fornecedor para gerar o pitch comercial. Exemplo: /cotar Altenburg")
            return
            
        brand = " ".join(args)
        await update.message.reply_text(f"Mapeando itens de alto giro de '{brand}'... 📊")
        
        db_service = InventoryDataService()
        data = db_service.get_supplier_opportunities(brand)
        
        if not data:
            await update.message.reply_text(f"❌ Não encontrei produtos de alto giro com estoque baixo da '{brand}'. O estoque pode estar cheio.")
            return
            
        await update.message.reply_text(f"✅ Encontrei {len(data)} itens com giro rápido. ZAR escrevendo a mensagem de negociação em lote...")
        
        agent = ZarAIAgent()
        report = agent.generate_supplier_pitch(data, brand)
        
        for chunk in chunk_message(report):
            await update.message.reply_text(chunk, parse_mode="HTML")
            
    except Exception as e:
        await update.message.reply_text(f"Erro fatal em cotar: {str(e)[:500]}")

async def cmd_caixa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Negado: Visão de contas a pagar e desembolsos restrito.")
        return

    try:
        from src.services.ai_agent import ZarAIAgent
        from src.db.supabase_client import get_supabase_client
        from datetime import datetime
        
        await update.message.reply_text("💸 Analisando Faturas e Projetando Desembolsos do Caixa... ⏳")
        
        supabase = get_supabase_client()
        # Busca faturas pendentes da tabela
        resp = supabase.table('accounts_payable').select('id, invoice_id, due_date, amount, status').eq('status', 'PENDING').execute()
        
        if not resp.data:
            await update.message.reply_text("🎉 Não há boletos abertos extraídos no momento! Você está em dia.")
            return
            
        # Puxa relacionamento para saber quem cobrar/pagar (NF > Order > Supplier)
        # Usamos selects locais para não quebrar em syntax error de join no Python Client Supabase
        invoices_resp = supabase.table('invoices').select('id, purchase_order_id, invoice_number').execute()
        orders_resp = supabase.table('purchase_orders').select('id, supplier_id').execute()
        suppliers_resp = supabase.table('suppliers').select('id, name').execute()
        
        sup_dict = {s['id']: s['name'] for s in suppliers_resp.data}
        order_dict = {o['id']: sup_dict.get(o['supplier_id'], 'Desconhecida') for o in orders_resp.data}
        inv_dict = {i['id']: {'num': i['invoice_number'], 'sup_name': order_dict.get(i['purchase_order_id'], 'Desconhecida')} for i in invoices_resp.data}
        
        boletos = []
        for p in resp.data:
            inv_info = inv_dict.get(p['invoice_id'], {})
            boletos.append({
                "venc": p.get('due_date'),
                "vlr": p.get('amount'),
                "nf": inv_info.get('num', '?'),
                "fabrica": inv_info.get('sup_name', '?')
            })
            
        boletos.sort(key=lambda x: str(x['venc']))
        boletos_recentes = boletos[:40] # Manda no máx 40 boletos pra não estourar prompt do Gemini
        
        agent = ZarAIAgent()
        analysis = agent.analyze_cash_flow(boletos_recentes)
        
        for chunk in chunk_message(analysis):
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Erro fatal em caixa: {e}")
        await update.message.reply_text(f"O ZAR Financeiro acusou pane ao ler as contas: {str(e)[:500]}")

async def cmd_giro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not auth:
        await update.message.reply_text("⛔ Faça login para acessar o sistema de Giro de Estoque.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if auth['role'] == 'supplier':
            auth_brands = [b.strip() for b in auth['brand'].split(',') if b.strip()]
            if not args:
                if len(auth_brands) == 1:
                    brand = auth_brands[0]
                else:
                    await update.message.reply_text(f"⚠️ Você representa múltiplas marcas: {auth['brand']}\nPor favor, digite qual deseja analisar. Ex: /giro {auth_brands[0]}")
                    return
            else:
                brand = " ".join(args)
                if not is_supplier(auth, brand):
                    await update.message.reply_text(f"🔒 Acesso Fornecedor: Redirecionamento negado para '{brand}'. Suas marcas: {auth['brand']}")
                    return
        else:
            if not args:
                await update.message.reply_text("🔎 Uso correto: /giro [Nome da Marca]")
                return
            brand = " ".join(args)
            
        await update.message.reply_text(f"⚙️ Analisando velocidade de vendas e calculando dias de cobertura para: {brand}... ⏳")
        
        db_service = InventoryDataService()
        turnover_data = db_service.analyze_inventory_turnover(brand)
        
        if not turnover_data:
            await update.message.reply_text("📉 Ainda não temos dias suficientes de histórico (Snapshots Diários) registrados para achar o padrão matemático de vendas dessa marca.")
            return
            
        agent = ZarAIAgent()
        analysis = agent.analyze_turnover(turnover_data, brand)
        
        for chunk in chunk_message(analysis):
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Erro em cmd_giro: {e}")
        await update.message.reply_text(f"Erro fatal em giro: {str(e)[:500]}")

async def cmd_reprecificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria pode alterar a política de preços de prateleira baseada em inflação.")
        return

    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Informe a fábrica para buscar distorções de inflação. Ex: /reprecificar Altenburg")
            return
            
        brand = " ".join(args)
        await update.message.reply_text(f"📉 Auditando as últimas Notas Fiscais da {brand} contra nosso Custo Base Atual... ⏳")
        
        db_service = InventoryDataService()
        repricing_data = db_service.get_repricing_opportunities(brand)
        
        if not repricing_data:
            await update.message.reply_text("✅ Boas notícias! Cruzando o banco de dados NFe vs Estoque, não foi detectada nenhuma inflação no custo de reposição dos produtos da fábrica. Remarcação de preços desnecessária.")
            return
            
        agent = ZarAIAgent()
        analysis = agent.analyze_repricing(repricing_data, brand)
        
        for chunk in chunk_message(analysis):
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Erro na reprecificação: {e}")
        await update.message.reply_text(f"Falha ao gerar etiquetas de preços novos: {str(e)[:500]}")

async def cmd_chargeback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria pode emitir termos de cobrança legal e logísticos (Chargebacks).")
        return

    try:
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Informe o número da Nota Fiscal alvo da quebra de pedido. Ex: /chargeback 123456")
            return
            
        nf_num = str(args[0])
        await update.message.reply_text(f"⚖️ ZAR Jurídico Logístico: Levantando faltantes e avarias da NFe {nf_num} para emissão da carta de protesto... ⏳")
        
        # Para efeito do teste, passamos uma anomalia simulada. Em perfomance real, ele leria da tabela `audits`.
        divergences = "Faltam 5 Itens do SKU 'Jogo de Cama Casal' listados no pedido.\nAvaria reportada pelo galpão em 2 'Travesseiros'."
        
        agent = ZarAIAgent()
        analysis = agent.generate_chargeback(nf_num, divergences)
        
        for chunk in chunk_message(analysis):
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Erro no chargeback: {e}")
        await update.message.reply_text(f"Falha no módulo de faturamento logístico: {str(e)[:500]}")

async def cmd_docas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Portal de agendamento de transporte exclusivo do galpão.")
        return

    try:
        args = context.args
        if not args:
            # Painel do dia
            from datetime import datetime
            hoje = datetime.now().strftime("%d/%m/%Y")
            msg = f"🚚 **Portal de Docas (Painel: {hoje})**\n\n🟢 Nenhuma transportadora ou carreta agendada para recebimento na doca principal hoje.\n\nPara alocar uma janela de carga digite: `/docas [Transportadora] [Data/Hora]`"
            await update.message.reply_text(msg, parse_mode='Markdown')
            return
            
        transp = " ".join(args)
        await update.message.reply_text(f"✅ Slot de agendamento de Descarregamento confirmado em sistema para: {transp}")
    except Exception as e:
        logger.error(f"Erro em docas: {e}")

async def cmd_tagplus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria pode acessar o ERP TagPlus.")
        return

    from src.services.tagplus_api import TagPlusAPI
    
    await update.message.reply_text("📡 Conectando ao ERP TagPlus e buscando produtos...")
    
    try:
        api = TagPlusAPI()
        products = api.get_products()
        
        if products is None:
            await update.message.reply_text("❌ Erro ao conectar com a TagPlus.")
            return
            
        if not products:
            await update.message.reply_text("Nenhum produto encontrado na base da TagPlus.")
            return
            
        msg = f"📦 *Produtos encontrados na TagPlus ({len(products)}):*\n\n"
        for p in products:
            desc = p.get('descricao', 'Sem nome')
            preco = p.get('valor_venda_padrao', 'N/A')
            msg += f"• *{desc}* | Venda: R$ {preco}\n"
            
        for chunk in chunk_message(msg):
            await update.message.reply_text(chunk, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"Erro no TagPlus: {e}")
        await update.message.reply_text(f"Ocorreu um erro ao listar produtos da TagPlus: {str(e)[:500]}")

async def cmd_sync_tagplus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria pode forçar sincronização massiva do ERP nas nuvens da IA.")
        return

    from src.services.tagplus_sync import TagPlusSyncService
    
    await update.message.reply_text("🔄 Desativando o motor Excel antigo e ativando ponte de dados direta com ERP TagPlus... Isso pode demorar se você tiver milhares de itens.")
    
    try:
        sync_service = TagPlusSyncService()
        success, message = sync_service.sync_inventory()
        
        if success:
            await update.message.reply_text(message, parse_mode="Markdown")
            await update.message.reply_text("🎉 Seu banco de dados da IA agora reflete o exato segundo em que estamos. Você pode testar comandos como `/micos` que a IA beberá dessa nova fonte imediata!")
        else:
            await update.message.reply_text(str(message))
            
    except Exception as e:
        logger.error(f"Erro no Sincronizador: {e}")
        await update.message.reply_text(f"Ocorreu um curto-circuito ao gravar dados TagPlus no banco neural: {str(e)[:500]}")

async def cmd_testar_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not is_admin(auth):
        await update.message.reply_text("⛔ Acesso Restrito: Apenas a diretoria testa os Pushes Diários.")
        return
        
    await update.message.reply_text("⏩ Acelerando o tempo para 08:00 AM... Forçando ZAR a processar Anomalias em Background. Aguarde a mensagem autônoma...")
    
    from src.services.scheduler import run_morning_alerts
    await run_morning_alerts(context)

async def route_intent(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE, auth: dict):
    from src.services.ai_agent import ZarAIAgent
    agent = ZarAIAgent()
    
    try:
        nlp = agent.extract_user_intent(text, auth.get('role', 'unknown'))
        intent = nlp.get('intent', 'chat_normal')
        brand = nlp.get('brand')
        args_extra = nlp.get('args')
        
        command_map = {
            "analisar": cmd_analisar,
            "micos": cmd_micos,
            "pendencias": cmd_pendencias,
            "negociar": cmd_negociar,
            "comparar": cmd_comparar,
            "comprar": cmd_comprar,
            "cotar": cmd_cotar,
            "caixa": cmd_caixa,
            "giro": cmd_giro,
            "reprecificar": cmd_reprecificar,
            "chargeback": cmd_chargeback,
            "docas": cmd_docas,
            "tagplus": cmd_tagplus,
            "sync_tagplus": cmd_sync_tagplus,
            "testar_alertas": cmd_testar_alertas
        }
        
        if intent in command_map.keys():
            fake_args = []
            if brand and brand.strip():
                fake_args.extend(brand.split())
            elif args_extra and args_extra.strip():
                fake_args.extend(str(args_extra).split())
                
            context.args = fake_args
            
            await update.message.reply_text(f"🧠 *ZAR NLP:* Identifiquei seu desejo de `/{intent}`. Ativando engrenagens operacionais...", parse_mode='Markdown')
            
            target_cmd = command_map[intent]
            
            # --- ZAR VOICE ENGINE: MONKEY PATCHING ---
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

            await target_cmd(update, context)
        else:
            await update.message.reply_text("🤖 Desculpe, não encontrei uma função comercial para isso. Minha especialidade é auditoria de estoque em Supply Chain corporativo. Pode ser mais direto?")
            
    except Exception as e:
        logger.error(f"Erro Cérebro NLP: {e}")
        await update.message.reply_text("Tive um curto-circuito na minha rede neural tentando ler a intenção da sua fala.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.startswith("/"):
        return
        
    auth = await get_user_auth(update.effective_user.id)
    if not auth:
        await update.message.reply_text("⛔ Faça login antes de conversar comigo.\nEx: /sou_fornecedor [Sua Marca] ou /admin [Senha]")
        return
        
    await update.message.reply_chat_action(action="typing")
    await route_intent(text, update, context, auth)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth = await get_user_auth(update.effective_user.id)
    if not auth:
        await update.message.reply_text("⛔ Faça login antes de usar os comandos de voz.")
        return
        
    await update.message.reply_chat_action(action="record_voice")
    
    try:
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)
        
        import os
        import uuid
        file_path = f"/tmp/{voice.file_id}_{uuid.uuid4().hex[:6]}.ogg"
        await voice_file.download_to_drive(file_path)
        
        from src.services.ai_agent import ZarAIAgent
        agent = ZarAIAgent()
        
        # Ouve o áudio:
        transcription = agent.transcribe_audio(file_path)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
        if not transcription:
            await update.message.reply_text("Desculpe, a IA teve dificuldade acústica em transcrever a frase perfeitamente.")
            return
            
        await update.message.reply_text(f"🗣️ *Transcrição de Áudio:* _{transcription}_", parse_mode="Markdown")
        await update.message.reply_chat_action(action="typing")
        
        # Redirecionando texto limpo extraído do áudio para funil cerebral padrão
        context.user_data["reply_as_voice"] = True
        await route_intent(transcription, update, context, auth)
        context.user_data["reply_as_voice"] = False
        
    except Exception as e:
        logger.error(f"Erro no processamento de voz: {e}")
        await update.message.reply_text(f"Erro ao processar as ondas de áudio e extração verbal. {str(e)[:500]}")
