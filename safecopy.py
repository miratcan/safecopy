#!/usr/bin/env python3
"""
safecopy — Amiga X-Copy / defrag-style, Samba-friendly file copy tool
"""

import argparse
import hashlib
import os
import sys
import time
import shutil
import signal
from pathlib import Path

# ANSI colors
C_RESET   = "\033[0m"
C_GREY    = "\033[38;5;240m"
C_BLUE    = "\033[38;5;33m"
C_YELLOW  = "\033[38;5;214m"
C_GREEN   = "\033[38;5;76m"
C_RED     = "\033[38;5;196m"
C_BOLD    = "\033[1m"
C_CLEAR   = "\033[2J\033[H"
C_HOME    = "\033[H"
C_HIDE_CURSOR = "\033[?25l"
C_SHOW_CURSOR = "\033[?25h"

BLOCK_FULL  = "\u25A0"  # ■ filled
BLOCK_EMPTY = "\u25A1"  # □ empty

def signal_handler(sig, frame):
    sys.stdout.write(C_SHOW_CURSOR + C_RESET + "\n")
    print(f"\n{C_RED}Interrupted.{C_RESET}")
    os._exit(1)

signal.signal(signal.SIGINT, signal_handler)

class XCopyVisualizer:
    def __init__(self, total_bytes):
        self.total_bytes = total_bytes
        self.done_bytes = 0
        self.term_width, _ = shutil.get_terminal_size((80, 24))
        self.grid_width = self.term_width - 4
        self.grid_height = 12
        self.total_blocks = self.grid_width * self.grid_height
        self.blocks = [0] * self.total_blocks
        self.current_file = ""
        self.start_time = time.time()

    def update_range(self, byte_offset, length, state):
        if self.total_bytes == 0:
            return
        start_idx = int((byte_offset / self.total_bytes) * self.total_blocks)
        end_idx = int(
            ((byte_offset + length) / self.total_bytes) * self.total_blocks
        )
        for i in range(start_idx, min(end_idx + 1, self.total_blocks)):
            self.blocks[i] = state

    def draw(self):
        sys.stdout.write(C_HOME)
        print(f"{C_BOLD}--- SAFE-COPY V1.0 (X-COPY MODE) ---{C_RESET}")
        print("-" * self.term_width)

        grid_output = []
        for y in range(self.grid_height):
            line = "  "
            for x in range(self.grid_width):
                idx = y * self.grid_width + x
                state = self.blocks[idx]
                if state == 1:
                    line += f"{C_BLUE}{BLOCK_FULL}"
                elif state == 2:
                    line += f"{C_YELLOW}{BLOCK_FULL}"
                elif state == 3:
                    line += f"{C_GREEN}{BLOCK_FULL}"
                elif state == 4:
                    line += f"{C_RED}{BLOCK_FULL}"
                else:
                    line += f"{C_GREY}{BLOCK_EMPTY}"
            grid_output.append(line + C_RESET)
        print("\n".join(grid_output))

        print("-" * self.term_width)

        elapsed = time.time() - self.start_time
        speed = (
            (self.done_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        )
        pct = (
            (self.done_bytes / self.total_bytes) * 100
            if self.total_bytes > 0 else 0
        )

        clean_file = self.current_file.replace("\n", "").replace("\r", "")
        if len(clean_file) > self.term_width - 15:
            clean_file = "..." + clean_file[-(self.term_width - 18):]

        w = self.term_width
        print(f" {C_BOLD}File :{C_RESET} {clean_file:<{w-15}}")
        print(
            f" {C_BOLD}Speed:{C_RESET} {speed:6.2f} MB/s"
            f"  |  {C_BOLD}Progress:{C_RESET} {pct:5.1f}%"
        )
        state_str = "Copying...  " if pct < 100 else "Done!       "
        print(f" {C_BOLD}State:{C_RESET} " + state_str)
        sys.stdout.flush()


def parse_chunk_size(value: str) -> int:
    raw = value.strip().lower()
    if raw.endswith("mb"):
        size = int(float(raw[:-2]) * 1024 * 1024)
    elif raw.endswith("kb"):
        size = int(float(raw[:-2]) * 1024)
    else:
        raise ValueError(f"Invalid chunk size '{value}'. Examples: 512kb, 4mb")
    if size < 4096:
        raise ValueError(f"Chunk size must be at least 4kb, got '{value}'")
    return size


def collect_tasks(sources):
    all_tasks = []
    total_size = 0
    for s in sources:
        if s.name in (".", ".."):
            continue
        if not s.exists():
            continue
        if s.is_dir():
            for root, dirs, files in os.walk(s):
                for f in files:
                    fp = Path(root) / f
                    try:
                        sz = fp.stat().st_size
                        all_tasks.append(
                            {'src': fp, 'base': s.parent, 'size': sz}
                        )
                        total_size += sz
                    except OSError:
                        continue
        else:
            try:
                sz = s.stat().st_size
                all_tasks.append(
                    {'src': s, 'base': s.parent, 'size': sz}
                )
                total_size += sz
            except OSError:
                continue
    return all_tasks, total_size


def copy_file(src, target, chunk_size, pause, bytes_processed, viz):
    import traceback
    src_md5 = hashlib.md5()
    try:
        with open(src, "rb") as fsrc:
            fdst = open(target, "wb")
            try:
                file_offset = 0
                chunk_count = 0
                while data := fsrc.read(chunk_size):
                    fdst.write(data)
                    src_md5.update(data)
                    file_offset += len(data)
                    viz.update_range(
                        bytes_processed + file_offset - len(data),
                        len(data),
                        1,
                    )
                    viz.done_bytes = bytes_processed + file_offset
                    chunk_count += 1
                    if chunk_count % 4 == 0:
                        viz.draw()
                    if pause > 0:
                        time.sleep(pause)
            finally:
                try:
                    fdst.close()
                except OSError as e:
                    sys.stderr.write(f"\nCLOSE ERROR: {target}: {e}\n")
                    sys.stderr.flush()

        target_md5 = hashlib.md5()
        with open(target, "rb") as ft:
            while d := ft.read(chunk_size):
                target_md5.update(d)

        return src_md5.hexdigest() == target_md5.hexdigest()

    except Exception as e:
        sys.stderr.write(f"\nERROR: {src} -> {target}: {e}\n")
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="safecopy — Amiga-style safe file copy"
    )
    parser.add_argument(
        "paths", nargs="+", help="Source(s) and destination"
    )
    parser.add_argument(
        "--move", action="store_true",
        help="Delete source after successful copy",
    )
    parser.add_argument(
        "--chunk-size", type=str, default="1mb",
        help="Chunk size, e.g. 512kb, 4mb (default: 1mb)",
    )
    parser.add_argument(
        "--pause", type=float, default=0,
        help="Pause between chunks in seconds (default: 0)",
    )
    args = parser.parse_args()

    if len(args.paths) < 2:
        print("Error: source and destination required.")
        return

    dest = Path(args.paths[-1]).absolute()
    sources = [Path(p).absolute() for p in args.paths[:-1]]

    all_tasks, total_size = collect_tasks(sources)

    if total_size == 0:
        print("No data to copy.")
        return

    try:
        chunk_size = parse_chunk_size(args.chunk_size)
    except ValueError as e:
        print(f"Error: {e}")
        return

    viz = XCopyVisualizer(total_size)
    sys.stdout.write(C_CLEAR + C_HIDE_CURSOR)

    bytes_processed = 0
    for task in all_tasks:
        src = task['src']
        target = dest / src.relative_to(task['base'])
        viz.current_file = str(src.relative_to(task['base']))
        target.parent.mkdir(parents=True, exist_ok=True)

        viz.update_range(bytes_processed, task['size'], 2)
        ok = copy_file(
            src, target, chunk_size, args.pause, bytes_processed, viz
        )
        if ok:
            viz.update_range(bytes_processed, task['size'], 3)
            if args.move:
                try:
                    src.unlink()
                except OSError as e:
                    sys.stderr.write(f"\nDELETE ERROR: {src}: {e}\n")
                    sys.stderr.flush()
        else:
            viz.update_range(bytes_processed, task['size'], 4)
            viz.current_file = f"ERROR: {src.name}"

        bytes_processed += task['size']
        viz.done_bytes = bytes_processed
        viz.draw()

    sys.stdout.write(C_SHOW_CURSOR + "\n")
    print("\n\nDone.")

if __name__ == "__main__":
    main()
