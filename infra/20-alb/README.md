# Papyrus ALB Smoke Test (infra/20-alb)

このディレクトリは、Application Load Balancer (ALB)、Target Group、Listener を最小構成で作成し、Papyrus の Fargate サービスに対して `/healthz` および `/dbcheck` を実行検証するための Terraform 定義を格納している。

ここで作成する ALB/Target Group は本番環境の恒久リソースではない。
CI ワークフロー (`alb-smoke`) において「作成 → テスト → 削除」というサイクルで利用する一時リソースであり、恒常的に残さない前提。

コスト管理上、このリソース群を放置することは禁止。ALB は起動中は課金対象となるため、必ず削除する。

---

## 変数 (`dev.auto.tfvars` の書式)

CI は毎回 `infra/20-alb/dev.auto.tfvars` を動的に生成し、実行後は破棄する。このファイルは Git 管理しない。

生成内容イメージ:

```hcl
vpc_id            = "vpc-xxxxxxxxxxxxxxx"
public_subnet_ids = ["subnet-aaa", "subnet-bbb"] # パブリックサブネット
container_port    = 5000
allow_cidrs       = ["0.0.0.x/0"]
ecs_tasks_sg_id   = "sg-xxxxxxxxxxxxxx"
```

各パラメータの意味:

- `ecs_tasks_sg_id`

  - Papyrus の Fargate タスクに付与される Security Group
  - Target Group のヘルスチェックや、ALB からタスクへの疎通で利用する
- `allow_cidrs`

  - ALB 用 Security Group に対し、どの CIDR からのアクセスを許可するかを定義
  - CI 用途では `["0.0.0.x/0"]` として全開放し、スモークテストを行う
  - 本番運用の ALB では同様の設定は行わない (あくまで検証用 ALB という扱い)

---

## smoke ワークフローの流れ

`alb-smoke` GitHub Actions が実行する処理を説明する。

### 1. プリフライト検証 (アプリおよび DB メタ情報の健全性確認)

まずアプリケーションを読み込み、想定している疎通確認用エンドポイントが定義されているかを検証する。

```bash
python - <<'PY'
from papyrus import create_app
app = create_app()
routes = sorted([r.rule for r in app.url_map.iter_rules()])
print("ROUTES:", routes)
assert "/healthz" in routes
assert "/dbcheck" in routes
PY
```

- `/healthz` および `/dbcheck` が存在しない場合は即座に失敗扱いとし、以降のデプロイ工程には進まない
- CI ログには `ROUTES: ['/','/dbcheck','/healthz', ...]` のようにルーティング一覧が残る

  - このログはアプリケーションビルド時点での健全性証跡として保管する

次に、Secrets Manager と RDS 実体の情報を比較し、接続先情報の不整合 (ドリフト) が発生していないことを検証する。

```bash
SEC_JSON=$(aws secretsmanager get-secret-value --secret-id papyrus/prd/db --query SecretString --output text)
EP=$(aws rds describe-db-instances --db-instance-identifier papyrus-pg16-dev --query 'DBInstances[0].Endpoint.Address' --output text)
PORT=$(aws rds describe-db-instances --db-instance-identifier papyrus-pg16-dev --query 'DBInstances[0].Endpoint.Port' --output text)

SEC_HOST=$(echo "$SEC_JSON" | jq -r .host)
SEC_PORT=$(echo "$SEC_JSON" | jq -r .port)

test "$SEC_HOST" = "$EP"   || { echo "FATAL: RDS endpoint drift"; exit 1; }
test "$SEC_PORT" = "$PORT" || { echo "FATAL: RDS port drift"; exit 1; }
```

- Secrets Manager 側の `host` / `port` と、実際の RDS のエンドポイントおよびポート番号が一致しているかを確認する
- ここで差異がある場合は、DB 接続先情報が正しくないと判断し、そのイメージは本番系の経路に進ませない

  - 例として、Secrets Manager 上の `host` にタイプミスがある場合などを検知する

これら 2 つのチェックにより、

- アプリケーションが必要なヘルスチェック用エンドポイントを保持していること
- DB 接続先メタ情報 (Secrets Manager と RDS) が破綻していないこと
  の両方をビルド時点で保証する。

### 2. Terraform apply による ALB セットアップ

```bash
cd infra/20-alb
terraform init -input=false -upgrade=false
terraform validate
terraform apply -auto-approve -var-file=dev.auto.tfvars
```

このステップで作成されるリソースは以下の通り:

- Application Load Balancer (`papyrus-alb`)
- ALB 用 Security Group (`papyrus-alb-sg`)
- Target Group (`papyrus-tg`, target-type=ip, port=5000, `health_check.path="/healthz"`)
- HTTP Listener (:80 → 上記 Target Group)

Terraform の実行結果は `terraform.tfstate` として残り、CI はこれをアーティファクトとして保存する。
合わせて `terraform apply` のログも証跡として取得する。

### 3. ECS タスク情報の取得

Papyrus の ECS サービスはあらかじめ 1 タスク (scale=1) が稼働している前提とする。
CI はそのタスクの ENI を調べ、タスクのコンテナが持つプライベート IP を取得する。

