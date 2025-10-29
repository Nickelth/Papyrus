## 2025-10-29

### 目的

Papyrus インフラの検証フローを「説明ではなく証跡で示せる」状態に近づける。  
具体的には以下を実施した:
- アプリケーションの健全性と RDS への書き込み可否を、ALB 経由で自動検証できるようにする
- その検証手順を CI / Terraform に固定し、再現性と監査性を持たせる
- TLS (PostgreSQL への SSL 接続必須) を運用ルールとして強制する設計にする
- 監視を IaC 管理下に置き、リリース後の稼働状態の可観測性を確保する

これにより、Papyrus の稼働可否・DB 書き込み可否・TLS 運用・監視・リソース破棄 (コスト制御) を、すべて自動テストおよび証跡ログで説明できるようになる。

### 変更内容

#### 1. `/healthz` の実装と疎通確認の自動化
- `papyrus/blueprints/healthz.py` を追加し、`/healthz` を実装。
  - DB 非依存で `{"ok": true}` を返す軽量ヘルスチェックエンドポイント。
- Flask 初期化処理 (`create_app`) に `healthz_bp` を登録済み。
- ALB/Target Group のヘルスチェックパスを `/healthz` に統一する前提を満たした。

#### 2. `/dbcheck` の ALB 経由動作検証
- `papyrus/blueprints/dbcheck.py` を Blueprint として登録し直し、`/dbcheck` を Flask の URL マップに確実に載る形にした。
- Fargate コンテナ上で `/dbcheck` が HTTP 200 を返しつつ、RDS に対して  
  `INSERT ... ON CONFLICT DO NOTHING` により SKU `SKU-APP` を書き込めることを確認。
- smoke CI の `curl` により、ALB 経由の `/dbcheck` 呼び出しで `HTTP/1.1 200 OK ... {"inserted":true}` を取得済み。

#### 3. ALB smoke パイプラインの確立
- GitHub Actions `alb-smoke` ワークフローを整備。
  - Terraform により ALB / Target Group / Listener / Security Group を一時的に作成。
  - 稼働中の ECS サービス (desiredCount=1) からタスクのプライベート IP を取得し、Target Group に `register-targets`。
  - `aws elbv2 wait target-in-service` により、ターゲットが healthy になるまで待機。
  - 取得した ALB の DNS 名に対して `/healthz` および `/dbcheck` をリクエストし、HTTP ステータスとレスポンス本文をログとして保存。
  - 処理完了後に `terraform destroy` を実行し、ALB/TG/Listener/SG をすべて削除してコストリークを防止。
- 結果として以下を確認済み:
  - `/healthz` → `HTTP/1.1 200 OK ... {"ok":true}`
  - `/dbcheck` → `HTTP/1.1 200 OK ... {"inserted":true}`
- これにより、「ALB 経由で Fargate サービスに到達し、そのアプリケーションが RDS に書き込み可能である」ことを自動で検証・証跡化できるようになった。

#### 4. `PGSSLMODE=require` の恒久適用
- ECS タスク定義を jq で再生成する処理を拡張し、`containerDefinitions[].environment` に
  `{"name":"PGSSLMODE","value":"require"}` を強制的に挿入するようにした。
- 新タスク定義は `register-task-definition` → `update-service --force-new-deployment --enable-execute-command` により反映。
- 反映後のタスクに対し `ecs execute-command` で環境変数を確認し、`PGSSLMODE=require` が常設されていることを証跡取得済み。
- これにより、PostgreSQL への平文接続を禁止し、すべてのアプリケーション接続を TLS 必須とした。

#### 5. DB 書き込み経路の二重化検証
- 既存の CLI 経路 (ECS Exec + `psycopg2`) により、SKU `SKU-CLI` を RDS に INSERT 済み。
- `/dbcheck` 経由のアプリケーション側から、SKU `SKU-APP` を INSERT 済み。
- ECS Exec により以下のクエリを実行し、両方のデータが RDS 上に存在することを確認済み:
  ```sql
  SELECT sku,name,unit_price
  FROM papyrus_schema.products
  WHERE sku IN ('SKU-CLI','SKU-APP');
  ```
  - 実測結果:  
    `ROWS: [('SKU-CLI', 'health', 0), ('SKU-APP', 'health', 0)]`
