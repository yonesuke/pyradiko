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

```bash
uv add git+https://github.com/yonesuke/pyradiko.git
```

or with pip:

```bash
pip install git+https://github.com/yonesuke/pyradiko.git
```

## Configuration

```bash
export RADIKO_MAIL="your_email@example.com"
export RADIKO_PASSWORD="your_password"
```

## Usage

### 基本的な録音（メタデータ・カバーアート画像自動埋め込み）

`recorder.record(...)` を実行すると、Radiko公式の番組表APIから番組タイトル、放送日、出演者情報、番組説明、公式カバーアートワーク画像を自動取得し、録音した `.m4a` ファイルにタグとして埋め込みます。

```python
from pyradiko import RadikoRecorder

recorder = RadikoRecorder()

station = "LFR"  # ニッポン放送
start_time = "202610110100"  # format: YYYYMMDDHHMM
end_time = "202610110300"    # format: YYYYMMDDHHMM
output = "audrey.m4a"

# 自動で番組情報・アートワーク画像が埋め込まれます (auto_metadata=True がデフォルト)
res = recorder.record(station, start_time, end_time, output)
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

### カスタムメタデータの上書き

手動でタグ情報を指定したい場合：

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

## Error Handling

認証失敗やAPIエラー時は、専用の例外クラスが送出されます。

- `RadikoAuthError`: ログインや認証トークン取得の失敗時（`PermissionError` を継承）
- `RadikoPlaylistError`: 放送局XMLやHLSプレイリストURL取得の失敗時
- `RadikoRecordError`: ffmpeg コマンド失敗時
