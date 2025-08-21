

### ディレクトリ構成

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
    ├── config_runtime.py
    ├── templates/
    └── static/
```

### 開発環境起動時

```bash
docker compose --env-file .env.dev build --no-cache --progress=plain
```