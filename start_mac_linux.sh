#!/usr/bin/env bash
set -e

echo ""
echo "  ===  Brew & Co. POS — Setup  ==="
echo ""

cd "$(dirname "$0")/backend"

echo "[1/3] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[2/3] Installing dependencies..."
pip install -r requirements.txt

echo "[3/3] Starting backend server..."
echo ""
echo "  Backend → http://localhost:5000"
echo "  Open frontend/index.html in your browser"
echo ""
python app.py
