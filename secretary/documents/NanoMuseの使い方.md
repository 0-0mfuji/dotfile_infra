# NanoMuseの使い方

Macで `dev secretary` または `secretary` を実行します。
ChatでAIと会話し、Libraryで作成したMarkdownや添付資料を一覧・プレビューできます。

AIの返答・文書は日本語です。Web UIは現時点ではEnglishまたは简体中文です。

モデルの変更はSettings → Connectionsで行います。

- Provider: Other OpenAI-compatible endpoint
- Base URL: `https://ollama.com/v1`
- Model: 利用するOllama Cloudモデル
- API key: Ollama Cloudのキー。「No key」を外して入力し、Save → Testの順に操作

例: 「今週の趣味の計画を立てて、plans/今週の計画.mdに保存して」

Libraryの保存先は `/srv/secretary/documents`。SilverBulletも同じ文書を開きます。
旧試用フォルダはこの保存先への互換リンクになっています。

メール・Plane・Karakeepの接続はMacの `secretary setup gmail` / `outlook` / `plane` / `karakeep`、
共有予定は `secretary timetree-config` から設定します。外部連携は読み取り専用です。
接続設定後はNanoMuseが再起動し、MCPツール一覧を更新します。

SilverBulletを開く場合は `secretary notes`（ログイン設定が必要）。
Hermesの旧設定・履歴は保持していますが、通常は起動しません。
