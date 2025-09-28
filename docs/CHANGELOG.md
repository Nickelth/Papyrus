* **2025-09-10**: CloudTrail 90日分の証跡を取得し保全（CloudShell実施）

  * **目的**: Papyrus関連の操作履歴をローカル/リポジトリで長期保全し、監査・インシデント解析に備える
  * **実行環境**: AWS CloudShell（アカウント: Papyrus 運用、リージョン: `us-west-2`）
  * **実施内容**:

    * `cloudtrail:LookupEvents` を用いて直近90日のイベントを **NDJSON**（1行1イベント）で全件取得
    * 「Papyrus」関連のみをフィルタした派生ファイルも生成
    * それぞれを gzip 圧縮しダウンロード、`docs/evidence/cloudtrail/` に保存
  * **実行コマンド（CloudShell）**:

    ```bash
    REGION=us-west-2
    START=$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ)
    END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    OUT=cloudtrail_events_$(date -u +%Y%m%dT%H%M%SZ).jsonl

    TOKEN=""
    : > "$OUT"
    while :; do
      RESP=$(aws cloudtrail lookup-events --region "$REGION" \
               --start-time "$START" --end-time "$END" --max-results 50 \
               ${TOKEN:+--next-token "$TOKEN"} --output json)
      echo "$RESP" | jq -c '.Events[]' >> "$OUT"
      TOKEN=$(echo "$RESP" | jq -r '.NextToken // empty')
      [ -z "$TOKEN" ] && break
    done

    # 「Papyrus」文字列を含むイベントだけを抽出（任意）
    jq -c 'select(tostring|test("papyrus"; "i"))' "$OUT" > "${OUT%.jsonl}.papyrus.jsonl"

    gzip -f "$OUT" "${OUT%.jsonl}.papyrus.jsonl"
    ```
  * **保存物**:

    * `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.jsonl.gz`（全イベント）
    * `docs/evidence/cloudtrail/<timestamp>/cloudtrail_events_<UTC>.papyrus.jsonl.gz`（Papyrus関連のみ）
  * **検証（抜粋）**:

```bash
zcat cloudtrail_events_*.jsonl.gz | head -n 3
zcat cloudtrail_events_*.jsonl.gz | wc -l
zcat cloudtrail_events_*.papyrus.jsonl.gz | jq -r '.EventName' | sort | uniq -c | sort -nr | head
```
