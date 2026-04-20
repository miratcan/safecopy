# safecopy

Amiga X-Copy inspired file copy tool with MD5 verification and a retro block display. Built for slow or unreliable targets like Samba shares and USB disks.

```
--- SAFE-COPY V1.0 (X-COPY MODE) ---
------------------------------------------------------------------------
  ■■■■■■■■■■■■■■■■■■■■□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□
  □□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□
  ...
------------------------------------------------------------------------
 File : Music/Tony Anderson - Tenderness.mp3
 Speed:   0.21 MB/s  |  Progress:  24.3%
 State: Copying...
```

**Block states:**
- Blue `■` — copying
- Yellow `■` — verifying (MD5)
- Green `■` — verified OK
- Red `■` — error

## Installation

Requires Python 3.8+.

```bash
pip install git+https://github.com/miratcanb/safecopy.git
```

Or download a pre-built binary from [Releases](https://github.com/miratcanb/safecopy/releases) (no Python required).

## Usage

```bash
# Copy files or directories
safecopy file.mp3 /Volumes/backup/
safecopy ~/Music/ /Volumes/backup/Music/

# Copy multiple sources
safecopy file1.mp3 file2.mp3 dir/ /Volumes/backup/

# Move (delete source after verified copy)
safecopy --move ~/Photos/ /Volumes/backup/Photos/

# Custom chunk size (default: 1mb)
safecopy --chunk-size 8mb ~/Music/ /Volumes/backup/
safecopy --chunk-size 256kb ~/Music/ /Volumes/backup/
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--move` | off | Delete source after successful copy |
| `--chunk-size` | `4mb` | Transfer chunk size (e.g. `512kb`, `4mb`) |
| `--pause` | `0` | Seconds to wait between chunks |

## How it works

1. Copies each file in chunks
2. Computes MD5 of the source during copy
3. Reads back the destination and computes its MD5
4. Marks green on match, red on mismatch
5. With `--move`, deletes source only after verified match

## Development

```bash
git clone https://github.com/miratcanb/safecopy.git
cd safecopy
uv sync --dev
uv run pytest tests/
```

## License

MIT
