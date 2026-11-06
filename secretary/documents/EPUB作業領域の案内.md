# EPUBと教材データの配置

| 場所 | 用途 |
|---|---|
| `/srv/secretary/documents` | NanoMuse・DSH・Codexの文書作業領域 |
| `/srv/secretary/karakeep-tool/data` | 原本・取得データ・OCRキャッシュ・EPUB |
| `data/study/text-reflow-library` | 移行前ライブラリの保全用 |
| `data/study/text-reflow-linux` | 現在の全件変換先（Karakeep-toolからの相対パス） |
| `/home/secretary/.dsh/skills` | DSH用のスキル |
| `/opt/secretary` | 管理用MCP・再開プログラム。作業用shellで探索しない |

DSH等のサンドボックスはdata領域を直接公開していない。専用MCPは別の実行環境でdataを参照できる。
見えないディレクトリをshellで繰り返し探索したり、データ消失と判断したりしない。

EPUBを修正するときはlist_epubsで対象を確認し、export_epubで文書作業領域へ独立コピーする。
返るworkspace_pathをDSHやCodexのファイルツールで扱い、必要なコード実行はそのクライアントの権限設定に従う。
既存のkt-*スキルが対応する処理はinspectで引数・Linux対応を確認してから専用MCP経路で実行する。
元EPUBや実行中のキャッシュへ修正版を直接上書きしない。修正後のEPUB構造検査も別途必要。
スキルは配置済みでも、すべての修正ツールの実動作が確認済みという意味ではない。

全件変換の状態確認はstudy_status。利用者が残り全部の正式再開を依頼し、実行が停止している場合だけstudy_resumeを使う。
起動要求がqueuedならstudy_status(wait_seconds=45)で確認する。再開用コマンドや/optの実装を探す必要はない。
DSH/Codexではツール名にmcp__secretary_tools__、NanoMuseではsecretary_tools__が付く。
