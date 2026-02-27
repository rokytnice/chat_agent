#!/usr/bin/env python3
"""
Test RAG-Integration in bot.py
Testet die Funktionalität ohne den Bot-Service zu starten.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
log = logging.getLogger("rag_integration_test")

# Add project to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from lib.rag_integration import RAGIntegration

def test_rag_integration():
    """Teste RAG-Integration mit Beispiel-Daten."""
    log.info("=" * 80)
    log.info("🧪 RAG-Integrations-Test")
    log.info("=" * 80)

    # Initialisiere RAG (wie in bot.py)
    log.info("\n1️⃣ Initialisiere RAG...")
    try:
        rag = RAGIntegration()
        log.info("✅ RAG initialisiert erfolgreich")
    except Exception as e:
        log.error(f"❌ Fehler beim Initialisieren von RAG: {e}")
        return False

    # Test 1: Speichere Beispiel-Konversationen
    log.info("\n2️⃣ Teste Speichern von Interaktionen...")
    test_interactions = [
        {
            "user": "Wie funktioniert das RAG-System?",
            "assistant": "RAG ist Retrieval-Augmented Generation, das Prompts mit relevantem Kontext anreichert. Es speichert vergangene Konversationen in ChromaDB und abruft relevante Einträge für neue Anfragen.",
        },
        {
            "user": "Was ist der Vorteil von RAG?",
            "assistant": "RAG ermöglicht es dem Bot, sich kontinuierlich zu verbessern, indem er:\n1. Konversationshistorie speichert\n2. Relevant Information abruft\n3. Prompts damit anreichert\n4. Bessere, kontextbewusste Antworten gibt",
        },
        {
            "user": "Wie wird RAG im Bot verwendet?",
            "assistant": "Im bot.py wird RAG automatisch:\n1. Bei jedem API-Call den System-Prompt mit Kontext anreichern\n2. Nach der Antwort die Interaktion speichern\n3. Für zukünftige Requests darauf zurückgreifen",
        },
    ]

    stored_ids = []
    for i, interaction in enumerate(test_interactions, 1):
        try:
            doc_id = rag.store_interaction(
                user_message=interaction["user"],
                assistant_response=interaction["assistant"],
                chat_id="test_user_123",
                model="claude-opus"
            )
            log.info(f"   ✅ Interaktion {i} gespeichert (ID: {doc_id})")
            stored_ids.append(doc_id)
        except Exception as e:
            log.error(f"   ❌ Fehler beim Speichern von Interaktion {i}: {e}")
            return False

    # Test 2: Teste Prompt-Anreicherung (wie in bot.py)
    log.info("\n3️⃣ Teste Prompt-Anreicherung (wie bot.py)...")
    test_query = "Erkläre mir RAG"
    base_prompt = "Du bist ein hilfreicher KI-Assistent. Antworte auf Deutsch."

    try:
        enriched_prompt = rag.enrich_user_message(
            user_query=test_query,
            system_prompt=base_prompt,
            chat_id="test_user_123"
        )

        original_length = len(base_prompt)
        enriched_length = len(enriched_prompt)
        added_chars = enriched_length - original_length

        log.info(f"   ✅ Prompt angereichert")
        log.info(f"      Original Länge: {original_length} Zeichen")
        log.info(f"      Angereichert Länge: {enriched_length} Zeichen")
        log.info(f"      Kontext hinzugefügt: {added_chars} Zeichen")

        if enriched_length > original_length:
            log.info(f"      ✨ Kontext erfolgreich hinzugefügt!")
        else:
            log.warning(f"      ⚠️ Kein Kontext hinzugefügt (könnte normal sein bei wenigen Einträgen)")

    except Exception as e:
        log.error(f"   ❌ Fehler bei Prompt-Anreicherung: {e}")
        return False

    # Test 3: Teste Memory-Statistiken
    log.info("\n4️⃣ Teste Memory-Statistiken...")
    try:
        stats = rag.get_memory_stats()
        log.info(f"   ✅ Statistiken abrufen erfolgreich:")
        for key, value in stats.items():
            log.info(f"      {key}: {value}")
    except Exception as e:
        log.error(f"   ❌ Fehler beim Abrufen von Statistiken: {e}")
        return False

    # Test 4: Teste Context-Zusammenfassung
    log.info("\n5️⃣ Teste Context-Zusammenfassung...")
    try:
        summary = rag.get_context_summary("Was ist RAG?")
        log.info(f"   ✅ Context-Zusammenfassung:")
        for line in summary.split('\n'):
            if line.strip():
                log.info(f"      {line}")
    except Exception as e:
        log.error(f"   ❌ Fehler bei Context-Zusammenfassung: {e}")
        return False

    # Test 5: Teste Project Knowledge hinzufügen
    log.info("\n6️⃣ Teste Project Knowledge...")
    try:
        # Simuliere README
        readme_content = """
