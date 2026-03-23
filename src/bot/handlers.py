import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.services.excel_parser import ExcelInventoryParser
from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Sou o Agente ZAR. Envie sua planilha diária de Estoque Geral (.xlsx) aqui no chat para que eu processe."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        from src.services.inventory_analysis import InventoryDataService
        from src.services.ai_agent import ZarAIAgent
        
        args = context.args
        brandFilter = " ".join(args) if args else None
        
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
    try:
        from src.db.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        args = context.args
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
