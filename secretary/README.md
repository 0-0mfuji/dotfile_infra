# 秘書環境

NanoMuse + SilverBulletの専用Incus環境です。`secretary.tf` の `secretary` を
サーバーのGit管理外tfvarsで設定し、OpenTofuで作成します。

サーバーで `git pull --ff-only` した後、次の入口から導入・更新します。

```sh
systemd-inhibit --what=sleep --mode=block ./provision/run secretary-dev
```

内部では秘書専用の `secretary/provision` に振り分けます。開発用エージェントは導入しません。
Macでは `dev secretary` でNanoMuseを開き、`dev secretary setup` で連携設定を行います。

固定版は `versions.env` で管理し、NanoMuseソースとSilverBulletのSHA-256を検証します。
旧Hermes・gatewayの導入と起動経路は廃止しました。既存の履歴・認証情報・旧実行ファイルは
`retire-hermes` がroot専用の `/var/backups/secretary/retired-hermes-*` に退避します。
再実行時にユーザーの文書・NanoMuseの認証設定を上書きしません。

詳細は [秘書の手順](https://github.com/0-0mfuji/dotfiles_server/blob/main/docs/secretary.md)を参照してください。

### 教材生成コードだけの更新

モデルや依存パッケージを変更しない `study/` の追加更新には、MacでKarakeep-toolの変更を公開し、このrepoの `versions.env` と `tooling/catalog.json` を更新・公開した後、サーバーで `git pull --ff-only`、`./secretary/update-tools-source` を実行できます。作業ツリーの変更・変換処理の実行中・巻き戻し・study外の変更がある場合は停止して保全します。無関係な取得処理やAIサービスは停止しません。その他の更新は通常のprovisionを使います。

PLaMoモデルだけのリビジョン更新は、サーバーでこのrepoをpullした後 `sudo ./secretary/plamo-model-update` を使います。実行中の翻訳が共有ロックを保持している場合は更新を拒否します。新しい版を別ディレクトリに取得して検査してから切り替え、失敗時は現行版を残します。
