## ローカル環境依存関係


### 1. Python本体バージョン
python3 3.12.3

### 2. 仮想環境(venv)
``` bash
python3 -m venv venv
source venv/bin/activate
```

### 3. pipパッケージ
requirements.txtを参照
``` bash
pip install -r requirements.txt
```

### 4. .envファイル
``` bash
cp .env.sample .env
# Then, edit .env and fill in your DB_PASSWORD etc.
```

### 5. PostgreSQLの初期化スクリプト
``` bash
psql -U postgres -d papyrus_db -f init.sql
```

### 6. 起動方法
``` bash
cd ~/papy
python3 -m venv venv
pip install -r requirements.txt
source venv/bin/activate
python run.py
```

```plaintext
your_project/
├── Dockerfile
├── docker-compose.yml
├── run.py
├── .env.dev
├── .env.prd
└── papyrus/
    ├── __init__.py
    ├── api_routes.py
    ├── auth_routes.py
    ├── auth.py
    ├── db.py
    ├── routes.py
    ├── templates/
    └── static/
```