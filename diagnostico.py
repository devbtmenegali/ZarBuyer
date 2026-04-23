from dotenv import load_dotenv
load_dotenv()

# Configurações do seu banco via .env (MAIS SEGURO)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Erro ao inicializar Supabase: {e}")
    exit(1)

tabelas_foco = [
    "mercadoria_cad", 
    "pv_movto", 
    "marcas", 
    "clientes",
    "vendedor",
    "fornecedores",
    "grupos",
    "cx_movto"
]

relatorio_txt = "=== MAPA DE DADOS DO ERP (DIAGNÓSTICO ZAR) ===\n\n"

for tabela in tabelas_foco:
    try:
        print(f"Buscando amostra da tabela: {tabela}...")
        res = supabase.table(tabela).select("dados").order("ultima_atualizacao", desc=True).limit(1).execute()
        
        relatorio_txt += f"TABELA: {tabela.upper()}\n"
        if res.data and len(res.data) > 0:
            dados = res.data[0].get("dados", {})
            chaves = list(dados.keys())
            
            # Formatação amigável
            relatorio_txt += f"  Status: OK. (Possui {len(chaves)} colunas internas vindas do ERP)\n"
            relatorio_txt += f"  Campos Encontrados:\n"
            
            for k, v in dados.items():
                tipo_valor = type(v).__name__
                # Corta o valor pra não ficar gigante e desconfigurado
                str_valor = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
                relatorio_txt += f"    - {k} ({tipo_valor}): Exemplo -> {str_valor}\n"
        else:
            relatorio_txt += "  Status: VAZIA. Nenhum dado encontrado nessa tabela.\n"
            
        relatorio_txt += "-" * 50 + "\n\n"
        
    except Exception as e:
        relatorio_txt += f"TABELA: {tabela.upper()}\n"
        relatorio_txt += f"  Status: ERRO - {str(e)}\n"
        relatorio_txt += "-" * 50 + "\n\n"

caminho_saida = "/Users/brunomenegali/Downloads/ZarBuyer/diagnostico_tabelas.txt"
with open(caminho_saida, "w", encoding="utf-8") as f:
    f.write(relatorio_txt)

print(f"\n✅ Concluído! O relatório com Dicionário de Dados do seu ERP foi salvo em: {caminho_saida}")
