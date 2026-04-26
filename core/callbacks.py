"""
core/callbacks.py
Pont de communication entre le Core (logique métier) et l'UI (CustomTkinter).

Principe :
    Le core ne connaît aucun widget. Il reçoit un objet PipelineCallbacks
    à l'exécution et appelle ses méthodes pour communiquer avec l'UI.
    Cela permet de tester le core sans aucune interface graphique.

Usage (dans l'UI) :
    cb = PipelineCallbacks(
        log=self._log,
        set_step=self._set_step,
        update_monitor=self._update_monitor,
        is_cancelled=lambda: self.is_cancelled,
        set_current_process=lambda p: setattr(self, '_proc', p),
    )
    pipeline.run(..., cb=cb)
"""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class PipelineCallbacks:
    """
    Interface de communication injectée dans les runners et l'orchestrateur.
    Tous les champs sont des callables — pas de widgets ici.
    """

    log: Callable[[str, bool], None]
    """
    log(text: str, replace: bool = False)
    Affiche un message dans la console UI.
    Si replace=True, écrase la dernière ligne (animation barre de progression).
    """

    set_step: Callable[[int, str], None]
    """
    set_step(index: int, status: str)
    Met à jour le statut d'une étape dans le panneau d'avancement.
    status ∈ {"doing", "done"}
    """

    update_monitor: Callable[[Any], None]
    """
    update_monitor(ctk_image | None)
    Met à jour l'aperçu temps réel pendant l'extraction.
    Passer None pour masquer le moniteur après l'extraction.
    """

    is_cancelled: Callable[[], bool]
    """
    is_cancelled() → bool
    Retourne True si l'utilisateur a cliqué sur "Annuler".
    Vérifié à chaque étape critique du pipeline.
    """

    set_current_process: Callable[[Any], None]
    """
    set_current_process(proc: subprocess.Popen | None)
    Enregistre le sous-processus actif afin de pouvoir le tuer (kill)
    si l'utilisateur annule pendant COLMAP ou Lichtfeld.
    Passer None après la fin du processus.
    """

    log_to_file: Callable[[str], None] | None = None
    """
    log_to_file(text: str)
    Écrit une ligne dans le fichier de log complet du projet (pipeline.log).
    Utilisé pour capturer les sorties brutes des sous-processus (debug).
    None si le logging fichier n'est pas activé.
    """
