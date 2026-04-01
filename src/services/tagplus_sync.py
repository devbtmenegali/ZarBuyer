import logging
from datetime import datetime
from typing import List, Dict

from src.services.tagplus_api import TagPlusAPI
from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class TagPlusSyncService:
    def __init__(self):
        self.api = TagPlusAPI()
        self.supabase = get_supabase_client()
        
    def sync_inventory(self):
        """
        Busca os produtos do TagPlus em tempo real e insere nas tabelas do ZAR (Products e Snapshots)
        atuando virtualmente como se fosse o antigo upload do Excel.
        """
        logger.info("Iniciando sincronização estrutural com TagPlus...")
        products_raw = self.api.get_products()
        
        if products_raw is None:
            logger.warning("Erro de falha crítica na API ao conectar com a TagPlus.")
            return False, "❌ Autenticação ou conexão com a TagPlus falhou."
            
        if not products_raw:
            return True, "⚠️ Conexão OK, mas a TagPlus retornou 0 produtos."
            
        logger.info(f"Integrando {len(products_raw)} produtos vindos do ERP...")
        
        products_batch = []
        for p in products_raw:
            sku = p.get('codigo') or str(p.get('id'))
            name = p.get('descricao', 'Produto sem Nome')
            
            products_batch.append({
                "sku": sku,
                "name": name,
                "unit": "UN", 
                "reference": str(p.get('id')),
                "brand": "TagPlus" # Pode ser atualizado depois para extrair nomes de Marcas reais
            })
            
        chunk_size = 500
        
        # 1. Bulk Upsert na tabela PRODUCTS
        if products_batch:
            for i in range(0, len(products_batch), chunk_size):
                self.supabase.table('products').upsert(products_batch[i:i+chunk_size], on_conflict="sku").execute()
                
        # 2. Resgatar os UUIDs internos do banco mapeados pelos SKUs
        skus = [p["sku"] for p in products_batch]
        product_map = {}
        for i in range(0, len(skus), chunk_size):
            resp = self.supabase.table('products').select("id, sku").in_("sku", skus[i:i+chunk_size]).execute()
            for row in resp.data:
                product_map[row["sku"]] = row["id"]
                
        # 3. Preparar a fotografia diária (Snapshot)
        today_date = datetime.now().strftime('%Y-%m-%d')
        snapshots_batch = []
        
        for p in products_raw:
            sku = p.get('codigo') or str(p.get('id'))
            p_id = product_map.get(sku)
            
            if p_id:
                # O ERP TagPlus não tem nomes uniformes de campos para todas contas, assumindo genéricos
                sale_price = float(p.get('valor_venda_padrao', 0) or 0)
                cost_price = float(p.get('valor_custo_padrao', 0) or 0)
                
                # Para evitar erros se o estoque não for rastreado no payload simples de /produtos
                stock = float(p.get('estoque_atual', p.get('estoque', 0)) or 0)
                
                snapshots_batch.append({
                    "product_id": p_id,
                    "sale_price": sale_price,
                    "cost_price": cost_price,
                    "stock_balance": stock,
                    "total_cost": stock * cost_price,
                    "snapshot_date": today_date
                })
                
        # 4. Bulk Insert dos Snapshots (On Conflict Update)
        if snapshots_batch:
            for i in range(0, len(snapshots_batch), chunk_size):
                self.supabase.table('inventory_snapshots').upsert(snapshots_batch[i:i+chunk_size], on_conflict="product_id, snapshot_date").execute()
                
        return True, f"✅ O ZAR sincronizou **{len(snapshots_batch)} produtos** vivos da TagPlus com o banco de inteligência em nuvem!"
