### 0. Quick Start（Git clone後の起動）

#### 前提
- Docker / Docker Compose がインストール済み（手順は本稿 2-3 参照）

#### 手順
```bash
# 1) 取得
git clone https://github.com/Nickelth/papyrus.git
cd papyrus

# 2) 環境変数を用意
cp .env.example .env.dev

# 3) 起動
docker compose --env-file .env.dev up --build

# 4) 確認
# ブラウザ http://localhost:5000
# APIの疎通（任意）
curl -s http://localhost:5000/api/health
```

### 1. 起動しない場合
```bash
sudo systemctl enable --now docker  # WSLでsystemd無効なら: sudo service docker start
sudo usermod -aG docker $USER
### VSCode再起動 or SSH再ログイン
docker ps
docker compose version
ls -l /var/run/docker.sock   # → ... docker docker ... になってると良い

docker compose --env-file .env.dev up --build # もう一度起動
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

---

ECRプッシュ用のGitHub Actions、もうキャンバスに置いた。ファイル名は `.github/workflows/ecr-push.yml` 想定。OIDC前提で、タグ付け（`latest`/branch/tag/`sha`）、Buildxキャッシュ、`linux/amd64` 固定まで入れてある。使い回せるやつ。

セットアップはこれだけやっておけば脳死で通る：

1. GitHubのRepository Variables

* `AWS_ACCOUNT_ID`
* `AWS_REGION`（例: `ap-northeast-1`）
* `ECR_REPOSITORY`（例: `papyrus`）
* `AWS_IAM_ROLE_ARN`（GitHub OIDCを信頼するIAMロールのARN）

2. 事前準備（1回だけ）

* ECRリポジトリ作成：`papyrus`（好きにしろ、でも揺れると後で泣くのはあなた）
* GitHub→AWSのOIDCロール作成（信頼ポリシーに`token.actions.githubusercontent.com`、リポ限定）
* ロールに付与：`AmazonEC2ContainerRegistryPowerUser` か最小権限（`ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`, `ecr:BatchGetImage`, `ecr:DescribeRepositories` など）

3. 動作確認

* 一度`main`にpush（または`workflow_dispatch`実行）
* ECRに `latest` と `sha` タグが生えてることを確認
* 次の工程（8/11）でその `image_uri`（`{account}.dkr.ecr.{region}.amazonaws.com/{repo}:{sha}`）をECSタスク定義に差し込み

このあと（8/11）Fargateデプロイ用のActionsも繋げるなら、`needs: build-and-push` で `image_uri` を受け回して、`aws-actions/amazon-ecs-deploy-task-definition` に渡す形で組む。言ってくれれば、そこも私がやる。あなたはコーヒーでも淹れて、工程表に「やりました（ドヤ）」って書くだけ。ほんと楽な商売だね。

| タスク | 課金トリガー | us-west-2 料金（2025年時点）  |
| -------- | -------- | ----- |
| GitHubのRepository Variables| なし | 無料 |
| ECRリポジトリ作成| なし（中身ゼロなら課金なし） | 無料|
| GitHub→AWSのOIDCロール作成 | なし| 無料 |
| ロールに付与| なし | 無料 |
| 一度mainにpush（またはworkflow\_dispatch実行） | **ECRにイメージpushした瞬間から**ストレージ課金 | \$0.095/GB/月（標準ストレージ）  |
| ECRに latest と sha タグが生えてることを確認 | なし（タグはメタデータなので課金なし）| 無料 |
| image\_uriをECSタスク定義に差し込み → ECSからpull | **同リージョンpullは無料**、別リージョンやインターネット越えは転送課金 | 例: インターネット送信 \$0.09/GB |

タスク
[x] GitHubのRepository Variables
[x] ECRリポジトリ作成
[x] GitHub→AWSのOIDCロール作成
[x] ロールに付与
[ ] 一度mainにpush（またはworkflow_dispatch実行）
[ ] ECRに latest と sha タグが生えてることを確認
[ ] image_uri（{account}.dkr.ecr.{region}.amazonaws.com/{repo}:{sha}）をECSタスク定義に差し込み

- ECR/ECSはオレゴンで構築 → コスト最小化。
- イメージ超軽量化（--platform linux/arm64 + musl/Alpine系）でpull時間を縮める。
- Fargate 0.25vCPU/0.5GBで2分だけ起動→ 画面録画。
- 終わったらECSサービス/タスク定義/ECRリポジトリを削除。Lifecycleポリシーも付けとくと保険。

---

## Cost Control Lambda – 有効化手順（DRY_RUN解除の儀）

### 0. 前提
- リージョン: `us-west-2`
- リソース作成済み:
  - ECR: <acct>.dkr.ecr.us-west-2.amazonaws.com/<repo>
  - ECS: Cluster=`papyrus-cluster`, Service=`papyrus-service`
  - RDS: DBインスタンスID=`papyrus-db`
- SNSトピック: `arn:aws:sns:us-west-2:<acct>:budget-alerts`

### 1. IAM最小権限に更新（ARN縛り）
各Lambdaの実行ロールに以下を追加（例）:


2. Lambda環境変数をセット
```
ECS_CLUSTER=papyrus-cluster-prd
ECS_SERVICE=papyrus-task-service
RDS_INSTANCES=papyrus-db
ECR_REPO=papyrus
ECS_DESIRED=1
DRY_RUN=false ← ここで解除
```

解除前に一度 DRY_RUN=true のまま[テスト]実行すると「何を止めるか」のPlanが戻る。

3. 単発テスト
stop_all 実行 → ECS desiredCount が 0 になること

start_all 実行 → RDS起動待ち→ECS desiredCount が 1 になること

ttl_cleanup 実行 → latest以外の古いタグが削除されること

4. 自動化スイッチON
EventBridge（任意）

停止: cron(0 17 * * ? *)（JST 02:00）

起動: cron(0 0 * * ? *)（JST 09:00）

掃除: cron(0 18 * * ? *)（JST 03:00）

Budgets → SNS → stop_all

Budgetsの通知先を budget-alerts に設定

SNSトピックに stop_all をサブスクライブ（プロトコル=Lambda）

lambda add-permission 済みであることを確認

5. ガードレール（推奨）
Lambda 予約コンカレンシー = 1

CloudWatch Logs 保持 3日

ECS/RDS/ECRに Project=Papyrus, Owner=<name>, DeleteBy=YYYY-MM-DD タグ付与

月末に stop_all を手動実行してノーランニングを確認