- これにより
  - 「コンテナから RDS へ TLS 必須で直接書き込める」
  - 「ALB 経由のアプリケーション呼び出しでも最終的に RDS へ書き込める」
  の両ラインを実証した。

#### 6. プリフライト (CI 前段チェック) の導入
- `alb-smoke` ワークフローの先頭にプリフライトを追加し、デプロイ前の健全性を強制。
  1. Flask アプリを import し、`create_app()` を実行。  
     ルーティング一覧をダンプし、`/healthz` と `/dbcheck` が存在しない場合は CI を失敗させる。  
     - CI ログに `ROUTES: [...]` を出力して証跡化。
  2. RDS 接続メタ情報のドリフト検知。  
     Secrets Manager (`papyrus/prd/db`) から取得した `host` / `port` と、`aws rds describe-db-instances` で取得した実体のエンドポイント/ポートを比較し、差異があれば `exit 1`。
- これにより、誤ったエンドポイント情報や誤配置された Blueprint などを、本番系に進む前に検出できるようになった。

#### 7. 監視 IaC (`infra/30-monitor`) の導入
- `infra/30-monitor` ディレクトリを作成し、監視リソースを Terraform 管理下に移行。
- CloudWatch Alarm を 3 種類追加し、SNS 通知先を関連付けた:
  - ECS メモリ使用率 > 80% (平均、2/5分評価)  
    - 対象: `ClusterName="papyrus-ecs-prd"` / `ServiceName="papyrus-task-service"`
  - ALB の 5xx レスポンス > 1 (合計、2/5分評価)
  - TargetResponseTime p90 > 1.5s (2/5分評価)  
    - 対象: 対象の Target Group / Load Balancer
- これを `terraform apply` してアラームと SNS 通知を一括作成済み。
- アプリケーション稼働後の異常 (高メモリ使用率、エラーレスポンス増加、レスポンスタイム悪化など) を継続監視できる状態になった。

#### 8. README ドキュメントの整理
- `infra/10-rds/README.md` の整備方針:
  - 必須変数 (`db_username`, `db_password`, `ecs_tasks_sg_id`, `private_subnet_ids` など) の明示
  - Parameter Group (`rds.force_ssl=1`) の意図と、反映のための RDS 再起動タイムスタンプ管理
  - スキーマ投入フローの二段化:
    - DRY RUN (BEGIN/ROLLBACK) 手順
    - 本適用および INSERT 検証手順
  - 証跡ファイル一覧の明文化  
    - `*_papyrus_tf_plan.txt` / `*_papyrus_tf_apply.txt`  
    - `*_papyrus_rds_endpoint.txt`  
    - `*_schema_dryrun_exec.log`  
    - `*_papyrus_psql_insert_cli.log`  
    - `*_papyrus_psql_insert_app.log`  
    - `*_papyrus_sku_check.log`
- `infra/20-alb/README.md` の整備方針:
  - `dev.auto.tfvars` は CI が毎回生成・破棄する一時ファイルであり Git 管理しないこと
  - ALB/TG/Listener/SG の作成 → ターゲット登録 → `/healthz` `/dbcheck` の検証 → `terraform destroy` による削除、というライフサイクルを明示
  - ALB は稼働中は常時課金されるため、destroy が必須である旨の注意喚起
  - `evidence/*_healthz.log` および `evidence/*_dbcheck.log` を CI アーティファクトとして保存する運用を明記

### 証跡一覧

今回新規に取得した、または強化した証跡は以下のとおり。

- `*_healthz.log`  
  - `HTTP/1.1 200 OK ... {"ok":true}` が ALB 経由で取得できていることを確認
- `*_dbcheck.log`  
  - `HTTP/1.1 200 OK ... {"inserted":true}` が ALB 経由で取得できていることを確認  
  - Papyrus アプリケーション経由で RDS に対し INSERT が成功していることの証明になる
