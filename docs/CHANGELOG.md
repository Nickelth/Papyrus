## 2025-10-22 → 2025-10-28

### 目的

Papyrus 環境において、ALB/TG の一時デプロイを自動化し、作成から破棄までを CI (GitHub Actions) 上で再現可能にすること。これにより「都度手でALBを作って/残骸を消し忘れて課金・名前衝突する」というリスクを排除し、証跡（DNS名/Target Group ARN等）を自動取得できる状態まで引き上げる。

### 主要変更

- `alb-smoke` ワークフローを整備し、以下が 1 ジョブ内で完結するようになった。

  - Terraform init/apply を実行し、Application Load Balancer / Target Group / Security Group をプロビジョニング
  - Terraform output から ALB DNS / Target Group ARN などを収集し、ジョブ内でエクスポート
  - 収集した出力をアーティファクトとして保存
  - 最後に Terraform destroy を必ず実行し、ALB/TG/SG を破棄してクリーンな状態に戻す
    （`destroy` ステップは `always` 扱いで、apply 中に失敗が出ても最終的に後片付けされる）

- dev.tfvars 相当の機密値（VPC ID / サブネットID / ECSタスクSGなど）はリポジトリに含めず、GitHub Actions 実行時に一時的にファイル生成する運用に変更。
  → 構成は IaC で再現可能、かつシークレットはリポジトリに残さない形に整理。

- IAM 権限を追加し、GitHub Actions 実行ロール（`ECRPowerUser` Assumeロール）に ALB/TG/Listener 周りのライフサイクル操作が許可されるようにした。
  具体的には以下のAPI権限を追加済み:

  - `elasticloadbalancing:CreateLoadBalancer` / `DeleteLoadBalancer` / `ModifyLoadBalancerAttributes` / `DescribeLoadBalancers` / `DescribeLoadBalancerAttributes`
  - `elasticloadbalancing:CreateTargetGroup` / `DeleteTargetGroup` / `ModifyTargetGroup` / `ModifyTargetGroupAttributes` / `DescribeTargetGroups` / `DescribeTargetGroupAttributes` / `DescribeTargetHealth` / `RegisterTargets` / `DeregisterTargets`
  - `elasticloadbalancing:CreateListener` / `DeleteListener` / `ModifyListener` / `DescribeListeners` / `DescribeListenerAttributes` / `ModifyListenerAttributes`
  - `elasticloadbalancing:AddTags` / `RemoveTags` / `DescribeTags`
  - `ec2:CreateSecurityGroup` / `DeleteSecurityGroup` / `AuthorizeSecurityGroupIngress` / `RevokeSecurityGroupIngress` / `AuthorizeSecurityGroupEgress` / `RevokeSecurityGroupEgress` / `DescribeSecurityGroups` / `DescribeSecurityGroupRules` / `DescribeVpcs` / `DescribeSubnets` / `DescribeNetworkInterfaces`

  これにより、前回まで発生していた以下の失敗を解消。

  - `DescribeListenerAttributes` 403 により Listener 作成後の属性参照で Terraform が落ちる
  - `ModifyLoadBalancerAttributes` / `ModifyTargetGroupAttributes` 403 により state 反映に失敗しゾンビ残留
  - ALB/TG/SG を作った途中で CI が停止し、次回 apply 時に `InvalidGroup.Duplicate` 等で衝突する

### 証跡

- GitHub Actions: `alb-smoke #9`

  - ステップ一覧:

    - `Setup Terraform`
    - `AWS creds` (AssumeRole 成功)
    - `Write tfvars (runtime only)`（機密を実行時だけ生成）
    - `Terraform apply (ALB/TG only)`
    - `Export outputs`（ALB DNS名 / Target Group ARN 等を取得）
    - `Save outputs artifact`（証跡をアーティファクト化）
    - `Terraform destroy (always)`（リソースを破棄し終了時はクリーン）
  - ジョブ全体のステータス: `succeeded`

