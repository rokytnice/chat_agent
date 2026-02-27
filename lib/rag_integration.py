#!/usr/bin/env python3
"""
Integration des ContextManagers in den Bot.
Automatische Anreicherung von Prompts mit RAG-Context.
"""

import logging
from typing import Optional, Dict, Any

from lib.context_manager import ContextManager

logger = logging.getLogger(__name__)


class RAGIntegration:
    """
    Vereinfachte Schnittstelle für RAG-Prompt-Anreicherung im Bot.
    """

    def __init__(self, context_manager: ContextManager = None):
        """
        Initialisiere RAG Integration.

        Args:
            context_manager: Existierende ContextManager-Instanz oder None (wird erstellt)
        """
        self.context_manager = context_manager or ContextManager()
        logger.info("✅ RAG Integration initialisiert")

    def enrich_user_message(
        self,
        user_query: str,
        system_prompt: str = "",
        chat_id: str = "",
    ) -> str:
        """
        Reichere eine User-Nachricht mit Kontext an.

        Args:
            user_query: Die ursprüngliche User-Nachricht
            system_prompt: Basis System-Prompt des Agenten
            chat_id: Chat-ID für Tracking

        Returns:
            Angereicherte Version des System-Prompts mit Kontext
        """
        try:
            enriched = self.context_manager.enrich_prompt(user_query, system_prompt)
            logger.info(f"✨ Prompt angereichert für Chat {chat_id} (Query: {user_query[:30]}...)")
            return enriched
        except Exception as e:
            logger.error(f"❌ Fehler bei Prompt-Anreicherung: {e}")
            return system_prompt  # Fallback zu Original

    def store_interaction(
        self,
        user_message: str,
        assistant_response: str,
        chat_id: str,
        model: str = "unknown",
        tokens_used: int = 0,
    ) -> bool:
        """
        Speichere eine Interaktion für zukünftiges Learning.

        Args:
            user_message: User-Nachricht
            assistant_response: Bot-Antwort
            chat_id: Chat-ID
            model: Verwendetes Modell
            tokens_used: Verwendete Token

        Returns:
            True wenn erfolgreich
        """
        try:
            metadata = {
                "chat_id": chat_id,
                "model": model,
                "tokens_used": tokens_used,
            }
            self.context_manager.store_conversation(
                user_message=user_message,
                assistant_response=assistant_response,
                metadata=metadata,
            )
            logger.debug(f"💾 Interaktion gespeichert für Chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Fehler beim Speichern der Interaktion: {e}")
            return False

    def add_project_knowledge(self, file_path: str, source: str = "project") -> bool:
        """
        Füge Projektdokumentation zur Knowledge Base hinzu.

        Args:
            file_path: Pfad zur Datei
            source: Quelle-Label (z.B. "README", "docs", "code")

        Returns:
            True wenn erfolgreich
        """
        try:
            from pathlib import Path

            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"⚠️ Datei nicht gefunden: {file_path}")
                return False

            content = file_path.read_text(encoding="utf-8")

            self.context_manager.store_knowledge(
                text=content,
                source=f"{source}:{file_path.name}",
                doc_type="document",
            )
            logger.info(f"📚 Dokumentation hinzugefügt: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"❌ Fehler beim Hinzufügen der Dokumentation: {e}")
            return False

    def set_user_preference(self, key: str, value: str) -> bool:
        """
        Setze eine Nutzer-Präferenz.

        Args:
            key: Präferenz-Schlüssel (z.B. "language", "communication_style")
            value: Präferenz-Wert (z.B. "de", "formal")

        Returns:
            True wenn erfolgreich
        """
        try:
            self.context_manager.store_user_preference(key, value)
            logger.info(f"⚙️ Präferenz gesetzt: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"❌ Fehler beim Setzen der Präferenz: {e}")
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """Gebe Memory-Statistiken."""
        try:
            return self.context_manager.get_stats()
        except Exception as e:
            logger.error(f"❌ Fehler beim Abrufen der Stats: {e}")
            return {}

    def get_context_summary(self, query: str) -> str:
        """
        Gebe eine Human-Readable Zusammenfassung des Context.

        Args:
            query: Die Query zum Retrieval

        Returns:
            Formatierte Context-Zusammenfassung
        """
        try:
            context = self.context_manager.retrieve_relevant_context(query)

            summary = f"📌 Context für Query: {query}\n"
            summary += "=" * 50 + "\n\n"

            if context.get("conversations"):
                summary += f"🗨️ {len(context['conversations'])} relevante Konversationen\n"
                for i, conv in enumerate(context["conversations"][:2], 1):
                    rel = f"{conv['relevance']:.0%}" if conv["relevance"] else "N/A"
                    summary += f"  {i}. [{rel}] {conv['text'][:80]}...\n"

            if context.get("knowledge"):
                summary += f"\n📚 {len(context['knowledge'])} Wissensdokumente\n"
                for i, know in enumerate(context["knowledge"][:2], 1):
                    rel = f"{know['relevance']:.0%}" if know["relevance"] else "N/A"
                    source = know["metadata"].get("source", "unknown")
                    summary += f"  {i}. [{rel}] {source}: {know['text'][:60]}...\n"

            if context.get("preferences"):
                summary += f"\n⚙️ {len(context['preferences'])} Nutzer-Präferenzen\n"
                for pref in context["preferences"]:
                    key = pref["metadata"].get("preference_key", "unknown")
                    summary += f"  • {key}: {pref['text']}\n"

            return summary

        except Exception as e:
            logger.error(f"❌ Fehler beim Generieren der Summary: {e}")
            return f"❌ Fehler: {str(e)}"
