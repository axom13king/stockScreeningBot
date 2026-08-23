# 株式スクリーニング自動通知アプリ

事前に決めたスクリーニング条件に合致する銘柄を毎日Telegramへ通知し、保有銘柄については売り時も知らせるアプリ。

## 構成

- **言語**: Python
- **実行環境**: GitHub Actions(日次スケジュール実行)
- **通知/連携**: Telegram Bot
- **データ永続化**: Supabase (PostgreSQL)
- **日次株価**: yfinance(遅延なし・無料。J-Quants無料プランは直近約3ヶ月のデータ遅延があり日次スクリーニング用途に不向きなため採用)
- **財務情報(PER/PBR算出用、将来実装)**: J-Quants API v2

## セットアップ

### 1. Supabase

1. https://supabase.com でプロジェクトを作成
2. SQL Editorで [db/schema.sql](db/schema.sql) の内容を実行してテーブルを作成
3. プロジェクト設定 > API から `SUPABASE_URL` と `SUPABASE_KEY` (anon/publishable key) を控える

### 2. Telegram Bot

1. Telegramで `@BotFather` に `/newbot` を送り、Botを作成してトークン(`TELEGRAM_BOT_TOKEN`)を取得
2. 作成したBotに何かメッセージを送った後、`https://api.telegram.org/bot<TOKEN>/getUpdates` にアクセスし、`chat.id` を確認して `TELEGRAM_CHAT_ID` として控える

実際の値は `.env` (gitignore対象、リポジトリにはコミットされない) にのみ記載し、READMEやコミットには含めないこと。

### 3. J-Quants API (v2) — 将来の財務情報(PER/PBR)取得用

1. https://jpx-jquants.com/ でアカウント登録・サブスクリプションプラン登録
2. ダッシュボードの「設定 > APIキー」から `JQUANTS_API_KEY` を発行・取得(v2はAPIキーを`x-api-key`ヘッダーで送るだけで、v1のようなリフレッシュトークン/IDトークンの交換は不要)
3. **無料プランは直近約3ヶ月のデータ遅延がある**ため、日次の株価取得には使わずyfinanceを使用している。財務情報(EPS/BPS)の取得は四半期単位のため遅延の影響が小さく、将来的にJ-Quantsを使う想定
4. yfinanceは日本株コードに `.T` を付与してアクセスする非公式ライブラリのため、Yahoo Finance側の仕様変更で動作しなくなるリスクがある点に留意

### 4. ローカル開発環境

Python 3.10以上が必要(型ヒントの記法に依存)。

このマシンでは `python` コマンドがWindowsストアのスタブを指してしまい動作しないため、`py` ランチャーを使うこと(venv作成後は `.venv` 内の `python` が使われるので問題ない)。

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env を編集して各種キーを設定
python main.py
```

### 5. GitHub Actions

リポジトリの Settings > Secrets and variables > Actions で、`.env.example` に列挙されている変数をすべて Secrets として登録する。[.github/workflows/daily.yml](.github/workflows/daily.yml) が平日16:30(JST、東証大引け後)に自動実行する。手動実行は Actions タブから `workflow_dispatch` で可能。

## スクリーニング条件・ウォッチリストの編集

- [config/screening_conditions.yaml](config/screening_conditions.yaml): スクリーニング条件(指標・閾値)
- [config/watchlist.yaml](config/watchlist.yaml): スクリーニング対象銘柄コード

## Telegramでの売買報告フォーマット

```
買 7203 2500 100    (証券コード 購入価格 株数)
売 7203 2600         (証券コード 売却価格)
```

## バックテスト(手元PCで随時実行)

```powershell
python -m src.backtest.run_backtest --code 7203 --from 2023-01-01 --to 2024-01-01
```

## 未確定・今後詰める事項

- スクリーニングの具体的な指標・閾値
- 売り時判定の具体的なルール([src/holdings/rules.py](src/holdings/rules.py) は仮の初期値)
- PER/PBRの算出([src/screening/indicators.py](src/screening/indicators.py) のフィールド名はJ-Quants APIの実レスポンスで要検証)
- ウォッチリストを東証全銘柄に拡張する場合のAPI呼び出し回数・実行時間の検証
