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
    
    if not doc.file_name.endswith('.xlsx'):
        await update.message.reply_text("Por favor, envie um arquivo no formato Excel (.xlsx).")
        return
        
    await update.message.reply_text("Recebi a planilha! Iniciando processamento e leitura...")
    
    try:
        # Baixar o arquivo do Telegram
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
