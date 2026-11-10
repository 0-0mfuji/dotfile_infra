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

PLaMoモデルだけのリビジョン更新は、サーバーでこのrepoをpullした後 `./secretary/plamo-model-update` を使います。実行中の翻訳が共有ロックを保持している場合は更新を拒否します。新しい版を別ディレクトリに取得して検査してから切り替え、失敗時は現行版を残します。

### Container startup processing

After updating the host checkout with `git pull --ff-only`, run
`./secretary/pipeline-deploy`. It installs only inside `secretary-dev`.
No host services or public ports are added.

The container enables `secretary-pipeline-gpu.service` (medical examination
PDFs first, then PLaMo English/Japanese article and Kandel copies),
`secretary-pipeline-narou.service` (fixed existing 2,000-candidate library,
3-second request delay), and `secretary-pipeline-upload.timer`.
They resume on container boot; completed input hashes/output files are reused.
GPU workers share the existing `translation.lock`. PLaMo retains its model in
one process and checkpoints each sentence. Its source/model hash prevents
using translations from a different input or model revision.
If a sentence produces no Japanese, the article is recorded under
`/var/lib/secretary-pipeline/review/articles/` with its source hash, model and
sentence index. No partial article is sent to the outbox. The worker continues
with other articles and reports `review_required` after completing the remaining
work. Remove a review record only after diagnosing the issue to allow a retry;
other worker errors retain the normal retry behavior.

`/var/lib/secretary-pipeline` holds status, logs, sentence caches, the fixed
article snapshot, bilingual EPUBs and completed article outbox. Source PDFs,
EPUBs and bookmarks are retained. OCR uses CUDA/300dpi/offline models and the
existing X3/layout/readability conversion tools, without independent Tesseract
comparison. Existing Linux results are verified against source hashes and
output presence before skipping; missing medical files are processed separately
in `data/study/medical-auto`. Low disk (6 GiB admission, 5 GiB OCR/download
reserve) or a job error causes delayed retries with saved progress.

Publisher credentials remain with `secretary-karakeep`. The AI user does not
join its credential group. The publisher creates text bookmarks with original
ID/source link, `【英日対訳】`, original tags plus `英日対訳` and `Plamo翻訳`,
original manual list memberships, and original `createdAt` plus 5 seconds.
Metadata/content are read back before completion. A durable create intent plus
source/hash marker prevents blind duplicate creation if a response is lost.
An ambiguous outcome requires operator reconciliation. Originals are not updated
or deleted. Automated translation is a draft, not human or medical review.

Status: `incus exec secretary-dev -- runuser -u secretary -- /opt/secretary-tools/bin/python /opt/secretary/secretary-pipeline.py status`.

Modal provides an optional authenticated RPC, with no public URL. Deploy
`files/modal-plamo-app.py` using the Modal CLI after setting the workspace spend
limit. The isolated client `/opt/secretary-modal/bin/python
/opt/secretary/modal-plamo-client.py` reads JSON lines containing `text` or
`texts` (up to 256) and writes JSON lines. Document extraction, caching and
publishing remain local. The normal automatic pipeline continues to use local
GPU; calling the Modal RPC explicitly is separately billable. Keep the Modal
token in the secretary user's private configuration and never commit it.
NanoMuse/DSH may use `secretary_tools`'s `pipeline_status` without a shell.
Stop/resume with `systemctl stop/start secretary-pipeline-gpu.service
secretary-pipeline-narou.service secretary-pipeline-upload.timer` inside the
container. Stop `secretary-pipeline-upload.service` too if an upload is active.
Disabling the corresponding units prevents startup on subsequent boots.
The existing host idle policy detects GPU work and the existing OCR/download
executables; this deployment does not alter the host suspend configuration.
