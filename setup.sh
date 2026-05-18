#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Aluminum Pro Trader – AWS Ubuntu Server Setup
# Run once:  chmod +x setup.sh && ./setup.sh
# ─────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

echo "=== Installing system packages ==="
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip screen

echo "=== Installing Python dependencies ==="
pip3 install --upgrade pip -q
pip3 install -r requirements.txt

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To start the bot in the background (survives SSH disconnect):"
echo ""
echo "  screen -S jarvis"
echo "  python3 bot.py"
echo "  (press Ctrl+A then D to detach)"
echo ""
echo "To reattach later:"
echo "  screen -r jarvis"
echo ""
echo "To check logs (if you ran with nohup instead):"
echo "  tail -f jarvis.log"
