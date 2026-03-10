#!/usr/bin/env bash
# Install PyTorch with MPS (Apple Silicon) support so embedding uses the GPU.
# Run from repo root: bash scripts/install_torch_mps.sh
# Then restart the app and run the pipeline again.

set -e
echo "Checking Python architecture..."
ARCH=$(python3 -c "import platform; print(platform.machine())")
echo "  Python arch: $ARCH"

if [ "$ARCH" != "arm64" ]; then
  echo ""
  echo "WARNING: You are not using ARM64 (Apple Silicon) Python. Current: $ARCH"
  echo "MPS requires native ARM64 Python on M1/M2/M3/M4 Macs."
  echo "Install ARM64 Python from https://www.python.org/downloads/ (macOS 64-bit universal2)"
  echo "or: arch -arm64 brew install python"
  echo ""
  read -p "Continue anyway? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then exit 1; fi
fi

echo ""
echo "Reinstalling PyTorch (this will enable MPS on Apple Silicon)..."
pip install 'torch>=2.0.0' --force-reinstall

echo ""
echo "Verifying MPS..."
python3 -c "
import torch
mps = getattr(torch.backends, 'mps', None)
built = mps.is_built() if mps else False
avail = mps.is_available() if mps else False
print('  MPS built:', built)
print('  MPS available:', avail)
if built and avail:
    print('  OK — embedding will use Apple Silicon GPU.')
else:
    print('  MPS still not available. Try: new terminal, or use ARM64 Python.')
"
