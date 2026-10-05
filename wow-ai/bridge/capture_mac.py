#!/usr/bin/env python3
"""macOS counterpart of capture.ps1 / capture_x11.py: screen-captures the
top-left corner of the native WoW: Forever client and decodes the WoWAI pixel
strip (see Codec.lua in the addon). Prints one JSON line per new message to
stdout, with the same {info|warn|error|id,text} contract as the other capture
scripts. Started by bridge.js.

Uses only the Python stdlib plus the built-in macOS screencapture binary and
osascript. The first run will trigger System Settings permissions for
System Events (window discovery) and Screen Recording (screencapture).

  capture_mac.py --test-image strip.png   decode a PNG once and exit (tests)
  capture_mac.py --probe out.png          save what the capture sees once and exit
  capture_mac.py --window-name NAME       match a window by title instead of process name
"""

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import zlib

p = argparse.ArgumentParser()
p.add_argument("--cell", type=int, default=4)
p.add_argument("--cells", type=int, default=200)
p.add_argument("--max-rows", type=int, default=48)
p.add_argument("--interval-ms", type=int, default=250)
p.add_argument("--process-name", default="World of Warcraft")
p.add_argument("--window-name", default="")
p.add_argument("--test-image", default="")
p.add_argument("--probe", default="")
# macOS specific: how many pixels to search down for the strip (title bar + menu bar)
p.add_argument("--y-slack", type=int, default=80, help="vertical search margin in physical pixels")
# region to capture, in screen points (independent of Retina scale)
p.add_argument("--region-w", type=int, default=1000)
p.add_argument("--region-h", type=int, default=400)
args = p.parse_args()

CELL, CELLS, MAXROWS = args.cell, args.cells, args.max_rows
W, H = CELLS * CELL, MAXROWS * CELL
XSLACK = 8
YSLACK = args.y_slack


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Decoder: identical rules to capture.ps1 and capture_x11.py
# ---------------------------------------------------------------------------

