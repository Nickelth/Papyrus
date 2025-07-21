CREATE SCHEMA IF NOT EXISTS papyrus_schema;

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(20) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    unit_price INTEGER NOT NULL,
    note TEXT
);

INSERT INTO papyrus_schema.products (sku, name, unit_price, note)
VALUES
('KB-001', 'メカニカルキーボード', 12000, '青軸'),
('EM-002', 'エルゴノミクスマウス', 8500, 'Bluetooth対応'),
('MO-003', '24インチモニター', 19800, 'HDMI・DP両対応'),
('MO-004', '27インチモニター', 27800, '4K'),
('MO-005', '32インチモニター', 59800, '4K'),
('ST-006', 'デスク用スタンド', 3200, NULL);
('LN-007','LANケーブル', 3400, NULL),
