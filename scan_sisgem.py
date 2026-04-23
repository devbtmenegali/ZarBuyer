import pyodbc

conn_str = "DRIVER={SQL Server};SERVER=localhost;DATABASE=sisgem;Trusted_Connection=yes;"

query = """
SELECT TABLE_NAME, COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

print("Conectando ao núcleo do ERP Sisgem...")

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute(query)
    
    resultados = cursor.fetchall()
    
    # Agrupa por tabela
    tabelas = {}
    for row in resultados:
        tabela = row[0]
        coluna = row[1]
        if tabela not in tabelas:
            tabelas[tabela] = []
        tabelas[tabela].append(coluna)
        
    relatorio = "=== MAPEAMENTO ABSOLUTO DE TODAS AS TABELAS DO SISGEM ===\n"
    relatorio += "Isso contém o layout inteiro do ERP. Guarde este arquivo com carinho!\n\n"
    for tab, cols in tabelas.items():
        # Como vão ser muitas tabelas, vamos formatar elas mais compactas:
        relatorio += f"[{tab}] -> Colunas: " + ", ".join(cols) + "\n\n"
        
    caminho = "tabelas_sisgem.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(relatorio)
        
    print(f"Sucesso! Mapeamento salvo em: {caminho}")

except Exception as e:
    print(f"Erro fatal: {e}")
