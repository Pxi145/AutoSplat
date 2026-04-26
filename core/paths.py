"""
core/paths.py
Résolution des chemins vers les binaires (COLMAP, Lichtfeld)
et gestion des dossiers de projets.

Responsabilités :
  - Localiser les exécutables tiers dans bin/
  - Créer / retrouver les dossiers de projets horodatés
  - Identifier le meilleur modèle sparse après le Mapper COLMAP
  - Parcourir récursivement un dossier pour trouver un .ply
"""
import os
from datetime import datetime


# ---------------------------------------------------------------------------
# Résolution des binaires
# ---------------------------------------------------------------------------

def find_colmap_exe(bin_dir: str) -> str | None:
    """
    Cherche colmap.exe dans les emplacements standards sous bin/.
    Retourne le chemin absolu ou None si introuvable.
    """
    colmap_dir = os.path.join(bin_dir, "colmap-x64-windows-cuda")
    candidates = [
        os.path.join(colmap_dir, "colmap.exe"),
        os.path.join(colmap_dir, "bin", "colmap.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def find_lichtfeld_exe(bin_dir: str) -> str | None:
    """
    Cherche l'exécutable Lichtfeld Studio dans bin/LichtFeld-Studio/bin/.
    Teste plusieurs noms de fichiers et le sous-dossier Release/.
    Retourne le chemin absolu ou None si introuvable.
    """
    base_lf = os.path.join(bin_dir, "LichtFeld-Studio", "bin")
    exe_names = [
        "Lichtfeld Studio.exe",
        "Lichtfeld.exe",
        "LichtFeld-Studio.exe",
    ]
    for name in exe_names:
        # Cherche d'abord directement dans bin/
        direct = os.path.join(base_lf, name)
        if os.path.exists(direct):
            return direct
        # Puis dans bin/Release/
        release = os.path.join(base_lf, "Release", name)
        if os.path.exists(release):
            return release
    return None


# ---------------------------------------------------------------------------
# Gestion des projets
# ---------------------------------------------------------------------------

def resolve_project_path(
    projects_dir: str,
    existing_path: str | None = None,
    project_name: str | None = None,
) -> str:
    """
    Retourne le chemin du projet actif.

    - Si `existing_path` pointe vers un dossier existant, le réutilise
      (cas où l'utilisateur a ouvert le dossier avant de lancer).
    - Sinon, génère un nouveau dossier horodaté :
        - Avec nom personnalisé : cool_banana_20260405_023009
        - Sans nom : Projet_20260405_023009
    """
    if existing_path and os.path.exists(existing_path):
        return existing_path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if project_name:
        # Nettoyer le nom (espaces → underscores, pas de caractères spéciaux)
        safe_name = "".join(
            c if c.isalnum() or c in ("_", "-") else "_"
            for c in project_name.strip()
        ).strip("_")
        if safe_name:
            return os.path.join(projects_dir, f"{safe_name}_{timestamp}")
    return os.path.join(projects_dir, f"Projet_{timestamp}")


# ---------------------------------------------------------------------------
# Helpers post-COLMAP
# ---------------------------------------------------------------------------

def find_best_sparse_model(sparse_path: str) -> str | None:
    """
    Analyse les sous-dossiers générés par COLMAP Mapper (nommés "0", "1", etc.)
    et retourne le nom du dossier dont la somme de taille des fichiers .bin
    est la plus grande — donc le modèle 3D le plus complet.

    Retourne None si aucun sous-dossier valide n'est trouvé.
    """
    best_folder, max_size = None, -1
    bin_files = ("points3D.bin", "images.bin", "cameras.bin")

    try:
        for folder_name in os.listdir(sparse_path):
            folder_path = os.path.join(sparse_path, folder_name)
            if not os.path.isdir(folder_path):
                continue

            total_size = sum(
                os.path.getsize(os.path.join(folder_path, f))
                for f in bin_files
                if os.path.exists(os.path.join(folder_path, f))
            )
            if total_size > max_size:
                max_size = total_size
                best_folder = folder_name

    except Exception as e:
        print(f"[Paths] Erreur lors de l'analyse de sparse_raw : {e}")

    return best_folder


def find_ply_in_dir(root_dir: str) -> str | None:
    """
    Parcourt récursivement root_dir et retourne le chemin du dernier
    fichier .ply trouvé (tri naturel par os.walk → itération la plus haute).
    Retourne None si aucun .ply n'est trouvé.
    """
    final_ply = None
    for root, _, files in os.walk(root_dir):
        for filename in files:
            if filename.lower().endswith(".ply"):
                final_ply = os.path.join(root, filename)
    return final_ply
