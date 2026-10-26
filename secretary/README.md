# 秘書環境

Hermes + SilverBulletの専用Incus環境。`secretary.tf` の `secretary` をローカルtfvarsで設定して
OpenTofuで作成し、Debianホスト上で `./secretary/provision` を実行する。
コンテナ名は `secretary-dev`。`provision/run` からも専用処理へ振り分け、開発用エージェントは導入しない。
Macでは `dev secretary` が未設定項目を案内してHermesとSilverBulletを開く。

詳しい設定・接続・認証・バックアップ手順は、姉妹リポジトリ
[dotfiles_server/docs/secretary.md](https://github.com/0-0mfuji/dotfiles_server/blob/main/docs/secretary.md)。

固定版は `versions.env`。公式HermesインストーラーのSHA-256とcommit、SilverBulletバイナリの
SHA-256を確認して導入する。AIユーザーはsudo不可。文書と認証情報を分離する。
自動Suspendの変更や外部メール送信は行わない。
