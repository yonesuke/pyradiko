# pyradiko

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Ruff](https://github.com/yonesuke/pyradiko/actions/workflows/ruff.yml/badge.svg)](https://github.com/yonesuke/pyradiko/actions/workflows/ruff.yml)


pythonでradiko音源を録音する

基本的にこちらのshell scriptをpythonに焼き直したもの。感謝。

- https://github.com/uru2/rec_radiko_ts

## Requirements

- Python 3.9+
- ffmpeg

## Installation

```bash
pip install git+https://github.com/yonesuke/pyradiko.git
```

or with uv:

```bash
uv add git+https://github.com/yonesuke/pyradiko.git
```

## Configuration

```bash
export RADIKO_MAIL="your mail address"
export RADIKO_PASSWORD="your password"
```

## Usage

オードリーのオールナイトニッポンを録音する例

```python
from pyradiko import RadikoRecorder

recorder = RadikoRecorder()

station = "LFR"  # ニッポン放送
start_time = "202501260100"  # format: YYYYMMDDHHMM
end_time = "202501260300"  # format: YYYYMMDDHHMM
output = "audrey.m4a"

res = recorder.record(station, start_time, end_time, output)
```
