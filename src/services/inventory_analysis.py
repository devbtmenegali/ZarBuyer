from src.db.supabase_client import get_supabase_client
from datetime import datetime

class InventoryDataService:
    def __init__(self):
        self.supabase = get_supabase_client()

    def get_brand_summary(self, brand: str = None) -> list:
        # Pega de todos os tempos ordenado
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(sku, name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('stock_balance', desc=True) \
            .limit(300)
            
        resp = query.execute()
        data = resp.data
        
        # Filtra marca e mantém apenas o registro mais novo por produto
        seen = set()
        unique_latest_data = []
        for row in data:
            if not row['products']: continue
            if brand and brand.lower() not in str(row['products'].get('brand', '')).lower(): continue
            
            p_name = row['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                unique_latest_data.append(row)
                if len(unique_latest_data) >= 100: break
            
        simplified = []
        for row in unique_latest_data:
            simplified.append({
                "Nome": row['products']['name'],
                "Marca": row['products']['brand'],
                "Estoque_Qtd": row['stock_balance'],
                "Custo_Total": row['total_cost'],
                "Preco_Venda": row['sale_price']
            })
        return simplified

    def get_highest_stock_items(self) -> list:
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('total_cost', desc=True) \
            .limit(300)
            
        resp = query.execute()
        
        # Manter apenas a última ocorrência no banco para evitar somar 2 dias do mesmo produto
        seen = set()
        unique_latest_data = []
        for r in resp.data:
            if not r['products']: continue
            p_name = r['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                unique_latest_data.append({
                    "Nome": p_name,
                    "Quantidade": r['stock_balance'],
                    "Valor_Parado": r['total_cost']
                })
                if len(unique_latest_data) >= 50: break
                
        return unique_latest_data

    def get_low_stock_items(self, brand: str = None) -> list:
        # Busca produtos com estoque menor que 5 para alertar reposição
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('stock_balance', asc=True) \
            .limit(300)
            
        resp = query.execute()
        
        seen = set()
        low_stock_data = []
        for row in resp.data:
            if not row['products']: continue
            if brand and brand.lower() not in str(row['products'].get('brand', '')).lower(): continue
            
            p_name = row['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                # Consider low stock if balance is <= 5
                if float(row['stock_balance']) <= 5:
                    low_stock_data.append({
                        "Nome": p_name,
                        "Marca": row['products']['brand'],
                        "Estoque_Atual": row['stock_balance'],
                        "Custo_Atual": row['cost_price'],
                        "Preco_Venda": row['sale_price']
                    })
                if len(low_stock_data) >= 100: break
                
        return low_stock_data

    def compare_similar_products(self, keyword: str) -> list:
        # Busca produtos com snapshot recente
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(1000)
            
        resp = query.execute()
        
        seen = set()
        comparison_data = []
        for row in resp.data:
            if not row['products']: continue
            p_name = str(row['products'].get('name', ''))
            
            # Filtra por keyword no nome (ex: "Travesseiro")
            if keyword.lower() in p_name.lower():
                if p_name not in seen:
                    seen.add(p_name)
                    comparison_data.append({
                        "Nome": p_name,
                        "Marca": row['products'].get('brand', 'N/A'),
                        "Custo": row['cost_price'],
                        "Preco_Venda": row['sale_price'],
                        "Estoque": row['stock_balance']
                    })
                if len(comparison_data) >= 50: break
                
        return comparison_data

    def get_supplier_opportunities(self, brand: str) -> list:
        # Busca os produtos daquela marca ordenados por data
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(1000)
            
        resp = query.execute()
        
        seen = set()
        opportunities = []
        for row in resp.data:
            if not row['products']: continue
            p_brand = str(row['products'].get('brand', ''))
            
            if brand.lower() in p_brand.lower():
                p_name = row['products'].get('name', '')
                if p_name not in seen:
                    seen.add(p_name)
                    # Consideramos oportunidade se o estoque for menor/igual a 30 (indicativo de alto giro se já esteve mais alto)
                    if float(row['stock_balance']) <= 30:
                        opportunities.append({
                            "Nome": p_name,
                            "Estoque": row['stock_balance'],
                            "Preco_Venda": row['sale_price']
                        })
                if len(opportunities) >= 20: break
                
        return opportunities

    def analyze_inventory_turnover(self, brand: str) -> list:
        # Puxamos limitando a 3000 pra dar folga aos historicos
        query = self.supabase.table('inventory_snapshots') \
            .select('product_id, snapshot_date, stock_balance, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(3000)
            
        resp = query.execute()
        
        from collections import defaultdict
        product_history = defaultdict(list)
        
        for row in resp.data:
            if not row['products']: continue
            r_brand = str(row['products'].get('brand', ''))
            if brand.lower() not in r_brand.lower(): continue
            
            p_name = row['products'].get('name', 'N/A')
            product_history[p_name].append({
                "date": row['snapshot_date'],
                "balance": row['stock_balance']
            })
            
        turnover_data = []
        for p_name, history in product_history.items():
            if len(history) < 2:
                continue 
                
            latest = history[0]
            oldest = history[-1]
            
            from datetime import datetime
            fmt = "%Y-%m-%d"
            try:
                d_latest = datetime.strptime(latest['date'][:10], fmt)
                d_oldest = datetime.strptime(oldest['date'][:10], fmt)
                
                delta_days = (d_latest - d_oldest).days
                if delta_days == 0:
                    continue
                    
                diff_balance = float(oldest['balance']) - float(latest['balance'])
                
                if diff_balance > 0:
                    daily_velocity = diff_balance / delta_days
                    days_remaining = float(latest['balance']) / daily_velocity if daily_velocity > 0 else 999
                else:
                    daily_velocity = 0
                    days_remaining = 999
                    
            except Exception as e:
                continue
                
            turnover_data.append({
                "Nome": p_name,
                "Estoque_Atual": latest['balance'],
                "Venda_Dia": round(daily_velocity, 2),
                "Dias_Cobertura": round(days_remaining)
            })
            
        turnover_data.sort(key=lambda x: x['Dias_Cobertura'])
        return turnover_data[:30]

    def get_repricing_opportunities(self, brand: str) -> list:
        # 1. Pega os produtos atuais da marca para ter o custo base e preço de venda atual
        query = self.supabase.table('inventory_snapshots') \
            .select('product_id, cost_price, sale_price, stock_balance, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(1000)
            
        resp = query.execute()
        
        current_catalog = {}
        for row in resp.data:
            if not row['products']: continue
            p_brand = str(row['products'].get('brand', ''))
            if brand.lower() not in p_brand.lower(): continue
            
            p_name = row['products'].get('name', 'N/A')
            if p_name not in current_catalog:
                current_catalog[p_name] = {
                    "cost_price": float(row['cost_price']),
                    "sale_price": float(row['sale_price']),
                    "stock_balance": row['stock_balance']
                }
                
        # 2. Busca as ultimas NFes da fábrica
        sup_lookup = self.supabase.table('suppliers').select('id, name').ilike('name', f"%{brand[:10]}%").execute()
        if not sup_lookup.data:
            return []
            
        sup_ids = [s['id'] for s in sup_lookup.data]
        
        # Pega pedidos para saber invoice
        po_resp = self.supabase.table('purchase_orders').select('id').in_('supplier_id', sup_ids).execute()
        if not po_resp.data: return []
        po_ids = [po['id'] for po in po_resp.data]
        
        inv_resp = self.supabase.table('invoices').select('id').in_('purchase_order_id', po_ids).execute()
        if not inv_resp.data: return []
        inv_ids = [i['id'] for i in inv_resp.data]
        
        # 3. Pega os itens dessas NFes
        items_resp = self.supabase.table('invoice_items') \
            .select('product_name, unit_price, invoice_id') \
            .in_('invoice_id', inv_ids) \
            .execute()
            
        new_costs = {}
        # Assume que o maior ID = NFe mais recente
        for item in sorted(items_resp.data, key=lambda x: x['invoice_id'], reverse=True):
            name = item['product_name']
            if name not in new_costs:
                new_costs[name] = float(item['unit_price'])
                
        # 4. Compara
        repricing_list = []
        for p_name, new_cost in new_costs.items():
            catalog_item = None
            # Busca nome exato ou contido (match rudimentar)
            for c_name, c_data in current_catalog.items():
                if p_name.lower() in c_name.lower() or c_name.lower() in p_name.lower():
                    catalog_item = c_data
                    break
                    
            if catalog_item:
                old_cost = catalog_item['cost_price']
                
                # Se custo novo for maior que o base estocado (Inflação)
                if new_cost > old_cost and old_cost > 0:
                    diff_pct = ((new_cost - old_cost) / old_cost) * 100
                    
                    # Calcula markup antigo e projeta o novo preco
                    markup_pct = ((catalog_item['sale_price'] - old_cost) / old_cost) if old_cost > 0 else 0
                    suggested_price = new_cost * (1 + markup_pct)
                    
                    repricing_list.append({
                        "Produto": p_name,
                        "Custo_Antigo": old_cost,
                        "Custo_NFe_Novo": new_cost,
                        "Inflacao_PCT": round(diff_pct, 2),
                        "Preco_Venda_Atual": catalog_item['sale_price'],
                        "Novo_Preco_Sugerido": round(suggested_price, 2)
                    })
                    
        return repricing_list[:40]