def cell_value(px, c, r, ox=0, oy=0):
    rr, gg, bb = px(ox + c * CELL + CELL // 2, oy + r * CELL + CELL // 2)
    return (4 if rr >= 128 else 0) + (2 if gg >= 128 else 0) + (1 if bb >= 128 else 0)


def has_magic(px, ox, oy):
    acc = 0
    for i in range(6):  # 18 bits cover the two magic bytes
        acc = (acc << 3) | cell_value(px, i, 0, ox, oy)
    return (acc >> 2) == 0xC71A


def decode(px, ox=0, oy=0):
    acc = 0
    nbits = 0
    out = bytearray()
    needed = 6
    total = CELLS * MAXROWS
    for i in range(total):
        acc = (acc << 3) | cell_value(px, i % CELLS, i // CELLS, ox, oy)
        nbits += 3
        while nbits >= 8:
            out.append((acc >> (nbits - 8)) & 0xFF)
            nbits -= 8
            acc &= (1 << nbits) - 1
            if len(out) == 2 and (out[0] != 0xC7 or out[1] != 0x1A):
                return None
            if len(out) == 6:
                length = out[4] * 256 + out[5]
                needed = 8 + length
                if needed > total * 3 // 8:
                    return {"error": "length"}
            if len(out) >= needed:
                break
        if len(out) >= needed:
            break
    if len(out) < needed:
        return {"error": "truncated"}
    length = out[4] * 256 + out[5]
    s1 = s2 = 0
    for k in range(2, 6 + length):
        s1 = (s1 + out[k]) % 255
        s2 = (s2 + s1) % 255
    if out[6 + length] != s1 or out[7 + length] != s2:
        return {"error": "checksum"}
    text = bytes(out[6:6 + length]).decode("utf-8", errors="replace")
    return {"id": out[2] * 256 + out[3], "text": text}


def find_and_decode(px, width, height, hint):
    """Decode at the last good offset, else search a top-left window for the magic.
    The vertical search window is larger because the macOS title bar pushes the
    UIParent top-left down."""
    cands = [hint] if hint else []
    cands += [(dx, dy) for dy in range(YSLACK + 1) for dx in range(XSLACK + 1)]
    for ox, oy in cands:
        if ox + W > width or oy + H > height:
            continue
        if has_magic(px, ox, oy):
            return decode(px, ox, oy), (ox, oy)
    return None, hint


# ---------------------------------------------------------------------------
# PNG in/out (tests, --probe, and screencapture output)
# ---------------------------------------------------------------------------

def read_png(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat = 8, b""
    width = height = depth = ctype = None
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if depth != 8 or ctype not in (2, 6):
        raise ValueError("only 8-bit RGB/RGBA PNGs are supported")
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * bpp
    rows, prev = [], bytearray(stride)
    for y in range(height):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        rows.append(line)
        prev = line

    def px(x, y):
        o = x * bpp
        row = rows[y]
        return row[o], row[o + 1], row[o + 2]
    return px, width, height


def write_png(path, px, width, height):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(px(x, y))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


if args.test_image:
    px, w, h = read_png(args.test_image)
    msg, _ = find_and_decode(px, w, h, None)
    emit(msg if msg else {"error": "no valid strip in image"})
    sys.exit(0)


# ---------------------------------------------------------------------------
# macOS window discovery and screen capture
# ---------------------------------------------------------------------------

def run_osascript(script):
    """Write the AppleScript to a temp file and run it; multi-line scripts are
    unreliable when passed inline to osascript -e."""
    fd, path = tempfile.mkstemp(suffix=".scpt")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(script)
        proc = subprocess.run(["osascript", path], capture_output=True, text=True, timeout=10)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "osascript failed")
    return proc.stdout.strip()


def find_window_bounds():
    """Return (x, y, w, h) in screen points for the best matching window."""
    want = args.process_name
    title = args.window_name

    if title:
        script = '''tell application "System Events"
    set allProcs to every process
    repeat with p in allProcs
        try
            set wins to every window of p whose name contains "%s"
            if (count wins) > 0 then
                set w to item 1 of wins
                tell w
                    set {x, y} to position
                    set {ww, hh} to size
                end tell
                return (x as string) & "," & (y as string) & "," & (ww as string) & "," & (hh as string)
            end if
        end try
    end repeat
end tell
return ""''' % title.replace('"', '\\"')
    else:
        script = '''tell application "System Events"
    set pList to every process whose name contains "%s"
    if (count pList) = 0 then
        return ""
    end if
    set p to item 1 of pList
    tell p
        if not (exists front window) then
            return ""
        end if
        set w to front window
        tell w
            set {x, y} to position
            set {ww, hh} to size
        end tell
        return (x as string) & "," & (y as string) & "," & (ww as string) & "," & (hh as string)
    end tell
end tell
return ""''' % want.replace('"', '\\"')

    out = run_osascript(script)
    if not out:
        return None
    parts = out.split(",")
    if len(parts) != 4:
        return None
    return tuple(int(float(p.strip())) for p in parts)


def capture_region(x, y, w, h, out_path):
    """Use screencapture to grab a region of the screen into a PNG.
    Coordinates are in screen points (macOS logical coordinates); the resulting
    PNG is in device pixels, which is what the decoder expects."""
    cmd = [
        "screencapture",
        "-R%d,%d,%d,%d" % (int(x), int(y), int(w), int(h)),
        "-x",  # no sound
        out_path,
    ]
    subprocess.run(cmd, check=True, timeout=5)


def grab(out_path):
    """Find the WoW window, capture the top-left region, and return a pixel accessor."""
    bounds = find_window_bounds()
    if not bounds:
        return None
    x, y, ww, wh = bounds
    rw = min(args.region_w, ww)
    rh = min(args.region_h, wh)
    if rw <= 0 or rh <= 0:
        return None
    try:
        capture_region(x, y, rw, rh, out_path)
    except Exception as e:
        return {"error": "screencapture failed: %s" % e}
    return read_png(out_path)


def run():
    if args.probe:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            g = grab(tmp)
            if g is None:
                emit({"error": "no game window found"})
                sys.exit(1)
            if isinstance(g, dict):
                emit(g)
                sys.exit(1)
            px, width, height = g
            write_png(args.probe, px, width, height)
            msg, off = find_and_decode(px, width, height, None)
            emit({"info": "saved %dx%d to %s" % (width, height, args.probe), "strip": msg, "offset": off})
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return

    last_key = None
    last_warn = 0.0
    bounds = None
    bounds_at = 0
    hint = None
    while True:
        start = time.time()
        # Refresh window bounds every 5 s so moving/resizing the window is picked up.
        if bounds is None or start - bounds_at > 5:
            bounds = find_window_bounds()
            bounds_at = start
        if not bounds:
            emit({"info": "waiting for %s window" % (args.window_name or args.process_name)})
            time.sleep(3)
            continue
        x, y, ww, wh = bounds
        rw = min(args.region_w, ww)
        rh = min(args.region_h, wh)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            try:
                capture_region(x, y, rw, rh, tmp)
            except Exception as e:
                emit({"warn": "screencapture failed: %s" % e})
                time.sleep(1)
                continue
            px, width, height = read_png(tmp)
            msg, hint = find_and_decode(px, width, height, hint)
            if msg and msg.get("error"):
                if time.time() - last_warn >= 5:
                    last_warn = time.time()
                    emit({"warn": "strip seen but rejected: " + msg["error"]})
            elif msg:
                key = "%d:%s" % (msg["id"], msg["text"])
                if key != last_key:
                    last_key = key
                    emit(msg)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        elapsed = time.time() - start
        sleep = max(0, args.interval_ms / 1000.0 - elapsed)
        if sleep:
            time.sleep(sleep)


try:
    run()
except KeyboardInterrupt:
    pass
