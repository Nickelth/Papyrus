
## 2025-10-08 → 2025-10-17

### 目的

ECSデプロイ時にロールバックが頻発する問題が発生。
Terraform記述のDB名、パスワードがSecretsと不整合を起こしていることが原因。
まず、Secrets不整合とSSL未指定による起動失敗を解消する。
次に、Papyrus を「DB接続で即死させずに」正常起動させ、VPC内からHTTP 200を確認する。

### 主要変更

* **ECS Exec有効化**: IAMロール修正、CloudShellからpsqlコマンド直叩きを有効化。
* **現行Secrets検証**: `papyrus/prd/db` の `database`/`password` をRDS実体と突き合わせて確認。
* **RDS再起動**: ParameterGroup反映確認のため再起動実施（`rds.force_ssl=1` 維持、ApplyType=dynamic確認）。
* **Secrets更新**: `papyrus/prd/db` を正値に上書き（`database=papyrus`、正しい`password`、既存の`host/port/username`）。
* **タスク更新**: サービスを `--force-new-deployment` で再デプロイ。必要に応じて `PGSSLMODE=require` をタスク定義へ付与し再登録。
* **VPC内疎通確認**: ECS Exec からアプリ直叩き。`/healthz` は未実装で404、`/` は200で生存判定OK。

### 証跡

* RDSパラメータ確認: `describe-db-parameters` で `rds.force_ssl=1 (dynamic)` を記録
* Secrets現値・更新:
  * `aws secretsmanager get-secret-value --secret-id papyrus/prd/db` 出力（更新前/更新後）

* ECSデプロイ/状態:
  * `aws ecs update-service --force-new-deployment` 実行ログ
  * `aws ecs wait services-stable` 完了
  * `aws ecs describe-services` で `desiredCount=1 / runningCount=1` を確認

* HTTP疎通（ECS Exec 内 Python）:
  * `/healthz -> 404 Not Found`（未実装のため想定内）
  * `/ -> 200 OK` 本文 `Welcome to Papyrus` を確認

### ロールアウト

* 対象: `us-west-2` の Papyrus（Fargate, cluster `papyrus-ecs-prd`, service `papyrus-task-service`）
* 影響範囲: 新リビジョンのタスク1本のみ。ALB未連携のため外部トラフィック影響なし。
* 認証: OIDC（既存設定）。Secrets/SSM読み取りは `papyrusTaskRole`。
* 結果: サービス安定（`services-stable`）、アプリHTTP 200をVPC内で確認。

### 残課題

* **ヘルスエンドポイント実装**: `/healthz` をDB非依存で200返す軽量版で追加。将来ALB/TGのHCに流用。
* **ALB/TG連結の最小化**: `containerName=app`/`containerPort=5000` でターゲット登録。ALBアクセスログ先S3だけ先に用意。
* **DB経由の実証**: 一時エンドポイント `/dbcheck` 等で `INSERT 0 1` をアプリ経由で実演し証跡化。
* **SSLの恒久化**: タスク定義に `PGSSLMODE=require` を常設。可能なら `sslrootcert=rds-combined-ca-bundle.pem` を同梱して検証強化。
* **CIプリフライト**: デプロイ前に「SecretsとRDS実体のdiffチェック」をWorkflowに追加（`DBName/Endpoint/Port/Username`）。
* **監視**: CloudWatch Alarm（ECSメモリ、ALB 5xx%、TargetResponseTime）をPapyrus側にも適用。
* **ドキュメント**: `infra/10-rds/README.md` に「手作業との差分・再起動時刻・ParameterGroup差分」を追記。



## 2025-09-10

*CloudTrail 90日分の証跡を取得し保全（CloudShell実施）*

### 目的

Papyrus関連の操作履歴をローカル/リポジトリで長期保全し、監査・インシデント解析に備える

### 実行環境

AWS CloudShell（アカウント: Papyrus 運用、リージョン: `us-west-2`）

### 実施内容

* `cloudtrail:LookupEvents` を用いて直近90日のイベントを **NDJSON**（1行1イベント）で全件取得
* 「Papyrus」関連のみをフィルタした派生ファイルも生成
* それぞれを gzip 圧縮しダウンロード、`docs/evidence/cloudtrail/` に保存

### 証跡

* `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.jsonl.gz`（全イベント）
* `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.papyrus.jsonl.gz`（Papyrus関連のみ）
