## Ops（S3・ログ・Runbook）

### S3 同期

```bash
export S3_BUCKET=s3://<bucket>/mlops-sklearn-portfolio
make s3-push     # snapshots/<UTC>/ と latest/ 更新
make s3-pull     # latest/ を取得（SRC=... でスナップショット指定）
```

* `artifacts/manifest.json` に SHA256/サイズを記録。

## ログと確認

* 学習ログ: `logs/train-*.log`（`make check` でサマリ）
* APIログ: `logs/api-YYYYMMDD.log`（1行JSON）

### Terraform（薄切りIaC）

```bash
make prep                     # infra/ を /tmp/infra/ に同期し terraform.tfvars を配置
terraform -chdir=/tmp/infra plan -target=module.ecs \
  | tee docs/evidence/"$(date +%Y%m%d_%H%M%S)"_tf_plan_target_ecs.txt
```

* `make prep` が `dev.tfvars` を `terraform.tfvars` として同期するため、`bucket_name` などの必須変数を手動で渡す必要がない。
* `-target` で一部モジュールのみを計画する場合、未対象のモジュール出力は `null` を返す（エラーではなくなる）。

### 機密情報のマスク

アクセスキーやアカウントIDをログに載せてコミットしてしまったとき用。

`~/docs/replacement.txt`に記載の`regex`に従いログファイルの文字を置換する。

```bash
git filter-repo --replace-text /docs/replacements.txt
```

## 緊急時

* 手順は `severe_disaster_manual.md` を参照（監査向け）。