- `*_papyrus_sku_check.log`  
  - `ROWS: [('SKU-CLI', 'health', 0), ('SKU-APP', 'health', 0)]`  
  - CLI 経由 (`SKU-CLI`) とアプリ経由 (`SKU-APP`) の両経路で投入したデータが RDS 上に存在することを確認
- `*_pgsslmode_env.log`  
  - ECS Exec の環境変数ダンプにより、`PGSSLMODE=require` がタスク定義レベルで常設されていることを確認
- `infra/30-monitor` の `terraform apply` 実行ログ  
  - `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.`  
  - 監視 (CloudWatch Alarm / SNS) が Terraform で作成済みであることの証跡
- `alb-smoke` ワークフローログ  
  - プリフライトの `ROUTES: [...]` 出力
  - Secrets Manager と RDS のエンドポイント・ポートの差分チェック結果
  - `register-targets` 後に `wait target-in-service` が成功した記録
  - `terraform destroy` による ALB/TG/Listener/SG の削除完了ログ

証跡は `docs/evidence/` に保存すると同時に、CI のアーティファクトとしても収集している。  
これにより、外部レビューや面談等で「本当に動いているのか」を問い合わせられた場合に、ログ一式を提示して説明できるようになった。

### ロールアウト

Papyrus のリリースパスは今後、以下の手順を標準とする。

1. 新しいコンテナイメージを ECR に push する  
2. jq を用いてタスク定義を再生成し、`PGSSLMODE=require` を常設した状態にする  
3. `register-task-definition` → `update-service --force-new-deployment --enable-execute-command` でサービスを更新  
4. RDS が稼働済み、かつ ECS の `desiredCount=1` を満たした状態で `alb-smoke` を起動  
5. CI が一時的に ALB/TG/Listener/SG を Terraform で作成  
6. その ALB 経由で `/healthz` および `/dbcheck` を呼び出し、HTTP 200 と期待レスポンス本文を取得 (`{"ok":true}`, `{"inserted":true}`)  
   - `/dbcheck` の応答により、アプリ経由で RDS への INSERT が成立していることを証明  
7. `terraform destroy` により ALB/TG/Listener/SG を完全削除し、不要リソースを残さない  
8. 監視については、`infra/30-monitor` を `terraform apply` 済みであれば CloudWatch Alarm / SNS 通知が有効な状態になる

このフローを通過したコンテナイメージは、
- 正常応答すること
- RDS に対して TLS 必須で書き込み可能であること
- モニタリング対象になっていること
- コストリークを残さないこと  
を満たしている。

### 残課題 (Open Items)

- README の最終反映  
  - `infra/10-rds/README.md` および `infra/20-alb/README.md` について、変数定義・手順・証跡ファイル名・コスト注意点をリポジトリに正式コミットする

- タスク定義更新フローのスクリプト化  
  - jq → `register-task-definition` → `update-service` の一連手順をスクリプト化し、手動操作による入力ミスを防止する

- TLS 検証の強化  
  - 現状は `PGSSLMODE=require` により「平文接続は禁止」までを強制している  
  - 追加強化として、RDS 提供の CA バンドルをコンテナに同梱し、  
    `sslrootcert=/etc/ssl/certs/rds-combined-ca-bundle.pem` のような証明書検証までカバーする案は設計済みだが未導入

- コスト管理の README 明文化  
  - ALB は稼働中に課金が発生するため、`terraform destroy` が失敗した場合のリカバリ手順  
    (手動での `terraform destroy` 実行、セキュリティグループ残骸がある場合は手動削除など) を README に記載する

---

## 2025-10-28

### 目的

Papyrus の「本番相当の最小構成」をCI上で一時的に起動し、ALB経由でFargateタスクへ到達できること、アプリの `/healthz` と `/dbcheck` が正常応答することを証跡付きで確認し、最後にすべて削除することを自動化した。

