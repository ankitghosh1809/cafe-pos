@echo off
echo.
echo  ===  Brew ^& Co. POS — Setup  ===
echo.

cd backend

echo [1/3] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

echo [2/3] Installing dependencies...
pip install -r requirements.txt

echo [3/3] Initialising database and starting server...
echo.
echo  Backend running at http://localhost:5000
echo  Open frontend\index.html in your browser
echo.
python app.py
