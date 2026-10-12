# host: Development Serverのホスト構築

Debian 13 (UEFI) を最小インストールした直後の状態から、Incusを動かせる状態まで
持っていくためのスクリプト群。Incus Instance自体はリポジトリ直下のOpenTofuで作る。

## 手順

サーバー上で、**一般ユーザーから**実行する (rootシェルで `sudo` を実行しない。
公開鍵の確認先が `/root` になって失敗する):

```sh
git clone git@github.com:0-0mfuji/dotfile_infra.git
cd dotfile_infra/host

sudo ./setup.sh          # 00-base, 10-ssh, 20-network, 30-zfs, 40-incus
```

| step | 内容 |
| --- | --- |
| `00-base` | 基本パッケージ |
| `10-ssh` | パスワード認証を無効化 (authorized_keysが空なら中断) |
| `20-network` | WoL永続化 (`wol@<iface>.service`)、Tailscale導入。MACアドレスを表示する |
| `30-zfs` | ZFSパッケージ導入 (`contrib`有効化) |
| `40-incus` | Incus導入、`incus-admin`グループへ追加 |

特定のstepだけなら `sudo ./setup.sh 00 40`。

`20-network` の後に、Tailscaleへのログインを対話式で行う:

```sh
sudo tailscale up --hostname=dev-server
```

`10-ssh` はパスワードログインを止める。実行前に、別のターミナルから鍵でログインできることを
確認すること。

## ストレージ(ディスクを消す。手動で一度だけ)

`/dev/disk/by-id/` のパスで指定する。マウント中・NTFS/Windowsらしいディスクは拒否し、
実行前にディスクIDの入力を求める。

```sh
ls -l /dev/disk/by-id/ | grep -v part      # 対象を確認 (下はこのサーバーでの例)
sudo ./storage-init /dev/disk/by-id/ata-CT1000BX500SSD1_2102E4E5327B
```

単一ディスクのためZFS poolに冗長性はない。ディスクを増設したら
`zpool attach dev-tank <既存> <新規>` でmirrorにできる。

## 次

リポジトリ直下に戻り、`./install.sh`(OpenTofu導入) →
`terraform.tfvars` (`zfs_source = "dev-tank/incus"`) → `tofu init && tofu apply`。
