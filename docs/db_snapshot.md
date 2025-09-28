# RDS 復旧手順（Papyrus）

## 前提
- リージョン: us-west-2
- 直近スナップショット: `<SNAP or FINAL>`

## 復旧
1. スナップショットから作成
   ```bash
   aws rds restore-db-instance-from-db-snapshot \
     --region us-west-2 \
     --db-instance-identifier papyrus-restore-$(date -u +%Y%m%dT%H%M%SZ) \
     --db-snapshot-identifier <SNAPSHOT_ID> \
     --db-instance-class db.t3.small

2. SG/VPC/サブネットを既存構成に合わせて modify-db-instance で調整

3. エンドポイントをアプリの設定（SSM/Secrets）に反映

4. 接続確認後、不要スナップショットは後日クリーンアップ