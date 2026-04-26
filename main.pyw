"""
main.pyw
Point d'entrée d'AutoSplat Studio.

Ce fichier est le seul à exécuter pour lancer l'application.
Il délègue immédiatement à ui.app.AutoSplatApp — aucune logique ici.

Lancement :
  - Via le raccourci .vbs  (sans console Windows)
  - Via `python main.pyw`  (avec console pour le debug)
"""
import sys
import os

# Garantit que le dossier racine du projet est dans sys.path,
# quel que soit le répertoire de travail courant au lancement.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ui.app import AutoSplatApp


def main():
    app = AutoSplatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