例:

```bash
TASK_ARN=$(aws ecs list-tasks \
  --cluster papyrus-ecs-prd \
  --service-name papyrus-task-service \
  --desired-status RUNNING \
  --query 'taskArns[0]' --output text)

TASK_IP=$(aws ecs describe-tasks \
  --cluster papyrus-ecs-prd \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' \
  --output text)
```

ここで取得した `TASK_IP:5000` が Target Group に登録される対象となる。

### 4. Target Group への登録とヘルスチェック

```bash
TG_ARN=$(terraform output -raw tg_arn)
aws elbv2 register-targets \
  --target-group-arn "$TG_ARN" \
  --targets "Id=$TASK_IP,Port=5000"

aws elbv2 wait target-in-service \
  --target-group-arn "$TG_ARN" \
  --targets "Id=$TASK_IP,Port=5000"
```

`aws elbv2 wait target-in-service` が完了することは、以下の事実を示す:

- ALB から ECS タスクへの疎通が正常に行われていること
- Target Group が設定しているヘルスチェックパス (`/healthz`) に対し、HTTP 200 が返却されていること
- ECS タスク上のアプリケーションサーバ (Gunicorn 等) が起動済みであること

この時点で「タスクが ALB 配下で正常応答している」という疎通証跡が取得できる。

### 5. `/healthz` と `/dbcheck` の動作検証

```bash
DNS=$(terraform output -raw alb_dns_name)

mkdir -p evidence

echo "[INFO] curl /healthz" | tee "evidence/$(date +%Y%m%d_%H%M%S)_healthz.log"
curl -si "http://$DNS/healthz" \
  | tee -a "evidence/$(date +%Y%m%d_%H%M%S)_healthz.log" || true

echo "[INFO] curl /dbcheck" | tee "evidence/$(date +%Y%m%d_%H%M%S)_dbcheck.log"
curl -si "http://$DNS/dbcheck" \
  | tee -a "evidence/$(date +%Y%m%d_%H%M%S)_dbcheck.log" || true
```

期待されるレスポンス:

- `/healthz`

  - `HTTP/1.1 200 OK ... {"ok":true}`
- `/dbcheck`

  - `HTTP/1.1 200 OK ... {"inserted":true}`

`/dbcheck` はアプリケーション内部でデータベース接続プールを経由し、`papyrus_schema.products` に対して
`INSERT ... ON CONFLICT DO NOTHING` を実行する。
これは「ALB 経由のリクエストがアプリケーションに到達し、そこから RDS への書き込みが行えている」ことの実証になる。

本ステップで取得した `-_healthz.log` および `-_dbcheck.log` は CI のアーティファクトとして保存する。
将来的に「実際に ALB 経由でアプリケーションが稼働し、DB トランザクションも成立していた」という説明を行う際の根拠となる。

### 6. Terraform destroy によるリソース削除 (コスト回避)

最後に、ALB / Target Group / Listener / Security Group を削除する。

```bash
terraform destroy -auto-approve -var-file=dev.auto.tfvars
```

必須手順。
Application Load Balancer は稼働中コストが発生し続けるため、検証目的のリソースは必ず削除する。
CI は削除処理のログも取得し、`destroy` が正常に完了したかを追跡できるようにしている。

---

## コストおよび運用上の注意点

- Application Load Balancer を恒久的に残さないこと

  - `terraform destroy` を実施しない場合、不要な ALB が稼働し続け、継続的な課金が発生する

- Security Group (`papyrus-alb-sg`) は CI 実行ごとに `CreateSecurityGroup` される設計のため、削除に失敗した残骸があると `InvalidGroup.Duplicate` によって `plan/apply` が失敗する

  - 「削除済みと思っていたが実際には残っている」ケースでは、この残存 SG を手動で除去する

- CI 実行ロールには、ALB / ELBv2 / EC2 / ECS / RDS / Secrets Manager への必要な権限が付与されている必要がある

  - 例:

    - `elasticloadbalancing:-` (ALB/Target Group/Listener の作成・登録・状態確認等)
    - `ec2:CreateSecurityGroup`, `ec2:AuthorizeSecurityGroupIngress`, `ec2:DeleteSecurityGroup`
    - `ecs:ListTasks`, `ecs:DescribeTasks`
    - `rds:DescribeDBInstances`
    - `secretsmanager:GetSecretValue`

---

## 証跡の管理

CI の成果物として、以下をアーティファクト化し、`docs/evidence/` に保管する想定:

- Terraform の状態およびログ

  - `infra/20-alb/terraform.tfstate`
  - `terraform apply` / `terraform destroy` のログ
- `/healthz` および `/dbcheck` 実行結果ログ

  - `-_healthz.log`: `/healthz` が HTTP 200 かつ `{"ok":true}` を返すこと
  - `-_dbcheck.log`: `/dbcheck` が HTTP 200 かつ `{"inserted":true}` を返すこと

これらは「ALB 経由でリクエストを正常に処理できる」「実DBに対してトランザクションを書き込める」という事実を示すための技術的証跡であり、外部公開用ドキュメント (ポートフォリオ / 記事等) に転用できる内容となっている。