# Chat Agent - Telegram Bot mit Claude Code Integration

Der Chat Agent ist ein bidirektionaler Telegram-Bot, der Claude Code als Backend nutzt.

## Features
- Claude Code Integration via CLI
- Telegram Commands: /claude, /bash, /playwright
- 2FA Authentifizierung
- Persistente Sessions
- Text-to-Speech Vorlesen
- MCP Playwright Integration
- Agenten-System mit verschiedenen Rollen
- RAG Kontextmanagement für Long-Term Memory

## Verwendung
1. Bot starten: ./start.sh
2. /start - Hilfe anzeigen
3. Nachrichten direkt an Claude senden
"""

        doc_id = rag.context_manager.store_knowledge(
            text=readme_content,
            source="project_docs",
            doc_type="readme"
        )
        log.info(f"   ✅ Project Knowledge gespeichert (ID: {doc_id})")
    except Exception as e:
        log.error(f"   ❌ Fehler beim Speichern von Project Knowledge: {e}")
        return False

    # Test 6: Teste Preferences
    log.info("\n7️⃣ Teste User Preferences...")
    try:
        rag.set_user_preference("language", "de")
        rag.set_user_preference("communication_style", "friendly")
        log.info(f"   ✅ Preferences gespeichert")
    except Exception as e:
        log.error(f"   ❌ Fehler beim Speichern von Preferences: {e}")
        return False

    # Final Stats
    log.info("\n" + "=" * 80)
    log.info("📊 Finale Memory-Statistiken:")
    log.info("=" * 80)
    try:
        final_stats = rag.get_memory_stats()
        log.info(f"Konversationen: {final_stats.get('conversations', 0)}")
        log.info(f"Knowledge: {final_stats.get('knowledge', 0)}")
        log.info(f"Preferences: {final_stats.get('preferences', 0)}")
        total = sum([
            final_stats.get('conversations', 0),
            final_stats.get('knowledge', 0),
            final_stats.get('preferences', 0),
        ])
        log.info(f"Total Einträge: {total}")
    except Exception as e:
        log.error(f"Fehler beim Abrufen finaler Statistiken: {e}")

    log.info("\n" + "=" * 80)
    log.info("✅ ALLE TESTS BESTANDEN!")
    log.info("=" * 80)
    log.info("\n🚀 RAG-System ist einsatzbereit und wird automatisch:")
    log.info("   • Prompts mit Kontext anreichern")
    log.info("   • Interaktionen speichern")
    log.info("   • Präferenzen lernen")
    log.info("   • Kontextuelle Antworten verbessern")
    log.info("\n📁 Persistent Storage: data/chroma_db/")
    log.info("📖 Dokumentation: docs/RAG_SYSTEM.md")
    log.info("🧪 Beispiele: examples/rag_example.py")

    return True


if __name__ == "__main__":
    success = test_rag_integration()
    sys.exit(0 if success else 1)
