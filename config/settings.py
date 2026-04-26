"""
config/settings.py
Gestion de la configuration persistante d'AutoSplat Studio.
Responsabilités :
  - Définir les valeurs par défaut du pipeline
  - Charger / sauvegarder le fichier bin/config.json
  - Aucune dépendance sur l'UI ou le core
"""
import os
import json


# ---------------------------------------------------------------------------
# Valeurs par défaut — utilisées si config.json est absent ou incomplet
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    # --- COLMAP 4.0 ---
    "colmap_mode":             "incremental",   # "incremental" | "global"
    "colmap_feature_type":     "SIFT",           # "SIFT" | "ALIKED_N16ROT" | "ALIKED_N32"
    "colmap_matcher_type":     "sequential",     # "sequential" | "exhaustive"
    "colmap_overlap":          20,
    "colmap_camera_model":     "SIMPLE_RADIAL",
    "default_blur_threshold":  4,
    # --- Lichtfeld ---
    "lichtfeld_iterations":    20000,
    "lichtfeld_strategy":      "mrnf (Standard)",
    "lichtfeld_resize":        "auto",
    "lichtfeld_tile_mode":     2,
    "lichtfeld_mip":           False,
    "lichtfeld_max_splats":    1000000,      # défaut Lichtfeld
    "lichtfeld_gut":           False,         # 3DGUT (images distordues)
    "export_format":           "html",
    # --- Stockage ---
    "auto_cleanup":            False,
}


def get_config_path(bin_dir: str) -> str:
    """Retourne le chemin absolu vers config.json."""
    return os.path.join(bin_dir, "config.json")


def load_config(bin_dir: str) -> dict:
    """
    Charge la configuration depuis bin/config.json.
    Fusionne avec DEFAULT_CONFIG pour garantir la présence de toutes les clés
    même si l'utilisateur a une version ancienne du fichier.
    Retourne toujours un dict complet et valide.
    """
    config_path = get_config_path(bin_dir)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            # Fusion : les valeurs utilisateur écrasent les valeurs par défaut
            return {**DEFAULT_CONFIG, **user_config}
        except Exception as e:
            print(f"[Config] Erreur de lecture config.json : {e}. Utilisation des valeurs par défaut.")
    return DEFAULT_CONFIG.copy()


def save_config(bin_dir: str, new_config: dict) -> bool:
    """
    Sauvegarde un dict de configuration dans bin/config.json.
    Retourne True si succès, False sinon.
    """
    config_path = get_config_path(bin_dir)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] Erreur de sauvegarde config.json : {e}")
        return False