- CloudShell 側のローカル証跡:

  - `*_alb_sg_leftover.json`

    - 残存していた `papyrus-alb-sg` の SecurityGroupId/VpcId を記録
  - `*_alb_sg_delete.log`

    - 上記 SG の削除ログ
  - `*_alb_sg_verify_gone.json`

    - `describe-security-groups` で `papyrus-alb-sg` が空配列になることを確認

- IAM 更新手順の記録:

  - `ECRPowerUser` ロールに対し、ELBv2 (ALB/TargetGroup/Listener) と SG 周りの Create/Describe/Modify/Delete/TAG 系アクションを付与したインラインポリシーを適用済み

### ロールアウト

- `alb-smoke` ワークフローを実行することで、Papyrus用の ALB / Target Group / リスナー / セキュリティグループを一時的に構築し、Terraformの `output` を保存したうえで、同じジョブの最後で確実に破棄できるようになった。
- これにより、手動オペレーション無しで「Papyrusの公開経路(ALB経由)を最低限のIaCで再現し、後片付けまで保証する」というスモークテストが日単位で再現可能になった。
- 破棄が `always` 指定になっているため、apply 中に失敗しても課金リソース（ALB/TG/SG）だけ残留する事故は基本的に抑止される。

### 残課題

- [ ] ALB/TG 作成までは自動化済みだが、以下は未自動化:

  - ECSタスクを Target Group に一時登録する処理 (`register-targets`)
  - ALB経由で `/healthz` を叩き、200 OK を取得する疎通テストの自動実行と、そのレスポンス/ステータスの証跡化
  - ALB→ECS 経由の `/dbcheck` 呼び出しでアプリ側 INSERT (`SKU-APP`) が成功したログを取得・保管するステップ

    - 現時点では `/dbcheck` は Flask 側に追加済み、CLI経由の `SKU-CLI` INSERT は確認済みだが、ALB経由のアプリINSERT成功の証跡 (`200 OK` + JSON) はまだ未取得

- [ ] タスク定義側の恒久化対応:

  - `PGSSLMODE=require` を ECS タスク定義の環境変数として常設し、平文接続を防ぐ
  - `/healthz` (DB 非依存の軽量エンドポイント) をアプリに実装し、ALB Target Group のヘルスチェックパスに使えるようにする
    → これが入ると ALB/TG 側のヘルス確認もワークフローで自動化しやすくなる

- [ ] 監視/監査系:

  - `terraform apply` 時に CloudWatch Alarm (ECS Memory >80%, ALB 5xx%, TargetResponseTime p90 >1.5s 等) と SNS Topic を最小セットで同時に立て、証跡ログを取得するステップは未導入
  - Secrets Manager (`papyrus/prd/db`) の接続情報と RDS 実体の Endpoint/DB名 の diff チェックを CI のプリフライトに入れるのは未実装

- [ ] ドキュメント:

  - `infra/20-alb` 用 README（「Runtime tfvars で apply/destroy する」「権限セットの最小要件」「ゾンビSGが残った場合の手動掃除手順」「出力アーティファクトの参照方法」）をまだ整理していない
    → 次回の Zenn/ポートフォリオ記事に載せるため、証跡ファイル名と一緒にまとめる必要あり

## 2025-10-21

### 目的

1. Papyrus の RDS スキーマを安全に投入し、アプリ/CLIの二系統で INSERT 0 1 を証跡化する。SSL必須・最小SGを維持したまま運用可能状態に上げる。
2. Papyrus のアプリ改修と再デプロイを通し、ECS/Fargate 上で /dbcheck を有効化。イメージを digest 固定で差し替え、ECS Exec を有効化したうえでルーティングを実機確認する。

### 主要変更

- `init.sql` を ECS Exec 経由で DRY-RUN → 本適用（BEGIN…ROLLBACK/COMMIT）
- 2系統の挿入検証:
  - CLI系: psycopg2 直で SKU-CLI を挿入
  - アプリ経由: 暫定 /dbcheck で SKU-APP を挿入
