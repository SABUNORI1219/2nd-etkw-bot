# 2nd-etkw-bot

Empire of TKW [ETKW]メンバー専用のBot。
Emperor Chikuwaという初代がいるため2ndとなっている。

## 概要
- Python製のDiscord Bot
- 機能の追加は`cogs/`ディレクトリ配下で管理

## セットアップ

1. 必要なパッケージをインストール
   ```
   pip install -r requirements.txt
   ```

2. 必要な環境変数や設定はRenderのサービスおよび`config.py`で管理

3. Botを起動
   ```
   python main.py
   ```

## ディレクトリ構成
- `cogs/` … Cogモジュール
- `lib/` … ライブラリ/ユーティリティ
- `assets/` … 画像・外部ファイル
- `tasks/` … 定期実行タスク等

## ライセンス
See [LICENSE](./LICENSE)
