#!/usr/bin/env python3
"""
safecopy — Samba-friendly file copy tool with MD5 verification
"""

import argparse
import contextlib
import hashlib
import logging
import os
import sys
import time
import shutil
from pathlib import Path
from typing import NamedTuple

# ANSI colors
C_RESET = "\033[0m"
C_GREEN = "\033[38;5;76m"
C_RED   = "\033[38;5;196m"
C_BOLD  = "\033[1m"
C_HIDE_CURSOR = "\033[?25l"
C_SHOW_CURSOR = "\033[?25h"

log = logging.getLogger(__name__)


class Task(NamedTuple):
    src: Path
    base: Path
    size: int


class Progress:
    def __init__(self, total_chunks, total_bytes):
        self.total_chunks = total_chunks
        self.total_bytes = total_bytes
        self.done_chunks = 0
        self.done_bytes = 0
        self.current_file = ""
        self.term_width, _ = shutil.get_terminal_size((80, 24))
        self._last_chunk_time = None
        self._last_speed = None

    def chunk_done(self, chunk_size):
        now = time.time()
        if self._last_chunk_time is not None:
            elapsed = now - self._last_chunk_time
            self._last_speed = (
                chunk_size / (1024 * 1024) / elapsed if elapsed > 0 else None
            )
        self._last_chunk_time = now
        self.done_chunks += 1

    def draw(self):
        pct = (
            (self.done_bytes / self.total_bytes) * 100
            if self.total_bytes > 0 else 0
        )
        clean_file = self.current_file.replace("\n", "").replace("\r", "")
        max_file_len = self.term_width - 10
        if len(clean_file) > max_file_len:
            clean_file = "..." + clean_file[-max_file_len + 3:]

        chunk_str = f"{self.done_chunks}/{self.total_chunks}"
        speed_str = (
            f"{self._last_speed:6.2f} MB/s"
            if self._last_speed is not None else "    N/A   "
        )
        sys.stdout.write(
            f"\033[2K\r{C_BOLD}{chunk_str:>12}{C_RESET}"
            f"  {speed_str}"
            f"  {pct:5.1f}%"
            f"  {clean_file}"
        )
        sys.stdout.flush()


def parse_chunk_size(value: str) -> int:
    raw = value.strip().lower()
    if raw.endswith("mb"):
        size = int(float(raw[:-2]) * 1024 * 1024)
    elif raw.endswith("kb"):
        size = int(float(raw[:-2]) * 1024)
    else:
        raise ValueError(
            f"Invalid chunk size '{value}'. Examples: 512kb, 4mb"
        )
    if size < 4096:
        raise ValueError(
            f"Chunk size must be at least 4kb, got '{value}'"
        )
    return size


def collect_tasks(sources):
    tasks = []
    total_size = 0
    for s in sources:
        if s.name in (".", "..") or not s.exists():
            continue
        if s.is_dir():
            for root, _, files in os.walk(s):
                for f in files:
                    fp = Path(root) / f
                    with contextlib.suppress(OSError):
                        sz = fp.stat().st_size
                        tasks.append(Task(fp, s.parent, sz))
                        total_size += sz
        else:
            with contextlib.suppress(OSError):
                sz = s.stat().st_size
                tasks.append(Task(s, s.parent, sz))
                total_size += sz
    return tasks, total_size


def copy_file(src, target, chunk_size, pause, bytes_processed, prog):
    src_md5 = hashlib.md5()
    file_offset = 0

    try:
        with open(src, "rb") as fsrc, open(target, "wb") as fdst:
            for data in iter(lambda: fsrc.read(chunk_size), b""):
                fdst.write(data)
                src_md5.update(data)
                file_offset += len(data)
                prog.done_bytes = bytes_processed + file_offset
                prog.chunk_done(len(data))
                prog.draw()
                if pause > 0:
                    time.sleep(pause)
    except KeyboardInterrupt:
        raise
    except OSError as e:
        log.error("copy failed %s -> %s: %s", src, target, e)
        return False

    target_md5 = hashlib.md5()
    try:
        with open(target, "rb") as ft:
            for d in iter(lambda: ft.read(chunk_size), b""):
                target_md5.update(d)
    except OSError as e:
        log.error("verify failed %s: %s", target, e)
        return False

    return src_md5.hexdigest() == target_md5.hexdigest()


def main():
    logging.basicConfig(
        stream=sys.stderr, level=logging.ERROR,
        format="%(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="safecopy — safe file copy with MD5 verification"
    )
    parser.add_argument("paths", nargs="+", help="Source(s) and destination")
    parser.add_argument(
        "--move", action="store_true",
        help="Delete source after successful copy",
    )
    parser.add_argument(
        "--chunk-size", type=str, default="4mb",
        help="Chunk size, e.g. 128kb, 4mb (default: 4mb)",
    )
    parser.add_argument(
        "--pause", type=float, default=0,
        help="Pause between chunks in seconds (default: 0)",
    )
    args = parser.parse_args()

    if len(args.paths) < 2:
        parser.error("source and destination required")

    dest = Path(args.paths[-1]).absolute()
    sources = [Path(p).absolute() for p in args.paths[:-1]]

    try:
        chunk_size = parse_chunk_size(args.chunk_size)
    except ValueError as e:
        parser.error(str(e))

    tasks, total_size = collect_tasks(sources)
    if not tasks:
        print("No data to copy.")
        return

    total_chunks = sum(max(1, -(-t.size // chunk_size)) for t in tasks)
    prog = Progress(total_chunks, total_size)
    sys.stdout.write(C_HIDE_CURSOR)

    failed = []
    bytes_processed = 0
    for task in tasks:
        target = dest / task.src.relative_to(task.base)
        prog.current_file = str(task.src.relative_to(task.base))
        target.parent.mkdir(parents=True, exist_ok=True)

        ok = copy_file(
            task.src, target, chunk_size, args.pause, bytes_processed, prog,
        )
        if ok and args.move:
            with contextlib.suppress(OSError):
                task.src.unlink()
        elif not ok:
            failed.append(task.src)

        bytes_processed += task.size

    sys.stdout.write(C_SHOW_CURSOR + "\n")
    if failed:
        print(f"\n{C_RED}Failed:{C_RESET}")
        for f in failed:
            print(f"  {f}")
    else:
        print(f"\n{C_GREEN}Done.{C_RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write(C_SHOW_CURSOR + C_RESET + "\n")
        print(f"\n{C_RED}Interrupted.{C_RESET}")
        sys.exit(1)
