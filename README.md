# dotfile_infra

Development Server上のIncus環境 (Instance / Profile / Network / Storage) を
[OpenTofu](https://opentofu.org/) ([terraform-provider-incus](https://search.opentofu.org/provider/lxc/incus/latest))
で宣言的に管理するリポジトリ。HCL・providerスキーマはTerraform互換。

[dotfiles_server](https://github.com/0-0mfuji/dotfiles_server) 側は
「利用可能なリモート開発環境が存在すること」だけを前提にしており、
Instanceの作成・更新・削除はすべてこちらの責務。

## 目次

- [実行場所](#実行場所)
- [構成](#構成)
- [使い方](#使い方)
- [注意事項](#注意事項)

## 実行場所

**OpenTofuは Development Server上で実行する。** MacBook側には何もインストール
しない、という dotfiles_server の設計方針(Thin Client)に合わせるため。
Incus provider はリモートAPIではなくローカルのUnixソケットへ接続する。

```
MacBook --(ssh)--> Development Server --(このリポジトリをclone)--> tofu apply --> Incus (local socket)
```

## 構成

```
provision/                コンテナの中身の構築 (Node.js, git/jj, GitHub CLI (gh), Claude Code/Codex, DeepSeek Harness)
host/                     Debianホストの構築 (SSH/WoL/Tailscale/ZFS/Incus導入、ディスク初期化)
install.sh                Development ServerへOpenTofu CLIをインストールする
versions.tf              provider バージョン制約 ("terraform"ブロックのまま。OpenTofu互換)
provider.tf               incus provider設定 (ローカルソケット接続)
variables.tf               入力変数の定義
storage.tf                  既存ZFS poolをIncus storage poolとして登録
networks.tf                 Development Network (bridge) の定義
profiles.tf                  共通profile (dev-base) / GPU passthrough profile
instances.tf                 dev_instances変数をfor_eachしてInstanceを作成
outputs.tf                   作成されたInstance名の一覧
cloud-init/dev-base.yaml.tftpl   Instance初期化用cloud-init (devユーザー・SSH公開鍵・パッケージ)
terraform.tfvars.example     設定例 (ファイル名はOpenTofuでも変更不要)
```

Instance名は `<key>-dev` (例: `lang` → `lang-dev`) になっており、
dotfiles_server の `config/projects.conf` の instance列・SSHのHost名と
命名規則を合わせている。

## dev_instances の項目

`terraform.tfvars` の `dev_instances` に、keyごと(`<key>-dev` というInstanceになる)に書く。

| 項目 | 既定値 | 内容 |
| --- | --- | --- |
| `image` | `images:debian/13/cloud` | イメージ。cloud-initを使うため `/cloud` 版が必要 |
| `type` | `container` | `container` または `virtual-machine` |
| `cpu` / `memory` / `disk_size` | `4` / `4GiB` / `50GiB` | リソース上限 |
| `gpu` | `false` | `true` でGPU passthrough profileを付与 |
| `web_port` | なし | サーバーのTailscale IP (`mobile_bind_ip`) で待ち受ける、Web UIへの転送ポート (Incus proxy)。スマホ用。設定は [environments.md](https://github.com/0-0mfuji/dotfiles_server/blob/main/docs/environments.md#スマホ用の設定-tailnet) |
| `nesting` | `true` | `security.nesting`。Codexのサンドボックス(bubblewrap)がコンテナ内で動くために必要。変更には再起動が要る |
| `ip` | なし | Development Network内の固定IPv4 (例: `10.10.0.11`)。SSH設定と合わせる |
| `media` | なし | 共有ボリューム `media_path` (既定 `/srv/media`、ホストの `dev-tank/media`) を、コンテナの同じパスに渡す。`"rw"` か `"ro"`。動画制作 (video / voice / blender) の素材と成果物の受け渡し用。コンテナを作り直しても残る |
| `packages` | `[]` | 基本パッケージ (`git` `curl` `build-essential` 等) に加えて入れるaptパッケージ |

## 使い方

前提: 最小インストール直後のDebian 13 (UEFI) から、Incusを動かせる状態にする
`host/` の手順を先に済ませておくこと ([host/README.md](host/README.md))。
ZFS dataset (`dev-tank/incus`) は `host/storage-init` が作り、このリポジトリは
それをIncusのstorage poolとして登録する。

```sh
# OpenTofu CLIが未導入の場合のみ (Debian: APT経由でインストールされる)
./install.sh

cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars   # storage_pool / dev_network / ssh_public_key / dev_instances

tofu init
tofu plan
tofu apply
```

## 更新をサーバーへ反映する

Macで変更をコミットしてGitHubへpushした後、Development Serverでこのリポジトリを更新する。
サーバーのcheckoutを直接編集せず、Gitを更新経路にする。

```sh
cd ~/dotfile_infra
git pull --ff-only
```

変更後は対象Instanceに対して `./provision/run <instance>` など、このREADMEや各環境の手順に
記載されたprovisionコマンドを実行する。OpenTofuの構成変更は、`tofu plan` で差分を確認してから
`tofu apply` する。pull前にサーバー側の変更が残っている場合は、消さずにコミットまたは退避してから更新する。

## 注意事項

- **cloud-initはInstanceの初回起動時にしか実行されない。** `packages` などを変えても、
  既存のInstanceには反映されない。反映するには作り直す
  (`tofu apply -replace='incus_instance.dev["os"]'`)。
- **作り直すとInstance内のデータ (ソースコード含む) は消える。** 先にGitHubへpushすること。
- 作成される `dev` ユーザーは、パスワードなしでsudoを使える (コンテナ内のみ。ログインは公開鍵のみ)。
- `storage.tf` / `networks.tf` の資産には `prevent_destroy` を付けている。
  誤った `tofu destroy` で開発データ・プロジェクトデータやNetwork設定が
  消えるのを防ぐため。
- GPU passthroughを使うInstance (`gpu = true`) は自動Suspendとの相性を
  個別に確認すること (dotfiles_server 側 `server/systemd/README.md` 参照)。
- `terraform.tfvars` はGit管理しない。公開鍵以外に秘密情報は基本的に
  含まれない想定だが、環境固有の値のためコミットしない。
- provider/リソースのスキーマはバージョンにより変わることがあるため、
  実際に `tofu init` したバージョンの公式ドキュメントを確認すること。

## Flutter / Android

`flutter-dev` は `provision/flutter.sh` がFlutter (Dart同梱)、Turso CLI、
corepack/pnpm、Linuxビルドツール、JDK 21とAndroid SDK/NDKを導入する。
Flutter・Android Command-line Tools・SDK/NDKの版は `provision/versions.env` で管理する。
Honoなどのアプリ依存はプロジェクトのlockfileに置く。

```sh
./provision/run flutter-dev
```

初回にAndroid SDKのライセンス確認が求められた場合は、devユーザーで
`~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --licenses` を実行してから再実行する。
MacのWebプレビューとAndroidエミュレーターへのAPK転送は
[dotfiles_serverのFlutter手順](https://github.com/0-0mfuji/dotfiles_server/blob/main/docs/flutter.md) を参照。

GitHub CLI (`gh`) は全コンテナの共通プロビジョニングで導入する。既存コンテナには `./provision/run` で反映する (稼働中の全 `*-dev`。停止中のものは起動後に実行)。認証は各コンテナで行い、Mac の `dev` 起動時に未認証なら案内する。

### 私用秘書（NanoMuse）

`systemd-inhibit --what=sleep --mode=block ./provision/run secretary-dev` で導入・更新する。
既定はNanoMuse 1.0.7。固定commitとSHA-256は `secretary/versions.env`。
Macの `dev secretary` でlocalhost:8787の認証付きUIを開く。
文書は `/srv/secretary/documents` をSilverBulletと共有する。
旧試用workspaceは自動統合し、統合前の両方をroot専用backupに保存する。
旧Hermes・gatewayの起動経路は廃止し、履歴・認証情報・旧実行ファイルはroot専用領域へ退避する。
外部連携は既存OAuth/readonly MCP。詳細はdotfiles_serverの `docs/secretary.md`。

秘書をスマホで開く場合は `secretary.nanomuse_port = 8787` と `mobile_bind_ip` を設定し、
計画を確認してapply後にprovisionを実行する。Macの `dev secretary mobile` でTailnet内専用の認証付きQRを表示する。
