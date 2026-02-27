#!/usr/bin/env python3
"""
Beispiel: Verwendung des RAG-Kontextmanagement-Systems.
"""

import sys
from pathlib import Path

# Füge parent zum path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.context_manager import ContextManager
from lib.rag_integration import RAGIntegration


def example_basic_usage():
    """Beispiel: Basis-Verwendung des ContextManagers."""
    print("=" * 60)
    print("1️⃣ BEISPIEL: Basis-Verwendung")
    print("=" * 60)

    # Initialisiere ContextManager
    cm = ContextManager()

    # Speichere eine Konversation
    conv_id = cm.store_conversation(
        user_message="Wie funktioniert RAG?",
        assistant_response="RAG (Retrieval-Augmented Generation) ermöglicht es, externe Knowledge-Bases zu durchsuchen...",
        metadata={"model": "claude-opus", "tokens_used": 150}
    )
    print(f"✅ Konversation gespeichert (ID: {conv_id})")

    # Speichere Wissen
    knowledge_id = cm.store_knowledge(
        text="André Rochlitz ist ein Software-Entwickler und AI-Enthusiast.",
        source="personal_docs",
        doc_type="profile"
    )
    print(f"✅ Wissen gespeichert (ID: {knowledge_id})")

    # Speichere Nutzer-Präferenz
    pref_id = cm.store_user_preference("language", "de")
    print(f"✅ Präferenz gespeichert (ID: {pref_id})")

    # Retrieve relevanten Context
    context = cm.retrieve_relevant_context("Wer ist André?", n_results=2)
    print(f"\n🔍 Retrieved Context:")
    for ctx_type, results in context.items():
        if results:
            print(f"  {ctx_type}: {len(results)} Ergebnisse")
            for r in results:
                print(f"    - Relevance: {r['relevance']:.0%} | {r['text'][:60]}...")

    # Zeige Stats
    stats = cm.get_stats()
    print(f"\n📊 Memory Stats:")
    print(f"  Conversations: {stats['conversations']}")
    print(f"  Knowledge: {stats['knowledge']}")
    print(f"  Preferences: {stats['preferences']}")


def example_rag_enrichment():
    """Beispiel: Prompt-Anreicherung mit RAG."""
    print("\n" + "=" * 60)
    print("2️⃣ BEISPIEL: RAG-Prompt-Anreicherung")
    print("=" * 60)

    rag = RAGIntegration()

    # Füge Projekt-Dokumentation hinzu
    rag.add_project_knowledge(
        "/home/aroc/projects/chat_agent/README.md",
        source="project_docs"
    )

    # Setze User-Präferenz
    rag.set_user_preference("communication_style", "casual")
    rag.set_user_preference("language", "de")

    # Enriche Prompt basierend auf Query
    system_prompt = "Du bist ein hilfreicher Software-Entwicklungs-Assistent."
    user_query = "Was ist der Chat Agent?"

    enriched_prompt = rag.enrich_user_message(
        user_query=user_query,
        system_prompt=system_prompt,
        chat_id="example_123"
    )

    print(f"\n📝 Original System-Prompt ({len(system_prompt)} chars):")
    print(f"  {system_prompt}")

    print(f"\n✨ Angereichert ({len(enriched_prompt)} chars):")
    print(enriched_prompt[:500] + "..." if len(enriched_prompt) > 500 else enriched_prompt)


def example_conversation_tracking():
    """Beispiel: Automatisches Tracking von Konversationen."""
    print("\n" + "=" * 60)
    print("3️⃣ BEISPIEL: Konversations-Tracking")
    print("=" * 60)

    rag = RAGIntegration()

    # Simuliere mehrere Konversationen
    conversations = [
        ("Was ist RAG?", "RAG ist Retrieval-Augmented Generation, ein Technik zum..."),
        ("Wie speichere ich Daten?", "Mit ChromaDB kannst du Embeddings speichern..."),
        ("Was ist ein Agent?", "Ein Agent ist ein autonomes System das..."),
    ]

    for user_msg, bot_response in conversations:
        success = rag.store_interaction(
            user_message=user_msg,
            assistant_response=bot_response,
            chat_id="example_chat_001",
            model="claude-opus",
            tokens_used=100
        )
        if success:
            print(f"✅ Gespeichert: {user_msg[:30]}...")

    # Abrufe Context für ähnliche Frage
    print(f"\n🔍 Context für neue Query 'Wie funktioniert speichern?':")
    summary = rag.get_context_summary("Wie funktioniert speichern?")
    print(summary)


def example_memory_stats():
    """Beispiel: Memory-Statistiken."""
    print("\n" + "=" * 60)
    print("4️⃣ BEISPIEL: Memory-Statistiken")
    print("=" * 60)

    rag = RAGIntegration()
    stats = rag.get_memory_stats()

    print(f"\n📊 Aktuelle Memory-Statistiken:")
    print(f"  Database Path: {stats.get('db_path', 'N/A')}")
    print(f"  Gespeicherte Konversationen: {stats.get('conversations', 0)}")
    print(f"  Wissensdokumente: {stats.get('knowledge', 0)}")
    print(f"  Nutzer-Präferenzen: {stats.get('preferences', 0)}")

    total = sum([stats.get(k, 0) for k in ['conversations', 'knowledge', 'preferences']])
    print(f"\n  📊 Total gespeicherte Einträge: {total}")


if __name__ == "__main__":
    print("\n🚀 RAG-Kontextmanagement-System Beispiele\n")

    # Führe alle Beispiele aus
    example_basic_usage()
    example_rag_enrichment()
    example_conversation_tracking()
    example_memory_stats()

    print("\n" + "=" * 60)
    print("✅ Alle Beispiele abgeschlossen!")
    print("=" * 60 + "\n")
