# DM通知Embed言語切替UX改善 - 実装ドキュメント

## 概要

このドキュメントは、DM通知Embedの言語切替UXを改善するために実装された変更について説明します。

## 主な変更内容

### 1. リアクションベース → ボタンベースに移行

**従来のシステム:**
- 🇯🇵、🇬🇧、🗑️ のリアクション
- 2秒のクールダウン
- `ReactionLanguageManager`クラス

**新しいシステム:**
- Discord Message Components（ボタン）
- 15分のタイムアウト
- `ButtonLanguageManager`クラス

### 2. 新機能

#### ボタンによる言語切替（15分間有効）
- 🇯🇵 日本語ボタン
- 🇬🇧 Englishボタン  
- 🗑️ Deleteボタン

#### タイムアウト後のスラッシュコマンド
- `/switch ja` - 日本語に切替
- `/switch en` - 英語に切替

#### 自動無効化
- 15分経過後、ボタンは自動的に無効化
- Embedにタイムアウトメッセージが追加される

## コード変更詳細

### lib/discord_notify.py

#### ButtonLanguageManagerクラス
```python
class ButtonLanguageManager:
    def __init__(self):
        self.message_states = {}
        self.timeout_seconds = 15 * 60  # 15分
```

**主要メソッド:**
- `add_message()` - メッセージを登録
- `can_switch_language()` - 言語切替可能かチェック（権限 + タイムアウト）
- `is_expired()` - 15分タイムアウトチェック
- `switch_language()` - 言語切替実行

#### LanguageSwitchViewクラス
```python
class LanguageSwitchView(discord.ui.View):
    def __init__(self, message_id: int, target_user_id: int):
        super().__init__(timeout=15 * 60)  # 15分タイムアウト
```

**ボタンハンドラー:**
- `japanese_button()` - 日本語切替
- `english_button()` - 英語切替
- `delete_button()` - メッセージ削除

### cogs/language_switch_cog.py（新規作成）

`/switch`スラッシュコマンドの実装:
- ユーザーの全ての脱退通知メッセージを検索
- 言語切替を実行
- タイムアウト済みメッセージの処理

## 使用方法

### ユーザー向け

#### 15分以内（ボタン操作）
1. DM通知Embedを受信
2. 🇯🇵または🇬🇧ボタンをクリックして言語切替
3. 🗑️ボタンでメッセージ削除可能

#### 15分経過後（スラッシュコマンド）
1. `/switch ja` または `/switch en` コマンドを使用
2. 該当する脱退通知メッセージが自動更新される

### 開発者向け

#### テストコマンド
- `/test_departure_dm` - DM通知テスト（ボタン付き）
- `/test_departure` - チャンネル通知テスト

#### 実際の通知
- `notify_member_removed()` - ギルド脱退時に自動送信
- DM送信失敗時はバックアップチャンネルに送信

## セキュリティ・権限

### 権限制御
- 言語切替：対象ユーザーのみ可能
- メッセージ削除：対象ユーザーのみ可能
- スラッシュコマンド：対象ユーザーのメッセージのみ変更可能

### タイムアウト制御
- ボタン：15分で自動無効化
- メッセージ状態：ButtonLanguageManagerで管理
- 期限切れメッセージの自動処理

## エラーハンドリング

### ボタン操作時
- 権限不足時：エフェメラルメッセージで警告
- タイムアウト時：スラッシュコマンド使用指示
- 同じ言語選択時：現在の状態を通知

### スラッシュコマンド時
- メッセージが見つからない場合：適切なエラーメッセージ
- 更新失敗時：ログ出力とカウント表示

## 下位互換性

### 削除された機能
- `ReactionLanguageManager` クラス
- `handle_reaction_add()` 関数
- `setup_reaction_language_switching()` 関数
- `get_user_for_reaction_removal()` 関数

### 既存機能への影響
- `create_departure_embed()` - 変更なし
- `notify_member_removed()` - ボタンシステムに更新
- テストコマンド - 説明文のみ更新

## 技術的な改善点

### UX改善
- リアクション → ボタン（より直感的）
- 2秒クールダウン → 15分タイムアウト（より実用的）
- 明確な期限切れメッセージ

### パフォーマンス
- リアクション管理の不要化
- ボタンによる直接的なインタラクション
- 状態管理の簡素化

### 保守性
- コードの分離（LanguageSwitchCog）
- 明確な責任分担
- テスト可能な設計

## 今後の拡張可能性

- 追加言語のサポート
- カスタムタイムアウト設定
- 通知設定のパーソナライゼーション
- 統計情報の収集