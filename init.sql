-- init.sql
\set ON_ERROR_STOP on

-- ※ POSTGRES_DB を使ってるならここで CREATE DATABASE は不要
CREATE SCHEMA IF NOT EXISTS papyrus_schema;

CREATE TABLE IF NOT EXISTS papyrus_schema.products (
  sku        text PRIMARY KEY,
  name       text NOT NULL,
  unit_price integer NOT NULL,
  note       text
);

INSERT INTO papyrus_schema.products (sku, name, unit_price, note) VALUES
  ('KB-001', 'メカニカルキーボード', 12000, '青軸'),
  ('EM-002', 'エルゴノミクスマウス', 8500, 'Bluetooth対応'),
  ('MO-003', '24インチモニター', 19800, 'HDMI・DP両対応'),
  ('MO-004', '27インチモニター', 27800, '4K'),
  ('MO-005', '32インチモニター', 59800, '4K'),
  ('ST-006', 'デスク用スタンド', 3200, NULL)
ON CONFLICT (sku) DO NOTHING;