- RDS SG は 5432 inbound を ECSタスクSGのみ に統一（重複SG整理済）
- `papyrus/routes.py` と名前衝突しないよう `papyrus/blueprints/dbcheck.py` に移動、`__init__.py` で Blueprint 登録。
- 実行中タスクに対し Exec で URL マップ確認。`/dbcheck` ルートの搭載を確認。

### 証跡

- `*_schema_dryrun_exec.log`, `*_schema_apply_exec.log`
- `*_papyrus_psql_insert_cli.log`, `*_papyrus_psql_insert_app.log`
- `*_rds_sg_inbound_after.json`
- 実行中イメージ
  - `*_running_image.log`
- URLマップ
  - `*_flask_url_map_after.log`
- /dbcheck 叩き込みログ（prefix 探査スクリプト込み）
  - `*_papyrus_psql_insert_app.log`
- サービス更新・安定待ち関連（必要に応じて script ログに追記）

### ロールアウト

- `us-west-2`、サービス `papyrus-task-service`。外部公開無し、影響はタスク1本のみ。
- 認証は OIDC。Secrets papyrus/prd/db は RDS 実体と整合済み（host/port/user/dbname/password）。
- タスク定義: `papyrus-task:39` をサービス `papyrus-task-service` に適用済み。
- サービス状態: Desired=1 / Running=1 まで復旧。
- ALB 経由のヘルスチェックは未設定だが、アプリは `0.0.0.0:5000` で稼働し、`/dbcheck` が URL マップに載っていることを Exec で確認済み。

### 残課題

- [ ] /healthz を軽量実装して将来の ALB/TG ヘルスに流用
- [ ] /dbcheck の 200 実測とレスポンス保存(今日は URL マップまで。次回、/dbcheck 実行で 200 と JSON をログに残す)
- [x] CI の安全策
  - [ ] コンテナ起動前テスト: python -c "from papyrus import create_app; a=create_app(); print([r.rule for r in a.url_map.iter_rules()])" を CI で回し、/dbcheck の存在を検知。
  - [x] ECS Exec 有効 のサービス設定 drift チェックを IaC 側に。
- [ ] PGSSLMODE=require をタスク定義で恒久化、可能なら sslrootcert 検証まで
- [ ] CI プリフライト: Secrets と RDS 実体の diff、RDS エンドポイント変更検知
- [ ] CloudWatch Alarm（ECSメモリ/CPU、将来のALB 5xx/応答遅延）
  - [ ] 退出コード異常（Exit 3 など）と起動失敗の CloudWatch アラームを追加。
- [ ] RDS 初期化フローの二段化
  - 既存の init.sql は本番データ扱い。DRYRUN と本適用をスクリプトで明確に分離し、Evidence を自動保存。


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

- [ ] **ヘルスエンドポイント実装**: `/healthz` をDB非依存で200返す軽量版で追加。将来ALB/TGのHCに流用。
- [ ] **ALB/TG連結の最小化**: `containerName=app`/`containerPort=5000` でターゲット登録。ALBアクセスログ先S3だけ先に用意。
- [x] **DB経由の実証**: 一時エンドポイント `/dbcheck` 等で `INSERT 0 1` をアプリ経由で実演し証跡化。
- [ ] **SSLの恒久化**: タスク定義に `PGSSLMODE=require` を常設。可能なら `sslrootcert=rds-combined-ca-bundle.pem` を同梱して検証強化。
- [ ] **CIプリフライト**: デプロイ前に「SecretsとRDS実体のdiffチェック」をWorkflowに追加（`DBName/Endpoint/Port/Username`）。
- [ ] **監視**: CloudWatch Alarm（ECSメモリ、ALB 5xx%、TargetResponseTime）をPapyrus側にも適用。
- [ ] **ドキュメント**: `infra/10-rds/README.md` に「手作業との差分・再起動時刻・ParameterGroup差分」を追記。



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