ALB / Target Group / SG / Fargateタスク / RDS を一時的に立てて HTTP 200 と DB書き込みを確認し、証跡を残してから `terraform destroy` まで行うCIを完成させた。

### 主要変更

1. **`alb-smoke` ワークフロー拡張**

   - `workflow_dispatch` で手動起動可能な `alb-smoke` を強化。
   - Terraformで ALB / Target Group / ALB用SG / タスクSGへの一時Ingress を `apply`。
   - `apply` 後の output を後続ステップで使えるようにエクスポート。

2. **Fargateタスクの動的検出とターゲット登録**

   - CIロールに `ecs:ListTasks` などを追加し、`papyrus-task-service` の RUNNING タスクを特定。
   - ENI からタスクのプライベートIPを取得し、`aws elbv2 register-targets` で Target Group に登録。
   - `aws elbv2 wait target-in-service` で ALB 側のヘルスチェック(InService)まで自動待機。
   - SGは `ecs_tasks_sg_id` を tfvars から渡し、Terraformが「ALB SG -> タスク SG:5000/tcp」の一時Ingressを自動で開閉するよう統一。

3. **疎通テストと証跡取得の自動化**

   - ALB の DNS 名に対して `curl -si http://ALB_DNS/healthz` と `/dbcheck` を実行。
   - ステータスライン / レスポンスヘッダ / ボディを `evidence/` 以下に時刻付きログとして保存。
   - `/dbcheck` で `SKU-APP` のINSERT経路が `200` / JSON で返ることも記録可能。
   - 失敗時でもCI自体は即死しないようにし、ログは必ず残す。

4. **証跡のアーティファクト化**

   - `actions/upload-artifact@v4` で `evidence/-.log` と `infra/20-alb/terraform.tfstate` を保存。
   - Smoke結果を「実際に到達・200応答・DB INSERTできた」物理ログとして持ち帰れるようにした。

5. **自動クリーンアップ**

   - ジョブ末尾で必ず `terraform destroy -auto-approve` を実行。
   - ALB / Target Group / SG / 一時Ingress をすべて破棄し、リーク・コスト残を防止。
   - destroy まで含めてワークフロー全体が成功状態で完走することを確認済み。

6. **変数とIAM権限の整備**

   - Terraform側に `ecs_tasks_sg_id` を追加し、`default = null` と `count = var.ecs_tasks_sg_id == null ? 0 : 1` で任意化。ローカル検証では未設定でも plan/apply が通る。CIでは Secrets から渡して有効化。
   - GitHub Actions で `PUBLIC_SUBNET_IDS`, `VPC_ID`, `ECS_TASK_SG_ID` などを runtime tfvars (`dev.auto.tfvars`) として書き出すフローを確立。
   - IAMロールには ALB/TG 周り (elasticloadbalancing系のDescribe/Modify/RegisterTargets 等)、ECS (ListTasks/DescribeTasks)、EC2 SG編集など最小限の権限を付与済み。

7. **CIジョブの成功確認**

   - 最新実行は `succeeded`。
   - 「作る → 疎通確認 → 証跡取得 → 破壊」が1本の workflow 内で成立した。

### 証跡

- GitHub Actions 実行結果のスクリーンショット
  (ジョブ `smoke` が `destroy` まで緑で完走している状態)

- `evidence/*_healthz.log`, `evidence/*_dbcheck.log`
  - ALB DNS に対して `curl -si /healthz` と `/dbcheck` を実行した生ログ
  - `/dbcheck` は RDS(PostgreSQL) に対する INSERT/UPSERT 経路 (`papyrus_schema.products` への SKU-APP) を通し、JSONを返すことを確認。

- `infra/20-alb/terraform.tfstate` のアーティファクト
  - CIがそのrunで実際に立てた ALB / Target Group / SG / 一時Ingress のリソースIDが入っている。監査証跡として利用可能。

- ECSタスク検出と `register-targets` のログ
  - RUNNINGタスクのプライベートIPを特定。
  - `private_ip:5000` を Target Group に一時登録。
  - `aws elbv2 wait target-in-service` が成功していることを記録。

