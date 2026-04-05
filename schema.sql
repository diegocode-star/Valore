-- Ejecuta este script UNA VEZ en el SQL Editor de Supabase
-- (Dashboard → SQL Editor → New query → pegar y ejecutar)

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT to_char(CURRENT_DATE, 'YYYY-MM-DD')
);

-- Migración para tablas existentes (ejecutar si la tabla ya existía):
-- ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS created_at TEXT;

CREATE TABLE IF NOT EXISTS transacciones (
    id BIGSERIAL PRIMARY KEY,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    categoria TEXT NOT NULL,
    descripcion TEXT,
    monto DOUBLE PRECISION NOT NULL,
    cuenta TEXT DEFAULT 'Efectivo',
    user_id BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS portafolio (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL,
    cantidad DOUBLE PRECISION NOT NULL,
    valor_unitario DOUBLE PRECISION NOT NULL,
    fecha TEXT NOT NULL,
    user_id BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS deudas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL,
    deuda_inicial DOUBLE PRECISION NOT NULL,
    saldo DOUBLE PRECISION NOT NULL,
    tasa_interes DOUBLE PRECISION NOT NULL DEFAULT 0,
    pago_minimo DOUBLE PRECISION NOT NULL DEFAULT 0,
    fecha_inicio TEXT NOT NULL,
    user_id BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pagos_deuda (
    id BIGSERIAL PRIMARY KEY,
    deuda_id BIGINT NOT NULL,
    fecha TEXT NOT NULL,
    monto DOUBLE PRECISION NOT NULL,
    nota TEXT
);

CREATE TABLE IF NOT EXISTS metas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    objetivo DOUBLE PRECISION NOT NULL,
    actual DOUBLE PRECISION NOT NULL DEFAULT 0,
    fecha_limite TEXT,
    emoji TEXT NOT NULL DEFAULT '🎯',
    user_id BIGINT NOT NULL DEFAULT 1
);
