# Papyrus RDS (infra/10-rds)

Papyrus アプリケーションで使用する最小構成の RDS (PostgreSQL) を Terraform で管理するディレクトリ。
目的は以下の 2 点:

- ECS Fargate 上のコンテナから RDS に対して TLS 経由で書き込みが行えることを確認する
- その手順と証跡を再現可能な形で残す

このディレクトリは、本番環境で恒久的に維持するコンポーネント (RDS インスタンス本体、Security Group、Parameter Group 等) を管理する想定。
原則として `terraform destroy` は実施しない。

---

## 構成要素

- DB インスタンス

  - エンジン: PostgreSQL 16 (`db.t4g.micro`)
  - パブリックアクセス: 無効 (プライベートサブネットのみ)
  - マスタユーザ: `papyrus`
  - DB 名: `papyrus`
  - 自動バックアップ保持期間: 1日
  - 暗号化: 有効
  - Final snapshot: 取得しない (開発都合)
  - `apply_immediately = true` によりパラメータ変更を即時適用

- DB Subnet Group

  - `private_subnet_ids` で指定した 2 つのプライベートサブネットを束ねる

- Security Group (RDS 用 SG)

  - Inbound 5432/TCP を、ECS タスク用 SG (`ecs_tasks_sg_id`) のみ許可
  - 任意の CIDR (例: `0.0.0.x/0`) は許可しない

- Parameter Group

  - `rds.force_ssl = 1`

    - RDS への接続を必ず SSL/TLS 経由に制限
    - 平文接続は拒否される
  - この変更は再起動後に有効化されるため、RDS インスタンスを再起動して反映済み

    - 再起動タイムスタンプは証跡ファイルとして保存 (例: `20251017_081500_papyrus_tf_apply.log`)

---

## 変数 (`dev.tfvars` の例)

`dev.tfvars` は `.gitignore` 済みで、個人環境 (例: CloudShell) のみで保持する。例:

```hcl
region             = "us-west-2"
name_prefix        = "papyrus"
db_username        = "papyrus"
db_password        = "sample-password"
vpc_id             = "vpc-xxxxxxxxxxxxxxxxxx"
private_subnet_ids = ["subnet-xxxxxxxxxxxxxxxxxx", "subnet-xxxxxxxxxxxxxxxxxx"]
ecs_tasks_sg_id    = "sg-xxxxxxxxxxxxxxxxxx"
```

重要な点:

- `ecs_tasks_sg_id` は、ECS (Fargate) のタスクに割り当てる Security Group。RDS 側では、この SG からの 5432/TCP のみ受け入れる
- `db_password` は Secrets Manager 上の `papyrus/prd/db` にも格納される

  - ここが不整合になるとアプリケーションからの接続が失敗する
  - CI のプリフライトでドリフト検知を行う (後述)

---

## 運用フロー

### 1. plan / apply の実行と証跡化

```bash
REGION=us-west-2
EVID=~/papyrus-invoice/docs/evidence
cd infra/10-rds
terraform init
terraform fmt -recursive
terraform validate

terraform plan -var-file=dev.tfvars \
  | tee $EVID/$(date +%Y%m%d_%H%M%S)_papyrus_tf_plan.log

terraform apply -auto-approve -var-file=dev.tfvars \
  | tee $EVID/$(date +%Y%m%d_%H%M%S)_papyrus_tf_apply.log
```

`terraform apply` のログは、以下の監査証跡として保管する。

証跡：[20251021_014118_papyrus_tf_apply.log](../../docs/evidence/20251021_014118_papyrus_tf_apply.log)

- パラメータの変更内容
- RDS の再起動有無とそのタイムスタンプ

### 2. RDS 接続情報の取得と記録

```bash
EP=$(terraform output -raw rds_endpoint)
PORT=$(terraform output -raw rds_port)

TS=$(date +%Y%m%d_%H%M%S)
echo "$EP:$PORT"
```

ここで取得した `host` / `port` は Secrets Manager (`papyrus/prd/db`) に登録されるべき値になる。
影響度は低いが、エンドポイントは攻撃面の足掛かりになりうるため、証跡としては残さない。

### 3. スキーマ投入のドライラン (DRY RUN)

本番運用で使用する `init.sql` は「本番データ投入」を含むため、いきなり本適用は行わない。
まず ECS Exec を用い、Fargate 上のアプリケーションコンテナ内部で `BEGIN; ...; ROLLBACK;` までを実行し、文法・権限・権限スコープのみを検証する。

手順概要:

1. `init.sql` を一時的に `/tmp/init.sql` に配置
2. `aws ecs execute-command` を使用して、Fargate 上の `app` コンテナに入る
3. Secrets Manager (`papyrus/prd/db`) から接続情報を取得し、`psycopg2` で接続
4. `BEGIN; ...; ROLLBACK;` でロールバック前提の試験投入を実施

   - 目的は「スキーマと INSERT ステートメントが RDS 上で有効に実行可能であること」の確認

