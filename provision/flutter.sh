#!/usr/bin/env bash
# agents.sh から読み込む。Flutter/Dart と Hono 用の実行環境を整える。
install_flutter() {
  local sdk="$HOME/sdk/flutter-$FLUTTER_VERSION" tmp p
  local packages=(clang cmake ninja-build pkg-config libgtk-3-dev libstdc++-14-dev git-lfs sqlite3 zip unzip xz-utils libglu1-mesa)
  local missing=()
  for p in "${packages[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
  if [ "${#missing[@]}" -gt 0 ]; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
  fi
  mkdir -p "$HOME/sdk"
  if [ ! -d "$sdk/.git" ]; then
    tmp="$(mktemp -d "$HOME/sdk/.flutter.XXXXXX")"
    git -C "$tmp" init -q
    git -C "$tmp" remote add origin https://github.com/flutter/flutter.git
    git -C "$tmp" fetch --depth 1 origin "refs/tags/$FLUTTER_VERSION:refs/tags/$FLUTTER_VERSION"
    [ "$(git -C "$tmp" rev-parse "$FLUTTER_VERSION^{commit}")" = "$FLUTTER_COMMIT" ] || { log "flutter: tag commit mismatch"; rm -rf "$tmp"; return 1; }
    git -C "$tmp" checkout -q -b stable "$FLUTTER_COMMIT"
    mv "$tmp" "$sdk"
  fi
  [ "$(git -C "$sdk" rev-parse HEAD)" = "$FLUTTER_COMMIT" ] || { log "flutter: unexpected SDK commit in $sdk"; return 1; }
  # 過去にSHAだけで導入したSDKにも、Flutterの版判定に必要なタグを補う。
  if ! git -C "$sdk" show-ref --verify --quiet "refs/tags/$FLUTTER_VERSION"; then
    git -C "$sdk" fetch --depth 1 origin "refs/tags/$FLUTTER_VERSION:refs/tags/$FLUTTER_VERSION"
    [ "$(git -C "$sdk" rev-parse "$FLUTTER_VERSION^{commit}")" = "$FLUTTER_COMMIT" ] || return 1
    git -C "$sdk" checkout -q -B stable "$FLUTTER_COMMIT"
    rm -f "$sdk/bin/cache/flutter.version.json"
  fi
  git -C "$sdk" update-ref refs/remotes/origin/stable "$FLUTTER_COMMIT"
  git -C "$sdk" branch --set-upstream-to=origin/stable stable >/dev/null
  # /usr/local/bin は SSH 非対話シェルや systemd のエージェントからも見える。
  sudo ln -sfn "$sdk/bin/flutter" /usr/local/bin/flutter
  sudo ln -sfn "$sdk/bin/dart" /usr/local/bin/dart
  sudo corepack enable
  git lfs install --skip-repo
  install_turso
  turso --version
  flutter --no-version-check config --enable-web --enable-linux-desktop
  flutter --no-version-check precache --web --linux
  flutter --version
  dart --version
  log "flutter: ready (Hono はプロジェクトの package.json / lockfile で管理)"
}

install_android() {
  local sdk="$HOME/Android/Sdk" tmp f
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-21-jdk-headless unzip
  export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
  export ANDROID_HOME="$sdk"
  if [ ! -x "$sdk/cmdline-tools/$ANDROID_TOOLS_VERSION/bin/sdkmanager" ]; then
    tmp="$(mktemp -d)"
    f="commandlinetools-linux-${ANDROID_TOOLS_VERSION}_latest.zip"
    curl -fsSL "https://dl.google.com/android/repository/$f" -o "$tmp/$f"
    echo "$ANDROID_TOOLS_SHA256  $tmp/$f" | sha256sum -c -
    unzip -q "$tmp/$f" -d "$tmp"
    mkdir -p "$sdk/cmdline-tools"
    mv "$tmp/cmdline-tools" "$sdk/cmdline-tools/$ANDROID_TOOLS_VERSION"
    rm -rf "$tmp"
  fi
  ln -sfn "$ANDROID_TOOLS_VERSION" "$sdk/cmdline-tools/latest"
  export PATH="$sdk/cmdline-tools/latest/bin:$sdk/platform-tools:$PATH"
  sdkmanager --sdk_root="$sdk" "platform-tools" "platforms;android-$ANDROID_API" "build-tools;$ANDROID_BUILD_TOOLS" "ndk;$ANDROID_NDK_VERSION" "cmake;3.22.1"
  [ -x "$sdk/platform-tools/adb" ] && [ -f "$sdk/platforms/android-$ANDROID_API/android.jar" ] && [ -d "$sdk/ndk/$ANDROID_NDK_VERSION" ] || {
    log "android: SDK packages missing; review licenses with sdkmanager --licenses, then rerun provision/run flutter-dev"
    return 1
  }
  flutter --no-version-check config --android-sdk "$sdk" --jdk-dir "$JAVA_HOME"
  flutter --no-version-check precache --android
  local marker="# >>> android (provision) >>>"
  for f in "$HOME/.profile" "$HOME/.bashrc"; do
    touch "$f"
    grep -qF "$marker" "$f" && continue
    { printf '%s\nexport JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64\nexport ANDROID_HOME="$HOME/Android/Sdk"\nexport PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"\n# <<< android (provision) <<<\n' "$marker"; cat "$f"; } > "$f.new" && mv "$f.new" "$f"
  done
  log "android: JDK 21 / API $ANDROID_API / NDK $ANDROID_NDK_VERSION installed"
}
