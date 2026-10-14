# pyradiko

[![CI](https://github.com/yonesuke/pyradiko/actions/workflows/ci.yml/badge.svg)](https://github.com/yonesuke/pyradiko/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

PythonでRadiko音源を録音するライブラリ。

基本的にこちらのshell scriptをPythonに焼き直したもの。感謝。
- https://github.com/uru2/rec_radiko_ts

## Requirements

- Python 3.10+
- ffmpeg (`ffmpeg`, `ffprobe`)

## Installation

### 1. 最低限（録音機能のみ・軽量）

`httpx2` のみ依存関係に含まれ、`mutagen` はインストールされません。

```bash
uv add git+https://github.com/yonesuke/pyradiko.git
```

or with pip:

```bash
pip install git+https://github.com/yonesuke/pyradiko.git
```

### 2. メタデータ自動付与機能付き（mutagen 込み）

Radiko公式の番組情報やジャケット写真（カバーアート）を `.m4a` に埋め込む機能もまとめて導入する場合：

```bash
uv add "pyradiko[metadata] @ git+https://github.com/yonesuke/pyradiko.git"
```

or with pip:

```bash
pip install "pyradiko[metadata] @ git+https://github.com/yonesuke/pyradiko.git"
```

※ 通常インストール後でも、`uv add mutagen` または `pip install mutagen` を追加するだけでメタデータ機能が利用可能になります。

## Configuration

```bash
export RADIKO_MAIL="your_email@example.com"
export RADIKO_PASSWORD="your_password"
```

## Usage

### 基本的な録音（デフォルト）

```python
from pyradiko import RadikoRecorder

recorder = RadikoRecorder()

station = "LFR"  # ニッポン放送
start_time = "202610110100"  # format: YYYYMMDDHHMM
end_time = "202610110300"    # format: YYYYMMDDHHMM
output = "audrey.m4a"

# デフォルトではメタデータ埋め込みは行わず、高速かつ軽量に録音のみを実行します
res = recorder.record(station, start_time, end_time, output)
```

### メタデータ・カバーアート画像の自動埋め込み (`embed_metadata=True`)

`embed_metadata=True` を渡すと、Radiko公式の番組表APIから番組タイトル、放送日、出演者情報、番組説明、公式カバーアートワーク画像を自動取得し、録音した `.m4a` ファイルにタグとして埋め込みます。

※ `mutagen` が未インストールの場合は、親切なインストール案内メッセージとともに `ImportError` が発生します。

```python
res = recorder.record(
    station,
    start_time,
    end_time,
    output,
    embed_metadata=True,  # 番組情報と公式ジャケット写真を自動埋め込み
)
```

### カスタムメタデータの手動指定

```python
res = recorder.record(
    station,
    start_time,
    end_time,
    output,
    metadata={
        "title": "オードリーのANN",
        "artist": "オードリー",
        "album": "オールナイトニッポン",
        "genre": "Radio",
    },
)
```

### 番組情報の事前取得

番組表APIから番組メタデータを直接取得することも可能です。

```python
from pyradiko import get_program_by_time

prog = get_program_by_time("LFR", "202610110100")
if prog:
    print(prog.title)           # オードリーのオールナイトニッポン
    print(prog.pfm)             # オードリー(若林正恭/春日俊彰)
    print(prog.broadcast_date)  # 2026-10-11
    print(prog.img)             # カバーアート画像URL
```

## Error Handling

認証失敗やAPIエラー時は、専用の例外クラスが送出されます。

- `RadikoAuthError`: ログインや認証トークン取得の失敗時（`PermissionError` を継承）
- `RadikoPlaylistError`: 放送局XMLやHLSプレイリストURL取得の失敗時
- `RadikoRecordError`: ffmpeg コマンド失敗時
- `ImportError`: `embed_metadata=True` 指定時に `mutagen` が未インストールの場合
