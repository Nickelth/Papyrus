## Papyrus

scikit-learn + Pipeline で表形式MLを**学習→成果物→推論API→コンテナ**まで最短導線で通すポートフォリオ。

[![ECR Push](https://github.com/Nickelth/Papyrus/actions/workflows/ecr-push.yml/badge.svg)](../../actions)
[![ECS Deploy](https://github.com/Nickelth/Papyrus/actions/workflows/ecs-deploy.yml/badge.svg)](../../actions)
[![ECS Scaling](https://github.com/Nickelth/Papyrus/actions/workflows/ecs-scale.yml/badge.svg)](../../actions)

## ルール

- README は**300行未満**、図鑑は docs。
- 詳細なコマンド羅列は `docs/training.md` と `docs/ops.md` に置く。
- 実行結果スクショや長表は S3 の成果物か `docs/` にリンクだけ。
- 変更履歴は **CHANGELOG** 系統に一元化。README の「変更履歴」セクションは禁止。

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

### 完成定義

[ ] **ECS→RDS の疎通 OK**（INSERT 0 1 が証跡に残る） 
[ ] **最小スキーマ適用済み**（schema.sql 投入） 
[ ] **観測の入口**として CloudWatch Logs に構造化ログが出ている（JSON1行） 
[ ] **IaC 薄切り**（RDS/SG/ParameterGroup だけTerraform化。完全Importは後回し） 
[ ] **証跡**：psql 接続ログ、SG設定SS、アプリログに接続成功 
[ ] **Parameter Group変更の反映証跡**(再起動含む)、トランザクションのログ1件、再試行ロジックの有無 
[ ] **CLI履歴の証跡化**: scriptコマンドかbash -xログ、加えてCloudTrail + Configを記事に添える