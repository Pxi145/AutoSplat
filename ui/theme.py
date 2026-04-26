"""
ui/theme.py
Constantes visuelles et widgets de base réutilisables.

Responsabilités :
  - Palette de couleurs centralisée (modifier ici = impact global)
  - Activation du mode sombre CustomTkinter
  - Widget BentoCard réutilisable (conteneur arrondi)

Aucune logique métier — uniquement du style.
"""
import customtkinter as ctk

# ---------------------------------------------------------------------------
# Thème global
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("Dark")

# ---------------------------------------------------------------------------
# Palette de couleurs — toute modification ici se propage à l'ensemble de l'UI
# ---------------------------------------------------------------------------
THEME_BG         = "#121212"   # Fond principal de la fenêtre
THEME_CARD       = "#1e1e1e"   # Fond des cartes / panneaux
THEME_ACCENT     = "#ea5b0f"   # Orange principal (boutons actifs, titres)
THEME_TEXT       = "#ffffff"   # Texte principal
THEME_TEXT_GRAY  = "#888888"   # Texte secondaire / labels inactifs


# ---------------------------------------------------------------------------
# Widget de base réutilisable
# ---------------------------------------------------------------------------
class BentoCard(ctk.CTkFrame):
    """
    Conteneur arrondi style Bento Box.
    Utilisé pour regrouper visuellement des éléments liés (drop zone,
    paramètres, console, progression…).
    """

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=THEME_CARD,
            corner_radius=20,
            border_width=0,
            **kwargs,
        )
