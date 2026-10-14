#!/usr/bin/env bash
# Verify the paper-video toolchain. Prints the python to use on the last line.
PY="${PAPER_VIDEO_PY:-$HOME/miniconda3/envs/paper-video/bin/python}"
ok=1
for b in ffmpeg ffprobe pdftoppm latex dvisvgm; do
  command -v "$b" >/dev/null || { echo "MISSING: $b"; ok=0; }
done
[ -x "$PY" ] || { echo "MISSING: python env at $PY"; ok=0; }
if [ -x "$PY" ]; then
  "$PY" -c "import manim" 2>/dev/null || { echo "MISSING: manim in $PY"; ok=0; }
  "$PY" -c "import kokoro, soundfile" 2>/dev/null || echo "WARN: kokoro not installed (only needed for free TTS)"
fi
if [ $ok = 0 ]; then
  cat <<'EOF'
Setup (no sudo needed):
  conda create -y -n paper-video -c conda-forge --override-channels python=3.11 manim
  ~/miniconda3/envs/paper-video/bin/pip install kokoro soundfile
  # LaTeX: needs latex + dvisvgm + standalone/preview packages (texlive-latex-extra on Debian/Ubuntu)
  # Or set PAPER_VIDEO_PY to another python that has manim.
EOF
  exit 1
fi
echo "OK $PY"
