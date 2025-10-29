## Papyrus

RDSから商品情報を取得し、GUI上の納品リストから納品書をPDF出力するポートフォリオ。

[![ECR Push](https://github.com/Nickelth/papyrus-invoice/actions/workflows/ecr-push.yml/badge.svg)](../../actions)
[![ECS Deploy](https://github.com/Nickelth/papyrus-invoice/actions/workflows/ecs-deploy.yml/badge.svg)](../../actions)
[![ECS Scaling](https://github.com/Nickelth/papyrus-invoice/actions/workflows/ecs-scale.yml/badge.svg)](../../actions)
[![ALB Smoke](https://github.com/Nickelth/papyrus-invoice/actions/workflows/alb-smoke.yml/badge.svg)](../../actions)

### ルール

- README は**300行未満**、図鑑は docs。
- 詳細なコマンド羅列は`docs/(date %Y%m%d).md`に置く。
- 実行結果スクショや長表は S3 の成果物か `docs/` にリンクだけ。
- 変更履歴は **CHANGELOG** 系統に一元化。README の「変更履歴」セクションは禁止。

### ディレクトリ構成

```plaintext
papyrus-invoice/
├── Dockerfile
├── docker-compose.yml
├── run.py
├── init.sql
├── requirements.txt
├── .env.dev
├── .env.prd
├── infra/
│   ├── 10-rds/
│   │   ├── .terraform.lock.hcl
│   │   ├── main.tf
│   │   ├── outputs.tf
│   │   ├── providers.tf
│   │   ├── variables.tf
│   │   └── versions.tf
│   └── 20-alb/
│       ├── .terraform.lock.hcl
│       ├── main.tf
│       └── outputs.tf
├── papyrus/
│   ├── blueprints/
│   │   ├── dbcheck.py
│   │   └── healthz.py
│   ├── __init__.py
│   ├── api_routes.py
│   ├── auth_routes.py
│   ├── auth.py
│   ├── db.py
│   ├── routes.py
│   └── config_runtime.py
├── templates/
├── static/
└── docs/
    └── evidence/
```

### 開発環境起動時

```bash
docker compose --env-file .env.dev build --no-cache --progress=plain
```

### CLoudWatch Alarm IaC監査

リポジトリクローン後、CloudShell上で入力

CLoudWatch Alarm監査体制をIaCで構築

- ECS メモリ >80% (平均2/5分)
- ALB 5xx% >1 (Sum 2/5分)
- TargetResponseTime p90 >1.5s

```bash
cd infra/30-monitor
terraform init -input=false
terraform validate
terraform plan   -var-file=dev.tfvars | tee "$EVID/$(date +%Y%m%d_%H%M%S)_monitor_tf_plan.log"
terraform apply  -var-file=dev.tfvars -auto-approve \
  | tee "$EVID/$(date +%Y%m%d_%H%M%S)_monitor_tf_apply.log"
```

### Github Actions CI/CD

- `ecr-push.yml`: `master`ブランチデプロイ時に自動実行、ECRイメージを更新。
- `ecs-deploy.yml`: Actionsで任意実行。ECSタスクをdesire=1にしてサービス起動。
- `ecs-scale.yml`: Actionsで任意実行。ECSタスクをdesire=0にしてサービス起動。
- `alb-smoke.yml`: Actionsで任意実行。ALB/TG/SGを作成→疎通→破壊。

### 完成定義

- [x] **ECS→RDS の疎通 OK**（INSERT 0 1 が証跡に残る） 

- [x] **最小スキーマ適用済み**（init.sql 投入） 

- [ ] **観測の入口**として CloudWatch Logs に構造化ログが出ている（JSON1行） 

- [x] **IaC 薄切り**（RDS/SG/ParameterGroup だけTerraform化。完全Importは後回し） 

- [x] **証跡**：psql 接続ログ、SG設定SS、アプリログに接続成功 

- [x] **Parameter Group変更の反映証跡**(再起動含む)、トランザクションのログ1件、再試行ロジックの有無 

- [ ] **CLI履歴の証跡化**: scriptコマンドかbash -xログ、加えてCloudTrail + Configを記事に添える