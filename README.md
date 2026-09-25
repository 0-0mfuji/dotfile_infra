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
install.sh                Development ServerへOpenTofu CLIをインストールする
versions.tf              provider バージョン制約 ("terraform"ブロックのまま。OpenTofu互換)
provider.tf               incus provider設定 (ローカルソケット接続)
variables.tf               入力変数の定義
storage.tf                  既存ZFS poolをIncus storage poolとして登録
networks.tf                 Development Network (bridge) の定義
profiles.tf                  共通profile (dev-base) / GPU passthrough profile
instances.tf                 dev_instances変数をfor_eachしてInstanceを作成
outputs.tf                   作成されたInstance名の一覧
cloud-init/dev-base.yaml.tftpl   Instance初期化用cloud-init (SSH公開鍵の投入等)
terraform.tfvars.example     設定例 (ファイル名はOpenTofuでも変更不要)
```

Instance名は `<key>-dev` (例: `lang` → `lang-dev`) になっており、
dotfiles_server の `config/projects.conf` の instance列・SSHのHost名と
命名規則を合わせている。

## 使い方

前提: Development Server上に Incus, 対象イメージが利用できること。
ZFS poolとDevelopment Network用のbridgeは事前にホスト側で用意しておく
(このリポジトリは既存のpool/networkをIncusへ登録するだけ)。

```sh
# OpenTofu CLIが未導入の場合のみ (Debian: APT経由でインストールされる)
./install.sh

cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars   # storage_pool / dev_network / ssh_public_key / dev_instances

tofu init
tofu plan
tofu apply
```

## 注意事項

- `storage.tf` / `networks.tf` の資産には `prevent_destroy` を付けている。
  誤った `tofu destroy` で開発データ・プロジェクトデータやNetwork設定が
  消えるのを防ぐため。
- GPU passthroughを使うInstance (`gpu = true`) は自動Suspendとの相性を
  個別に確認すること (dotfiles_server 側 `server/systemd/README.md` 参照)。
- `terraform.tfvars` はGit管理しない。公開鍵以外に秘密情報は基本的に
  含まれない想定だが、環境固有の値のためコミットしない。
- provider/リソースのスキーマはバージョンにより変わることがあるため、
  実際に `tofu init` したバージョンの公式ドキュメントを確認すること。
