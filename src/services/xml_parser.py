import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

class NfeParser:
    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse(self):
        """
        Lê o XML da NF-e e extrai os itens faturados ignorando complexidades tributárias
        para focar na auditoria direta (Produto, Qtd, Preço Faturado).
        """
        try:
            tree = ET.parse(self.filepath)
            root = tree.getroot()
            
            # O XML da NFe no Brasil tem um namespace padrão obrigatório
            ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
            
            # Procurar se é root ou se está dentro de nfeProc
            infNFe = root.find('.//nfe:infNFe', ns)
            if infNFe is None:
                # Tenta sem namespace caso seja um XML sujo
                infNFe = root.find('.//infNFe')
                ns = {'nfe': ''} # Fallback
                
            if infNFe is None:
                raise ValueError("Tag infNFe não encontrada. Isso é uma NFe válida?")

            # Identificação da Nota
            ide = infNFe.find('nfe:ide', ns)
            nNF = ide.find('nfe:nNF', ns).text if ide is not None and ide.find('nfe:nNF', ns) is not None else "DESCONHECIDO"
            
            # Dados do Emitente (Fábrica)
            emit = infNFe.find('nfe:emit', ns)
            emit_name = emit.find('nfe:xNome', ns).text if emit is not None else "FORNECEDOR"
            
            # Total da Nota
            total = infNFe.find('.//nfe:total/nfe:ICMSTot/nfe:vNF', ns)
            vNF = float(total.text) if total is not None else 0.0

            # Lendo os produtos
            items = []
            for det in infNFe.findall('nfe:det', ns):
                prod = det.find('nfe:prod', ns)
                if prod is not None:
                    name = prod.find('nfe:xProd', ns).text
                    ncm = prod.find('nfe:NCM', ns).text
                    qty = float(prod.find('nfe:qCom', ns).text)
                    unit_price = float(prod.find('nfe:vUnCom', ns).text)
                    
                    items.append({
                        "product_name": name,
                        "ncm": ncm,
                        "quantity": qty,
                        "unit_price": unit_price
                    })

        # Lendo as faturas (Contas a Pagar)
            installments = []
            cobr = infNFe.find('nfe:cobr', ns)
            if cobr is not None:
                for dup in cobr.findall('nfe:dup', ns):
                    nDup = dup.find('nfe:nDup', ns)
                    dVenc = dup.find('nfe:dVenc', ns)
                    vDup = dup.find('nfe:vDup', ns)
                    
                    if dVenc is not None and dVenc.text:
                        installments.append({
                            "installment_number": nDup.text if nDup is not None else "001",
                            "due_date": dVenc.text,
                            "amount": float(vDup.text) if vDup is not None else 0.0
                        })

            return {
                "supplier_name": emit_name,
                "invoice_number": nNF,
                "total_amount": vNF,
                "items": items,
                "installments": installments
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar XML da NF: {e}")
            raise e
