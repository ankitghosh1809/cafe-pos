import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
from app import app
