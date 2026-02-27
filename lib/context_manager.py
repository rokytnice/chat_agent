#!/usr/bin/env python3
"""
Kontextmanagement-System mit ChromaDB für RAG (Retrieval-Augmented Generation).
Speichert semantische Memory und reichert Prompts mit relevantem Kontext an.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import chromadb

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Verwaltet semantische Memory mit ChromaDB für RAG.
    - Speichert Konversationen und Erkenntnisse
    - Retrieval bei neuen Anfragen
    - Automatische Prompt-Anreicherung
    """

    def __init__(self, db_path: Path = None):
        """
        Initialisiere ChromaDB mit persistent storage.

        Args:
            db_path: Pfad zum Persistieren der Embeddings (default: ./data/chroma)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "chroma_db"

        db_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB mit persistentem Storage (neue API)
        self.client = chromadb.PersistentClient(path=str(db_path))
        self.db_path = db_path

        # Verschiedene Collections für verschiedene Memory-Typen
        self._init_collections()

        logger.info(f"✅ ContextManager initialisiert mit DB-Pfad: {db_path}")

    def _init_collections(self):
        """Initialisiere ChromaDB Collections für verschiedene Memory-Typen."""
        try:
            self.conversations = self.client.get_or_create_collection(
                name="conversations"
            )
            self.knowledge = self.client.get_or_create_collection(
                name="knowledge"
            )
            self.user_preferences = self.client.get_or_create_collection(
                name="user_preferences"
            )
            logger.info("✅ Collections initialisiert")
        except Exception as e:
            logger.error(f"❌ Fehler beim Erstellen der Collections: {e}")
            raise

    def store_conversation(
        self,
        user_message: str,
        assistant_response: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Speichere eine Konversation in ChromaDB.

        Args:
            user_message: Nachricht des Nutzers
            assistant_response: Antwort des Assistenten
            metadata: Zusätzliche Metadaten (z.B. tokens, model)
            doc_id: Eindeutige ID (wird generiert wenn nicht gegeben)

        Returns:
            Dokumenten-ID
        """
        import uuid

        if doc_id is None:
            doc_id = str(uuid.uuid4())

        # Kombiniere Nachricht und Antwort für besseres Embedding
        combined_text = f"Q: {user_message}\nA: {assistant_response}"

        # Standardmetadaten
        meta = {
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message[:500],  # Kurz truncieren
            "response_length": len(assistant_response),
            "type": "conversation",
        }

        if metadata:
            meta.update(metadata)

        try:
            self.conversations.add(
                documents=[combined_text],
                metadatas=[meta],
                ids=[doc_id]
            )
            logger.debug(f"💾 Konversation gespeichert (ID: {doc_id})")
            return doc_id
        except Exception as e:
            logger.error(f"❌ Fehler beim Speichern der Konversation: {e}")
            raise

    def store_knowledge(
        self,
        text: str,
        source: str,
        doc_type: str = "document",
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Speichere Wissen/Kontext in der Knowledge Base.

        Args:
            text: Der Wissenstext
            source: Quelle des Wissens (z.B. "project_docs", "codebase")
            doc_type: Typ des Dokuments
            doc_id: Eindeutige ID

        Returns:
            Dokumenten-ID
        """
        import uuid

        if doc_id is None:
            doc_id = f"{source}_{uuid.uuid4()}"

        meta = {
            "source": source,
            "type": doc_type,
            "timestamp": datetime.now().isoformat(),
            "text_length": len(text),
        }

        try:
            self.knowledge.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id]
            )
            logger.debug(f"📚 Wissen gespeichert von '{source}'")
            return doc_id
        except Exception as e:
            logger.error(f"❌ Fehler beim Speichern des Wissens: {e}")
            raise

    def store_user_preference(self, key: str, value: str, doc_id: Optional[str] = None) -> str:
        """
        Speichere Nutzer-Präferenzen (z.B. Sprache, Stil).

        Args:
            key: Präferenz-Schlüssel
            value: Präferenz-Wert
            doc_id: Eindeutige ID

        Returns:
            Dokumenten-ID
        """
        if doc_id is None:
            doc_id = f"pref_{key}"

        meta = {
            "preference_key": key,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self.user_preferences.add(
                documents=[value],
                metadatas=[meta],
                ids=[doc_id]
            )
            logger.debug(f"⚙️ Präferenz gespeichert: {key}")
            return doc_id
        except Exception as e:
            logger.error(f"❌ Fehler beim Speichern der Präferenz: {e}")
            raise

    def retrieve_relevant_context(
        self,
        query: str,
        n_results: int = 3,
        include_conversations: bool = True,
        include_knowledge: bool = True,
        include_preferences: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve relevanten Kontext für eine Anfrage (RAG).

        Args:
            query: Die Anfrage/Question
            n_results: Anzahl der Top-Ergebnisse pro Collection
            include_conversations: Konversationen einbeziehen?
            include_knowledge: Knowledge Base einbeziehen?
            include_preferences: Präferenzen einbeziehen?

        Returns:
            Dictionary mit retrieced Context aus verschiedenen Collections
        """
        context = {}

        try:
            if include_conversations:
                conv_results = self.conversations.query(
                    query_texts=[query],
                    n_results=n_results
                )
                context["conversations"] = self._format_results(conv_results)

            if include_knowledge:
                know_results = self.knowledge.query(
                    query_texts=[query],
                    n_results=n_results
                )
                context["knowledge"] = self._format_results(know_results)

            if include_preferences:
                pref_results = self.user_preferences.query(
                    query_texts=[query],
                    n_results=min(n_results, 2)  # Weniger Präferenzen
                )
                context["preferences"] = self._format_results(pref_results)

            logger.debug(f"🔍 Context retrieced für Query: {query[:50]}...")
            return context
        except Exception as e:
            logger.error(f"❌ Fehler beim Retrieval: {e}")
            return {}

    @staticmethod
    def _format_results(chroma_results: Dict) -> List[Dict[str, Any]]:
        """Formatiere ChromaDB-Ergebnisse in lesbare Form."""
        if not chroma_results or not chroma_results.get("documents"):
            return []

        formatted = []
        for i, doc in enumerate(chroma_results["documents"][0]):
            dist = chroma_results.get("distances", [[]])[0][i] if "distances" in chroma_results else None
            meta = chroma_results.get("metadatas", [[]])[0][i] if "metadatas" in chroma_results else {}
            doc_id = chroma_results.get("ids", [[]])[0][i] if "ids" in chroma_results else None

            formatted.append({
                "id": doc_id,
                "text": doc,
                "relevance": 1 - dist if dist is not None else None,  # Cosine distance → relevance
                "metadata": meta,
            })

        return formatted

    def enrich_prompt(self, user_query: str, system_prompt: str = "") -> str:
        """
        Reichere einen Prompt mit relevantem Kontext an (RAG).

        Args:
            user_query: Die ursprüngliche User-Query
            system_prompt: Basis System-Prompt

        Returns:
            Angereichter Prompt mit Kontext
        """
        context = self.retrieve_relevant_context(user_query)

        enriched = system_prompt if system_prompt else ""

        # Füge relevante Konversationen hinzu
        if context.get("conversations"):
            enriched += "\n\n## Relevante vergangene Konversationen:\n"
            for conv in context["conversations"][:2]:  # Top 2
                if conv["relevance"] and conv["relevance"] > 0.3:
                    enriched += f"- {conv['text'][:200]}...\n"

        # Füge Wissen hinzu
        if context.get("knowledge"):
            enriched += "\n\n## Relevantes Wissen:\n"
            for know in context["knowledge"][:2]:
                if know["relevance"] and know["relevance"] > 0.3:
                    source = know["metadata"].get("source", "unknown")
                    enriched += f"- [{source}] {know['text'][:150]}...\n"

        # Füge Präferenzen hinzu
        if context.get("preferences"):
            enriched += "\n\n## Nutzer-Präferenzen:\n"
            for pref in context["preferences"]:
                key = pref["metadata"].get("preference_key", "unknown")
                enriched += f"- {key}: {pref['text']}\n"

        logger.debug(f"✨ Prompt angereichert ({len(enriched)} Zeichen)")
        return enriched

    def get_stats(self) -> Dict[str, Any]:
        """Gebe Statistiken über gespeicherte Memory."""
        try:
            return {
                "conversations": self.conversations.count(),
                "knowledge": self.knowledge.count(),
                "preferences": self.user_preferences.count(),
                "db_path": str(self.db_path),
            }
        except Exception as e:
            logger.error(f"❌ Fehler beim Abrufen der Stats: {e}")
            return {}

    def clear_old_conversations(self, days: int = 30):
        """Entferne alte Konversationen (älter als N Tage)."""
        try:
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            # ChromaDB hat begrenzte Filtering-Features
            # Für echtes Cleanup müsste man direkt mit der DB arbeiten
            logger.info(f"🗑️ Alte Konversationen würden vor {cutoff_date} gelöscht")
        except Exception as e:
            logger.error(f"❌ Fehler beim Löschen alter Konversationen: {e}")

    def export_memory(self, filepath: Path) -> bool:
        """Exportiere alle Memory als JSON."""
        try:
            export_data = {
                "conversations": self.conversations.get()["documents"] if self.conversations.count() > 0 else [],
                "knowledge": self.knowledge.get()["documents"] if self.knowledge.count() > 0 else [],
                "preferences": self.user_preferences.get()["documents"] if self.user_preferences.count() > 0 else [],
                "timestamp": datetime.now().isoformat(),
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f"📤 Memory exportiert nach {filepath}")
            return True
        except Exception as e:
            logger.error(f"❌ Fehler beim Export: {e}")
            return False
