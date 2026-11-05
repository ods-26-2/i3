"""ponto de entrada na raiz do repo (Docker, B4 e a cadeia chamam `python main.py`); o
componente esta em I3/, ver I3/run_calibracao.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "I3"))

from run_calibracao import main  # noqa: E402

main()