証跡ファイル例:
`20251021_073000_schema_dryrun_exec.log`
このログには、`SCHEMA DRYRUN OK (statements= 3 )` といった検証成功メッセージが記録される。

### 4. 実データ INSERT の検証 (2 系統)

(1) CLI 経由 (`psycopg2` 直接実行)

```bash
aws ecs execute-command ... --command "/bin/sh -lc 'python - <<\"PY\"
import json,boto3,psycopg2
sm=boto3.client(\"secretsmanager\", region_name=\"us-west-2\")
sec=json.loads(sm.get_secret_value(SecretId=\"papyrus/prd/db\")[\"SecretString\"])
dsn=(\"host={h} port={p} dbname={d} user={u} password={pw} sslmode=require\").format(
    h=sec[\"host\"], p=sec.get(\"port\",5432), d=sec.get(\"database\",\"papyrus\"),
    u=sec[\"username\"], pw=sec[\"password\"])

conn=psycopg2.connect(dsn); cur=conn.cursor()
cur.execute(\"INSERT INTO papyrus_schema.products (sku,name,unit_price,note) VALUES ('SKU-CLI','health',0,'probe') ON CONFLICT (sku) DO NOTHING;\")
conn.commit()
cur.execute(\"SELECT sku,name,unit_price FROM papyrus_schema.products WHERE sku='SKU-CLI';\")
print(\"CLI INSERT ROW:\", cur.fetchone())
conn.close()
PY'" \
| tee $EVID/$(date +%Y%m%d_%H%M%S)_papyrus_psql_insert_cli.log
```

期待される出力例:
`CLI INSERT ROW: ('SKU-CLI', 'health', 0)`

成功ログ：[20251021_052218_papyrus_psql_insert_cli.log](../../docs/evidence/20251021_052218_papyrus_psql_insert_cli.log)

(2) アプリケーション経由 (`/dbcheck` ルート)

`papyrus.blueprints.dbcheck` の `/dbcheck` エンドポイントでは、Flask 側のコネクションプールを経由して INSERT を実行する。
この経路では SKU `SKU-APP` を投入し、ステータスとレスポンスを検証する。

- ALB のスモークテスト時に `/dbcheck` へ `curl` し、HTTP 200 と `{"inserted": true}` が返ることを確認済み
- 証跡ファイル例:
  [20251104_050806_dbcheck.log](../../docs/evidence/20251104_050806_dbcheck.log)

(3) 両経路の書き込み結果を確認

```bash
aws ecs execute-command ... --command "/bin/sh -lc 'python - <<\"PY\"
import json,boto3,psycopg2
sm=boto3.client(\"secretsmanager\", region_name=\"us-west-2\")
sec=json.loads(sm.get_secret_value(SecretId=\"papyrus/prd/db\")[\"SecretString\"])
dsn=(\"host={h} port={p} dbname={d} user={u} password={pw} sslmode=require\").format(
    h=sec[\"host\"], p=sec.get(\"port\",5432), d=sec.get(\"database\",\"papyrus\"),
    u=sec[\"username\"], pw=sec[\"password\"])

conn=psycopg2.connect(dsn); cur=conn.cursor()
cur.execute(\"SELECT sku,name,unit_price FROM papyrus_schema.products WHERE sku IN ('SKU-CLI','SKU-APP');\")
rows=cur.fetchall()
print(\"ROWS:\", rows)
conn.close()
PY'" \
| tee $EVID/$(date +%Y%m%d_%H%M%S)_papyrus_sku_check.log
```

期待される出力例:
`ROWS: [('SKU-CLI', 'health', 0), ('SKU-APP', 'health', 0)]`

これにより、以下の完了条件 (Definition of Done) を満たす。

- ECS タスクから RDS に対し、TLS 必須接続で INSERT が行えること
- CLI 経路およびアプリケーション経路の双方で DB 書き込みが成功していること
- すべての手順と結果の証跡ログが `docs/evidence` に保存されていること

成功ログ：[20251028_074758_papyrus_sku_check](../../docs/evidence/20251028_074758_papyrus_sku_check.log)

---

## セキュリティ / 運用メモ

- RDS 用 Security Group の inbound 5432/TCP は、ECS タスク用 SG のみ許可すること

  - 任意 CIDR (`0.0.0.x/0` 等) を許可しないこと
- `rds.force_ssl = 1` は Parameter Group により管理しているため、無断で Parameter Group を差し替えないこと
- Secrets Manager `papyrus/prd/db` の `host` / `port` / `password` を変更した場合、CI のプリフライトで不整合が検知される想定
- DB パスワードや `dev.tfvars` などの秘匿情報はリポジトリに含めない。公開対象は README と証跡ログのみとする