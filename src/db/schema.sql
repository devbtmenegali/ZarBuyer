-- Schema de Banco de Dados: Agente ZAR (Supabase)

-- Habilitar a extensão pgcrypto para geração de UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tabela de Produtos (Cadastro Geral)
CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(255) UNIQUE NOT NULL, -- Cód. Mercadoria
    name VARCHAR(255) NOT NULL,       -- Descrição Mercadoria
    unit VARCHAR(50),                 -- UN
    reference VARCHAR(255),           -- Referência
    brand VARCHAR(255),               -- Marca Descriçao
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Tabela de Visões Frequentes de Estoque (Snapshots Diários)
CREATE TABLE IF NOT EXISTS public.inventory_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES public.products(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    sale_price NUMERIC(15,2),         -- Preço Venda
    cost_price NUMERIC(15,2),         -- Preço Custo
    stock_balance NUMERIC(15,2),      -- Saldo Estoque
    total_cost NUMERIC(15,2),         -- Total Custo
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(product_id, snapshot_date) -- Evita duplicar a mesma foto do dia
);

-- Tabela de Fornecedores/Fábricas
CREATE TABLE IF NOT EXISTS public.suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    payment_terms VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Tabela de Pedidos de Compra (Simulada para cruzamento com NotasFiscais)
CREATE TABLE IF NOT EXISTS public.purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID REFERENCES public.suppliers(id),
    order_date DATE NOT NULL,
    expected_delivery DATE,
    status VARCHAR(50) DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Tabela de Notas Fiscais Recebidas (Para auditoria de preços e quantities)
CREATE TABLE IF NOT EXISTS public.invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_order_id UUID REFERENCES public.purchase_orders(id),
    invoice_number VARCHAR(255) NOT NULL,
    received_date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_amount NUMERIC(15,2),
    has_divergences BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Tabela de Itens do Pedido de Compra (Grava cada linha do PDF do Representante)
CREATE TABLE IF NOT EXISTS public.purchase_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_order_id UUID REFERENCES public.purchase_orders(id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(15,2) NOT NULL,
    received_quantity NUMERIC(15,2) DEFAULT 0, -- Rastreia faturamento parcial
    unit_price NUMERIC(15,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Tabela de Itens da Nota Fiscal (Grava cada linha do XML da NFe)
CREATE TABLE IF NOT EXISTS public.invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID REFERENCES public.invoices(id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    ncm VARCHAR(50),
    quantity NUMERIC(15,2) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL, -- Preço unitário real da NF deduzindo descontos
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