これにより「Papyrus は RDS 付きの実稼働中 ECS タスクを CI が動的に拾い、ALB 経由で HTTP 200 を返す」ことを客観的に証明できる。

### ロールアウト

- `alb-smoke` ワークフローを1回走らせるだけで、ALB / SG / TG / ECS / RDS / Flask / Gunicorn / Secrets Manager / SSM / psycopg2 / INSERT 経路まで含めた実インフラのスモークテスト (ほぼE2E) が自動実行される。
- destroy が必須ステップなので、検証後にリソースも課金も残らない。
- `evidence/*.log` と `terraform.tfstate` がartifact化されるため、監査・技術ブログの裏付け資料にそのまま使える。

### 残課題

- [x] `/healthz` をDB非依存の軽量エンドポイントとして固定し、TargetGroupの `health_check.path` を `/healthz` に統一する (現状は `/` を流用しているケースがある)。
- [x] `/dbcheck` のJSONレスポンス (SKU-APPや inserted=true 等) をartifactとして恒常的に保存し、RDSへのINSERT証跡を明文化する。
- [ ] PG接続のSSL (`PGSSLMODE=require`) をタスク定義に組み込み、平常運用とCIの接続ポリシーを統一する。
- [x] Secrets / RDS ドリフト検知、FlaskのBlueprint未登録でタスクがExit 3する問題の再発防止など、起動前プリフライトの自動化は未統合。
- [ ] CloudWatchアラーム (タスクExit Code, メモリ圧迫, 将来のALB 5xxなど) はまだTerraform化していない。
- [x] README整備(2025-10-21以降分、`ECS_TASK_SG_ID` の注入方法など) が未反映。今後 `infra/20-alb/README.md` に反映する。

---

## 2025-10-24 → 2025-10-28

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

- [x] ALB/TG 作成までは自動化済みだが、以下は未自動化:

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

- [x] ドキュメント:

  - `infra/20-alb` 用 README（「Runtime tfvars で apply/destroy する」「権限セットの最小要件」「ゾンビSGが残った場合の手動掃除手順」「出力アーティファクトの参照方法」）をまだ整理していない
    → 次回の Zenn/ポートフォリオ記事に載せるため、証跡ファイル名と一緒にまとめる必要あり

---

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
- ALB 経由のヘルスチェックは未設定だが、アプリは `0.0.0.x:5000` で稼働し、`/dbcheck` が URL マップに載っていることを Exec で確認済み。

### 残課題

- [x] /healthz を軽量実装して将来の ALB/TG ヘルスに流用
- [x] /dbcheck の 200 実測とレスポンス保存(今日は URL マップまで。次回、/dbcheck 実行で 200 と JSON をログに残す)
- [x] CI の安全策
  - [x] コンテナ起動前テスト: `python -c "from papyrus import create_app; a=create_app(); print([r.rule for r in a.url_map.iter_rules()])"` を CI で回し、/dbcheck の存在を検知。
  - [x] ECS Exec 有効 のサービス設定 drift チェックを IaC 側に。
- [ ] `PGSSLMODE=require` をタスク定義で恒久化、可能なら sslrootcert 検証まで
- [x] CI プリフライト: Secrets と RDS 実体の `diff`、RDS エンドポイント変更検知
- [ ] CloudWatch Alarm（ECSメモリ/CPU、将来のALB 5xx/応答遅延）
  - [ ] 退出コード異常（Exit 3 など）と起動失敗の CloudWatch アラームを追加。
- [x] RDS 初期化フローの二段化
  - 既存の `init.sql` は本番データ扱い。DRYRUN と本適用をスクリプトで明確に分離し、Evidence を自動保存。


## 2025-10-08 → 2025-10-17

### 目的

ECSデプロイ時にロールバックが頻発する問題が発生。
Terraform記述のDB名、パスワードがSecretsと不整合を起こしていることが原因。
まず、Secrets不整合とSSL未指定による起動失敗を解消する。
次に、Papyrus を「DB接続で即死させずに」正常起動させ、VPC内からHTTP 200を確認する。

