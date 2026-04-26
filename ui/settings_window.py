"""
ui/settings_window.py
Fenêtre modale "Paramètres Avancés".

Responsabilités :
  - Afficher les paramètres actuels du pipeline
  - Valider et collecter les nouvelles valeurs
  - Appeler le callback on_save(new_config) sans accéder directement à l'App

COLMAP 4.0.2 — Section ajoutée :
  - Mode de reconstruction (Incrémental / Global GLOMAP)
  - Type de features (SIFT / ALIKED)
  - Type de matching (Séquentiel / Exhaustif)
  - Nouveaux modèles caméra (DIVISION, SIMPLE_DIVISION, FISHEYE)
"""
import customtkinter as ctk
from typing import Callable

from ui.theme import THEME_ACCENT, THEME_CARD, THEME_TEXT_GRAY


class SettingsWindow(ctk.CTkToplevel):
    """
    Fenêtre modale de configuration du pipeline.

    Args:
        master:   Fenêtre parente (AutoSplatApp).
        config:   Dict de configuration actuel (lu-seulement).
        on_save:  Callback appelé avec le nouveau dict si l'utilisateur sauvegarde.
        on_error: Callback appelé avec un message d'erreur si la validation échoue.
    """

    def __init__(
        self,
        master,
        config:   dict,
        on_save:  Callable[[dict], None],
        on_error: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._config   = config
        self._on_save  = on_save
        self._on_error = on_error

        self._build_ui()

    def _build_ui(self):
        self.title("Paramètres Avancés — COLMAP 4.0")
        self.geometry("540x780")
        self.attributes("-topmost", True)
        self.grab_set()  # Fenêtre modale

        ctk.CTkLabel(
            self,
            text="⚙️ Configuration du Pipeline",
            font=("Roboto", 20, "bold"),
            text_color=THEME_ACCENT,
        ).pack(pady=(20, 10))

        # Frame pour tout le contenu (avec scrollbar)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=0)

        form = scroll
        row = 0

        # ================================================================
        # Section COLMAP 4.0 — Mode de reconstruction
        # ================================================================
        ctk.CTkLabel(
            form, text="Mode COLMAP",
            font=("Roboto", 14, "bold"), text_color=THEME_ACCENT, anchor="w",
        ).grid(row=row, column=0, columnspan=2, pady=(10, 5), sticky="w")
        row += 1

        # Mode de reconstruction
        ctk.CTkLabel(form, text="Reconstruction :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_mode = ctk.CTkComboBox(
            form,
            values=[
                "Incrémental (Standard)",
                "Global GLOMAP (Rapide)",
            ],
            width=210,
            state="readonly",
        )
        # Map config value → display value
        mode_val = self._config.get("colmap_mode", "incremental")
        self._combo_mode.set(
            "Global GLOMAP (Rapide)" if mode_val == "global"
            else "Incrémental (Standard)"
        )
        self._combo_mode.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Type de features
        ctk.CTkLabel(form, text="Extraction Features :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_feature = ctk.CTkComboBox(
            form,
            values=[
                "SIFT (Standard)",
                "ALIKED N16 (IA Léger)",
                "ALIKED N32 (IA Précis)",
            ],
            width=210,
            state="readonly",
        )
        feat_val = self._config.get("colmap_feature_type", "SIFT")
        feat_display_map = {
            "ALIKED_N16ROT": "ALIKED N16ROT (IA Léger)",
            "ALIKED_N32":    "ALIKED N32 (IA Précis)",
        }
        self._combo_feature.set(feat_display_map.get(feat_val, "SIFT (Standard)"))
        self._combo_feature.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Type de matching
        ctk.CTkLabel(form, text="Mode Matching :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_matcher = ctk.CTkComboBox(
            form,
            values=[
                "Séquentiel (Vidéo)",
                "Exhaustif (Photos)",
            ],
            width=210,
            state="readonly",
        )
        matcher_val = self._config.get("colmap_matcher_type", "sequential")
        self._combo_matcher.set(
            "Exhaustif (Photos)" if matcher_val == "exhaustive"
            else "Séquentiel (Vidéo)"
        )
        self._combo_matcher.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Note explicative
        note = ctk.CTkLabel(
            form,
            text="ALIKED utilise un réseau de neurones (nécessite CUDA).\n"
                 "N16 = léger et rapide, N32 = plus précis.\n"
                 "GLOMAP est plus rapide pour les grands jeux de données.",
            font=("Roboto", 10), text_color=THEME_TEXT_GRAY,
            anchor="w", justify="left",
        )
        note.grid(row=row, column=0, columnspan=2, pady=(0, 5), sticky="w")
        row += 1

        # ================================================================
        # Section Extraction & COLMAP (paramètres existants)
        # ================================================================
        ctk.CTkLabel(
            form, text="Extraction & COLMAP",
            font=("Roboto", 14, "bold"), text_color=THEME_ACCENT, anchor="w",
        ).grid(row=row, column=0, columnspan=2, pady=(15, 5), sticky="w")
        row += 1

        # Overlap
        ctk.CTkLabel(form, text="Matcher Overlap :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._entry_overlap = ctk.CTkEntry(form, width=150)
        self._entry_overlap.insert(0, str(self._config.get("colmap_overlap", 20)))
        self._entry_overlap.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Modèle caméra (avec les nouveaux modèles COLMAP 4.0)
        ctk.CTkLabel(form, text="Modèle Caméra :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_camera = ctk.CTkComboBox(
            form,
            values=[
                "OPENCV",
                "SIMPLE_RADIAL",
                "SIMPLE_PINHOLE",
                "PINHOLE",
                "DIVISION",
                "SIMPLE_DIVISION",
                "FISHEYE",
            ],
            width=180,
            state="readonly",
        )
        self._combo_camera.set(self._config.get("colmap_camera_model", "OPENCV"))
        self._combo_camera.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Seuil flou
        ctk.CTkLabel(form, text="Seuil Flou par défaut :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._entry_blur = ctk.CTkEntry(form, width=150)
        self._entry_blur.insert(0, str(self._config.get("default_blur_threshold", 30)))
        self._entry_blur.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # ================================================================
        # Section Lichtfeld
        # ================================================================
        ctk.CTkLabel(
            form, text="Entraînement Lichtfeld",
            font=("Roboto", 14, "bold"), text_color=THEME_ACCENT, anchor="w",
        ).grid(row=row, column=0, columnspan=2, pady=(15, 5), sticky="w")
        row += 1

        # Itérations
        ctk.CTkLabel(form, text="Itérations :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._entry_iter = ctk.CTkEntry(form, width=150)
        self._entry_iter.insert(0, str(self._config.get("lichtfeld_iterations", 10000)))
        self._entry_iter.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Stratégie
        ctk.CTkLabel(form, text="Qualité d'entraînement :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_strat = ctk.CTkComboBox(
            form,
            values=["mrnf (Standard)", "mcmc (Haute Qualité)", "igs+ (Avancé)"],
            width=180,
            state="readonly",
        )
        self._combo_strat.set(self._config.get("lichtfeld_strategy", "mrnf (Standard)"))
        self._combo_strat.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Résolution
        ctk.CTkLabel(form, text="Résolution :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_resize = ctk.CTkComboBox(
            form,
            values=["auto", "1 (Original)", "2 (Moitié)", "4 (Quart)", "8 (Huitième)"],
            width=180,
            state="readonly",
        )
        self._combo_resize.set(self._config.get("lichtfeld_resize", "auto"))
        self._combo_resize.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Tile Mode (mémoire GPU)
        ctk.CTkLabel(form, text="Tile Mode (VRAM) :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_tile = ctk.CTkComboBox(
            form,
            values=["1 (Défaut)", "2 (Moyen)", "4 (Économe)"],
            width=180,
            state="readonly",
        )
        tile_val = str(self._config.get("lichtfeld_tile_mode", 1))
        tile_display = {"1": "1 (Défaut)", "2": "2 (Moyen)", "4": "4 (Économe)"}
        self._combo_tile.set(tile_display.get(tile_val, "1 (Défaut)"))
        self._combo_tile.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Max Splats
        ctk.CTkLabel(form, text="Splats Maximum :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._entry_max_splats = ctk.CTkEntry(form, width=150, placeholder_text="Défaut : 1 000 000")
        self._entry_max_splats.insert(0, str(self._config.get("lichtfeld_max_splats", 0)))
        self._entry_max_splats.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # Note explicative
        note = ctk.CTkLabel(
            form,
            text="Nombre splats de base 1 000 000",
            font=("Roboto", 10), text_color=THEME_TEXT_GRAY,
            anchor="w", justify="left",
        )
        note.grid(row=row, column=0, columnspan=2, pady=(0, 5), sticky="w")
        row += 1

        # Format d'export
        ctk.CTkLabel(form, text="Format d'export :", anchor="w").grid(
            row=row, column=0, pady=5, sticky="ew"
        )
        self._combo_export_fmt = ctk.CTkComboBox(
            form,
            values=["usd", "usda", "usdc", "spz", "html"],
            width=180,
            state="readonly",
        )
        self._combo_export_fmt.set(self._config.get("export_format", "usd"))
        self._combo_export_fmt.grid(row=row, column=1, pady=5, sticky="e")
        row += 1

        # MIP
        self._switch_mip = ctk.CTkSwitch(
            form, text="Activer l'anti-aliasing MIP", progress_color=THEME_ACCENT
        )
        if self._config.get("lichtfeld_mip", False):
            self._switch_mip.select()
        self._switch_mip.grid(row=row, column=0, columnspan=2, pady=(15, 5), sticky="w")
        row += 1

        # GUT (3DGUT — Gaussian Unscented Transform)
        self._switch_gut = ctk.CTkSwitch(
            form, text="Activer GUT (3DGUT — images distordues)",
            progress_color=THEME_ACCENT,
        )
        if self._config.get("lichtfeld_gut", False):
            self._switch_gut.select()
        self._switch_gut.grid(row=row, column=0, columnspan=2, pady=(5, 5), sticky="w")
        row += 1

        # Note explicative GUT
        note_gut = ctk.CTkLabel(
            form,
            text="GUT permet l'entraînement sur des caméras distordues\n"
                 "(grand-angle, fisheye) sans nécessiter d'undistortion.",
            font=("Roboto", 10), text_color=THEME_TEXT_GRAY,
            anchor="w", justify="left",
        )
        note_gut.grid(row=row, column=0, columnspan=2, pady=(0, 5), sticky="w")
        row += 1

        # ================================================================
        # Section Stockage
        # ================================================================
        ctk.CTkLabel(
            form, text="Gestion du Stockage",
            font=("Roboto", 14, "bold"), text_color=THEME_ACCENT, anchor="w",
        ).grid(row=row, column=0, columnspan=2, pady=(15, 5), sticky="w")
        row += 1

        self._switch_cleanup = ctk.CTkSwitch(
            form,
            text="Nettoyage Auto (supprime images & base de données après entraînement)",
            progress_color="#ef4444",
        )
        if self._config.get("auto_cleanup", False):
            self._switch_cleanup.select()
        self._switch_cleanup.grid(row=row, column=0, columnspan=2, pady=(5, 10), sticky="w")
        row += 1

        # ================================================================
        # Bouton Sauvegarder
        # ================================================================
        ctk.CTkButton(
            self,
            text="SAUVEGARDER",
            fg_color=THEME_ACCENT,
            hover_color="#ff7b3b",
            command=self._apply_and_close,
        ).pack(pady=20)

    def _apply_and_close(self):
        """Valide les champs, construit le nouveau config et appelle on_save."""
        try:
            # Extraction des valeurs affichées → clés de config
            mode_display    = self._combo_mode.get()
            # Map display → config pour le feature type
            feature_display = self._combo_feature.get()
            if "N32" in feature_display:
                feature_config = "ALIKED_N32"
            elif "N16ROT" in feature_display:
                feature_config = "ALIKED_N16ROT"
            else:
                feature_config = "SIFT"

            new_config = {
                # --- COLMAP 4.0 ---
                "colmap_mode":            "global" if "GLOMAP" in mode_display else "incremental",
                "colmap_feature_type":    feature_config,
                "colmap_matcher_type":    "exhaustive" if "Exhaustif" in self._combo_matcher.get() else "sequential",
                "colmap_overlap":          int(self._entry_overlap.get()),
                "colmap_camera_model":     self._combo_camera.get(),
                "default_blur_threshold":  int(self._entry_blur.get()),
                # --- Lichtfeld ---
                "lichtfeld_iterations":    int(self._entry_iter.get()),
                "lichtfeld_strategy":      self._combo_strat.get(),
                "lichtfeld_resize":        self._combo_resize.get(),
                "lichtfeld_tile_mode":     int(self._combo_tile.get().split(" ")[0]),
                "lichtfeld_mip":           bool(self._switch_mip.get()),
                "lichtfeld_max_splats":    int(self._entry_max_splats.get()),
                "lichtfeld_gut":           bool(self._switch_gut.get()),
                "export_format":           self._combo_export_fmt.get(),
                # --- Stockage ---
                "auto_cleanup":            bool(self._switch_cleanup.get()),
            }
        except (ValueError, Exception) as e:
            self._on_error(
                f"Erreur lors de la sauvegarde : {e}"
            )
            return

        self._on_save(new_config)
        self.destroy()
