#!/usr/bin/env python3
"""VOICEVOX ENGINE で台本を読み上げ、wav と音素タイミング (audio_query の JSON) を書き出す。

  VOICE_URL=http://10.10.0.21:50021 python scripts/voice.py "こんにちは" --speaker 3 --out /srv/media/audio/hello

- 呼び出し先は環境変数 VOICE_URL だけで決まる。video-dev は voice-dev の起動を知らない (起動は `dev` の役目)。
  繋がらなければ、理由を出して終了コード1で終わる。別のVOICEVOX (Macのローカルなど) にも差し替えられる。
- 標準ライブラリだけで動く (uv sync 不要)。--speaker は話者のスタイルID (3=ずんだもん ノーマル など。GET /speakers で一覧)。
- 音声のキャラクターごとの利用規約 (クレジット表記など) に従うこと。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def call(base: str, path: str, params: dict, body: bytes | None = None, timeout: int = 60) -> bytes:
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=body if body is not None else b"", method="POST")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", help="読み上げる文")
    ap.add_argument("--speaker", type=int, default=3, help="話者のスタイルID (既定 3)")
    ap.add_argument("--out", required=True, help="出力の接頭辞。<out>.wav と <out>.query.json を書く")
    args = ap.parse_args()

    base = os.environ.get("VOICE_URL", "").rstrip("/")
    if not base:
        print("VOICE_URL が未設定です (例: http://10.10.0.21:50021)。provision.env に VOICE_URL を書いて ./provision/run video-dev", file=sys.stderr)
        return 1
    try:
        query = call(base, "/audio_query", {"text": args.text, "speaker": args.speaker})
        wav = call(base, "/synthesis", {"speaker": args.speaker}, body=query)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        print(f"VOICEVOX ({base}) に接続できません: {e}\n"
              "voice-dev が起動しているか確認してください (`dev video` は起動します)。起動直後は応答まで少し待つことがあります。", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(f"{args.out}.wav", "wb") as f:
        f.write(wav)
    with open(f"{args.out}.query.json", "w", encoding="utf-8") as f:
        json.dump(json.loads(query), f, ensure_ascii=False, indent=2)  # accent_phrases の moras に音素の長さ (口パク用)
    print(f"{args.out}.wav ({len(wav)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
