# video テンプレート

`video-dev` で動画を作るプロジェクトの雛形。**コピーして使う** (`~/src/video` など)。
Remotion (映像) と、Remotion の外側の Python (音声・字幕・画像処理) を、どちらも lockfile で固定してある。

```sh
cp -r ~/dotfile_infra/templates/video ~/src/video && cd ~/src/video
git init && pnpm install --frozen-lockfile    # Remotion (版は package.json で固定、^なし)
uv sync                                        # Python 3.12 + audio / subs / vision (uv.lock)
pnpm dev                                       # Remotion Studio (:3000)。Macからは `dev video` が開く
pnpm render Hello out/hello.mp4                # 書き出し
```

## 中身

| パス | 内容 |
| --- | --- |
| `package.json` / `pnpm-lock.yaml` | Remotion 4.0.536 の関連パッケージを**同じ版**で固定。React 19 |
| `pyproject.toml` / `uv.lock` | Python 3.12。`audio` / `subs` / `vision` のグループ (`uv sync --no-default-groups --group audio`) |
| `src/Hello.tsx` | 日本語の字幕が豆腐 (□) にならないことの確認用。豆腐なら `fonts-noto-cjk` が無い |
| `scripts/voice.py` | `$VOICE_URL` の VOICEVOX を呼び、`/srv/media/audio` に wav と音素タイミングを書く (標準ライブラリのみ) |

## 注意

- Remotion の版を上げるときは、**全 `@remotion/*` を同じ版**にする (`pnpm up "remotion" "@remotion/*" --latest` のあと、`package.json` の `^` を外す)。
- 3D・演出など、必要になったときに足すもの。版は**必ず入っている Remotion に揃える**:
  ```sh
  pnpm add --save-exact three @react-three/fiber @react-three/drei @types/three @remotion/three@4.0.536
  pnpm add --save-exact gsap @remotion/gsap@4.0.536 lottie-web @remotion/lottie@4.0.536 @remotion/rive@4.0.536 @remotion/light-leaks@4.0.536
  ```
- `pnpm-workspace.yaml` の `allowBuilds` は、esbuild のビルドスクリプトを許可している (pnpm 11 は既定で止める)。
- Remotion のライセンスには条件がある (収益化する・会社で使う場合は確認する)。
- 呼び出し先の VOICEVOX は `VOICE_URL` だけで決まる。`video-dev` は `voice-dev` の起動を知らない (起動は `dev video` の役目)。
- 素材と成果物は `/srv/media/{audio,renders,out}` (共有ボリューム。コンテナを作り直しても残る) に置く。
