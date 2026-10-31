#!/usr/bin/env python3
"""
Apex Racing GP - Music Optimizer
Optimizes MP3/audio files for smooth web streaming and Cloudflare R2 hosting.
- Re-encodes audio to optimal web streaming bitrate (128k/160k)
- Strips heavy embedded cover art and metadata junk (saves up to 60-70% file size)
- Normalizes loudness so game tracks have consistent volume
- Auto-detects bundled ffmpeg via imageio-ffmpeg or system PATH
"""

import os
import sys
import re
import shutil
import argparse
import subprocess
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add backend folder to sys.path if needed
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Detect default input source whether running inside monorepo or standalone
DEFAULT_INPUT = BACKEND_DIR / "music"
if (BACKEND_DIR.parent / "src" / "music").exists():
    DEFAULT_INPUT = BACKEND_DIR.parent / "src" / "music"
elif (BACKEND_DIR / "raw_music").exists():
    DEFAULT_INPUT = BACKEND_DIR / "raw_music"


def get_ffmpeg_binary() -> str:
    """Find FFmpeg binary using imageio_ffmpeg or system PATH."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except ImportError:
        pass

    path_exe = shutil.which("ffmpeg")
    if path_exe:
        return path_exe

    print("[ERROR] FFmpeg not found! Please install imageio-ffmpeg (`pip install imageio-ffmpeg`) or install FFmpeg.")
    sys.exit(1)


def clean_filename(filename: str, existing_names: set = None) -> str:
    """Clean filename by removing website watermarks, quality tags, trailing audio ID digits, and messy symbols."""
    stem = Path(filename).stem
    # Remove bracketed/parenthesized website promotions
    stem = re.sub(r'\(.*?(justnaija|naijaloaded|tooxclusive|waploaded|320kbps|official|audio).*?\)', '', stem, flags=re.I)
    stem = re.sub(r'\[.*?(justnaija|naijaloaded|tooxclusive|waploaded|320kbps|official|audio).*?\]', '', stem, flags=re.I)
    # Remove trailing track IDs (e.g. -554675, -281126)
    stem = re.sub(r'-\d{5,}$', '', stem)
    # Remove trailing/leading dashes, spaces, underscores
    stem = re.sub(r'[-_\s]+', '-', stem).strip('-')
    
    candidate = f"{stem}.mp3"
    if existing_names is not None:
        counter = 1
        while candidate.lower() in existing_names:
            counter += 1
            candidate = f"{stem}-{counter}.mp3"
        existing_names.add(candidate.lower())
    return candidate


def format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def optimize_audio_file(
    input_path: Path,
    output_path: Path,
    ffmpeg_exe: str,
    bitrate: str = "128k",
    normalize_loudness: bool = True
) -> bool:
    """
    Optimize an audio file:
    - -vn: strip video/cover art
    - -c:a libmp3lame: high quality MP3 encoder
    - -b:a <bitrate>: target bitrate
    - -ar 44100: standard 44.1kHz web audio sample rate
    - -ac 2: stereo
    - -map_metadata -1: strip bloated ID3 frames
    - -af loudnorm: broadcast loudness normalization
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        ffmpeg_exe,
        "-y",               # overwrite output
        "-i", str(input_path),
        "-vn",              # drop embedded album art
        "-map_metadata", "-1",  # drop unnecessary metadata
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-ar", "44100",
        "-ac", "2",
    ]

    if normalize_loudness:
        # Integrated loudness -16 LUFS (optimal for web game audio over engine sounds)
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])

    cmd.append(str(output_path))

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='replace')
        if result.returncode != 0:
            print(f"[FAIL] FFmpeg failed on {input_path.name}: {result.stderr[-250:]}")
            return False
        return True
    except Exception as e:
        print(f"[FAIL] Exception optimizing {input_path.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Optimize MP3 files for Apex Racing GP web & Cloudflare streaming.")
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(DEFAULT_INPUT),
        help=f"Input folder or file containing original audio tracks (default: {DEFAULT_INPUT.name})."
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(BACKEND_DIR / "optimized_music"),
        help="Output folder for optimized audio tracks (default: backend/optimized_music)."
    )
    parser.add_argument(
        "--bitrate", "-b",
        type=str,
        default="128k",
        choices=["96k", "128k", "160k", "192k", "256k"],
        help="Audio bitrate (default: 128k, optimal for fast web streaming)."
    )
    parser.add_argument(
        "--no-norm",
        action="store_true",
        help="Disable automatic loudness volume normalization."
    )

    args = parser.parse_args()

    ffmpeg_exe = get_ffmpeg_binary()
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    print(f"🎵 Apex Racing GP - MP3 Optimizer")
    print(f"===================================")
    print(f"• FFmpeg binary : {ffmpeg_exe}")
    print(f"• Target bitrate: {args.bitrate}")
    print(f"• Loudness norm : {'Disabled' if args.no_norm else 'Enabled (-16 LUFS)'}")
    print(f"• Input source  : {input_path}")
    print(f"• Output dir    : {output_dir}")
    print(f"===================================\n")

    files_to_process = []
    if input_path.is_file():
        files_to_process.append(input_path)
    elif input_path.is_dir():
        for ext in ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]:
            files_to_process.extend(list(input_path.glob(ext)))
    else:
        print(f"[ERROR] Input path does not exist: {input_path}")
        sys.exit(1)

    if not files_to_process:
        print("[WARN] No audio files found to process.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    total_orig = 0
    total_opt = 0
    existing_names = set()

    for idx, audio_file in enumerate(files_to_process, start=1):
        clean_name = clean_filename(audio_file.name, existing_names)
        out_file = output_dir / clean_name
        orig_size = audio_file.stat().st_size
        total_orig += orig_size

        print(f"[{idx}/{len(files_to_process)}] Processing: {audio_file.name}")
        print(f"    ↳ Output name: {clean_name}")
        print(f"    ↳ Original size: {format_bytes(orig_size)}")

        success = optimize_audio_file(
            input_path=audio_file,
            output_path=out_file,
            ffmpeg_exe=ffmpeg_exe,
            bitrate=args.bitrate,
            normalize_loudness=not args.no_norm
        )

        if success and out_file.exists():
            opt_size = out_file.stat().st_size
            total_opt += opt_size
            reduction = ((orig_size - opt_size) / orig_size) * 100
            print(f"    ✔ Optimized size: {format_bytes(opt_size)} (Saved {reduction:.1f}%)\n")
        else:
            print(f"    ❌ Optimization failed.\n")

    if total_orig > 0:
        overall_saved = ((total_orig - total_opt) / total_orig) * 100
        print("🎉 Optimization Complete!")
        print(f"• Total original size : {format_bytes(total_orig)}")
        print(f"• Total optimized size: {format_bytes(total_opt)}")
        print(f"• Total space saved   : {format_bytes(total_orig - total_opt)} ({overall_saved:.1f}% reduction)")
        print(f"• Files saved to      : {output_dir}\n")


if __name__ == "__main__":
    main()