### 主要変更

- **ECS Exec有効化**: IAMロール修正、CloudShellからpsqlコマンド直叩きを有効化。
- **現行Secrets検証**: `papyrus/prd/db` の `database`/`password` をRDS実体と突き合わせて確認。
- **RDS再起動**: ParameterGroup反映確認のため再起動実施（`rds.force_ssl=1` 維持、ApplyType=dynamic確認）。
- **Secrets更新**: `papyrus/prd/db` を正値に上書き（`database=papyrus`、正しい`password`、既存の`host/port/username`）。
- **タスク更新**: サービスを `**force-new-deployment` で再デプロイ。必要に応じて `PGSSLMODE=require` をタスク定義へ付与し再登録。
- **VPC内疎通確認**: ECS Exec からアプリ直叩き。`/healthz` は未実装で404、`/` は200で生存判定OK。

### 証跡

- RDSパラメータ確認: `describe-db-parameters` で `rds.force_ssl=1 (dynamic)` を記録
- Secrets現値・更新:
  - `aws secretsmanager get-secret-value **secret-id papyrus/prd/db` 出力（更新前/更新後）

- ECSデプロイ/状態:
  - `aws ecs update-service **force-new-deployment` 実行ログ
  - `aws ecs wait services-stable` 完了
  - `aws ecs describe-services` で `desiredCount=1 / runningCount=1` を確認

- HTTP疎通（ECS Exec 内 Python）:
  - `/healthz -> 404 Not Found`（未実装のため想定内）
  - `/ -> 200 OK` 本文 `Welcome to Papyrus` を確認

### ロールアウト

- 対象: `us-west-2` の Papyrus（Fargate, cluster `papyrus-ecs-prd`, service `papyrus-task-service`）
- 影響範囲: 新リビジョンのタスク1本のみ。ALB未連携のため外部トラフィック影響なし。
- 認証: OIDC（既存設定）。Secrets/SSM読み取りは `papyrusTaskRole`。
- 結果: サービス安定（`services-stable`）、アプリHTTP 200をVPC内で確認。

### 残課題

- [x] **ヘルスエンドポイント実装**: `/healthz` をDB非依存で200返す軽量版で追加。将来ALB/TGのHCに流用。
- [ ] **ALB/TG連結の最小化**: `containerName=app`/`containerPort=5000` でターゲット登録。ALBアクセスログ先S3だけ先に用意。
- [x] **DB経由の実証**: 一時エンドポイント `/dbcheck` 等で `INSERT 0 1` をアプリ経由で実演し証跡化。
- [ ] **SSLの恒久化**: タスク定義に `PGSSLMODE=require` を常設。可能なら `sslrootcert=rds-combined-ca-bundle.pem` を同梱して検証強化。
- [x] **CIプリフライト**: デプロイ前に「SecretsとRDS実体のdiffチェック」をWorkflowに追加（`DBName/Endpoint/Port/Username`）。
- [ ] **監視**: CloudWatch Alarm（ECSメモリ、ALB 5xx%、TargetResponseTime）をPapyrus側にも適用。
- [x] **ドキュメント**: `infra/10-rds/README.md` に「手作業との差分・再起動時刻・ParameterGroup差分」を追記。

---

## 2025-09-10

*CloudTrail 90日分の証跡を取得し保全（CloudShell実施）*

### 目的

Papyrus関連の操作履歴をローカル/リポジトリで長期保全し、監査・インシデント解析に備える

### 実行環境

AWS CloudShell（アカウント: Papyrus 運用、リージョン: `us-west-2`）

### 実施内容

- `cloudtrail:LookupEvents` を用いて直近90日のイベントを **NDJSON**（1行1イベント）で全件取得
- 「Papyrus」関連のみをフィルタした派生ファイルも生成
- それぞれを gzip 圧縮しダウンロード、`docs/evidence/cloudtrail/` に保存

### 証跡

- `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.jsonl.gz`（全イベント）
- `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.papyrus.jsonl.gz`（Papyrus関連のみ）
