# RAG-Kontextmanagement-System

Dokumentation für das **Retrieval-Augmented Generation (RAG) Kontextmanagement** basierend auf **ChromaDB**.

## 📖 Übersicht

Das RAG-System ermöglicht es dem Chat-Agent, sein Wissen kontinuierlich zu erweitern und Prompts mit relevantem Kontext anzureichern. Es besteht aus drei Hauptkomponenten:

### 1. **ContextManager** (`lib/context_manager.py`)
- Verwaltet ChromaDB für persistente Embeddings
- Speichert drei Arten von Memory:
  - **Conversations**: Vergangene Nutzer-Assistent-Interaktionen
  - **Knowledge**: Projektdokumentation, Code, externe Ressourcen
  - **User Preferences**: Nutzer-Einstellungen und -Präferenzen
- Retrieval von relevantem Context basierend auf Semantic Search

### 2. **RAGIntegration** (`lib/rag_integration.py`)
- Vereinfachte Schnittstelle für den Bot
- Automatische Prompt-Anreicherung
- Speicherung von Interaktionen
- Präferenz-Management

### 3. **ChromaDB**
- **Vector Database** für Embeddings
- **Cosine Similarity** zur Relevanz-Berechnung
- Persistenter Storage in `data/chroma_db/`

---

## 🚀 Quick Start

### Installation

```bash
pip install chromadb
```

### Basis-Verwendung

```python
from lib.rag_integration import RAGIntegration

# Initialisiere RAG
rag = RAGIntegration()

# Speichere eine Konversation
rag.store_interaction(
    user_message="Was ist ein Agent?",
    assistant_response="Ein Agent ist ein autonomes System...",
    chat_id="user_123"
)

# Enriche einen Prompt mit Kontext
enriched = rag.enrich_user_message(
    user_query="Erzähl mir vom Agent",
    system_prompt="Du bist ein hilfreich Assistent"
)

# Nutze den angereicherten Prompt beim API-Call
response = anthropic.messages.create(
    system=enriched,
    messages=[{"role": "user", "content": user_query}]
)
```

---

## 💾 Speichern von Memory

### Konversationen speichern

```python
rag.store_interaction(
    user_message="Wie konfiguriere ich den Bot?",
    assistant_response="Der Bot wird konfiguriert in bot.py...",
    chat_id="user_123",
    model="claude-opus",
    tokens_used=256
)
```

**Metadata:**
- `chat_id`: Eindeutige Chat-Identifikation
- `model`: Verwendetes LLM-Modell
- `tokens_used`: Verbrauchte Token
- `timestamp`: Automatisch

### Projektdokumentation hinzufügen

```python
# Füge README zur Knowledge Base hinzu
rag.add_project_knowledge(
    file_path="README.md",
    source="project_docs"
)

# Oder: Direkt Text speichern
cm = rag.context_manager
cm.store_knowledge(
    text="André Rochlitz entwickelt AI-Systeme...",
    source="personal_docs",
    doc_type="profile"
)
```

### Nutzer-Präferenzen

```python
rag.set_user_preference("language", "de")
rag.set_user_preference("communication_style", "formal")
```

---

## 🔍 Retrieval & Kontext-Anreicherung

### Context Retrieval

```python
context = cm.retrieve_relevant_context(
    query="Wie funktioniert RAG?",
    n_results=3,
    include_conversations=True,
    include_knowledge=True,
    include_preferences=True
)

# context["conversations"]: Liste relevanter Konversationen
# context["knowledge"]: Relevante Dokumente
# context["preferences"]: User-Präferenzen
```

**Struktur eines Ergebnisses:**
```json
{
  "id": "doc_id_123",
  "text": "Die gefundene Information...",
  "relevance": 0.87,  // 0-1, basierend auf Cosine Similarity
  "metadata": {
    "source": "project_docs",
    "timestamp": "2025-02-26T12:30:00"
  }
}
```

### Automatische Prompt-Anreicherung

```python
# Der Bot nutzt dies automatisch:
enriched_prompt = rag.enrich_user_message(
    user_query="Erkläre mir RAG",
    system_prompt="Du bist ein AI-Experte"
)

# enriched_prompt enthält jetzt:
# - Original System-Prompt
# - Relevante vergangene Konversationen (Relevance > 0.3)
# - Relevante Dokumentation
# - Nutzer-Präferenzen
```

---

## 📊 Memory Management

### Statistiken abrufen

```python
stats = rag.get_memory_stats()

# {
#   "conversations": 42,
#   "knowledge": 8,
#   "preferences": 5,
#   "db_path": "/path/to/chroma_db"
# }
```

### Context-Zusammenfassung

```python
summary = rag.get_context_summary("Wie funktioniert mein Bot?")
print(summary)

# Ausgabe:
# 📌 Context für Query: Wie funktioniert mein Bot?
# ==================================================
#
# 🗨️ 2 relevante Konversationen
#   1. [95%] Gestern fragtest du etwa "Was ist ein Agent?"...
#   2. [78%] Letzte Woche fragtest du...
#
# 📚 3 Wissensdokumente
#   1. [92%] project_docs: Der Bot ist ein Telegram-Interface für...
#   2. [81%] README: Installation und Konfiguration...
#
# ⚙️ 2 Nutzer-Präferenzen
#   • language: de
#   • communication_style: casual
```

### Export der Memory

```python
from pathlib import Path

# Exportiere alle Memory als JSON
rag.context_manager.export_memory(
    Path("exports/memory_backup.json")
)
```

---

## 🔧 Integration in den Bot

### Im Telegram-Bot-Code

```python
from lib.rag_integration import RAGIntegration

class TelegramBot:
    def __init__(self):
        self.rag = RAGIntegration()

    async def handle_message(self, update, context):
        user_message = update.message.text
        chat_id = str(update.message.chat_id)

        # Enriche den System-Prompt mit Kontext
        agent = get_active_agent()
        enriched_system_prompt = self.rag.enrich_user_message(
            user_query=user_message,
            system_prompt=agent.get("system_prompt", ""),
            chat_id=chat_id
        )

        # Rufe Claude API auf mit angereichertem Prompt
        response = anthropic_client.messages.create(
            system=enriched_system_prompt,
            messages=[...],
            model=agent["model"]
        )

        # Speichere die Interaktion für zukünftiges Learning
        self.rag.store_interaction(
            user_message=user_message,
            assistant_response=response.content[0].text,
            chat_id=chat_id,
            model=agent["model"],
            tokens_used=response.usage.output_tokens
        )

        # Sende Antwort
        await update.message.reply_text(response.content[0].text)
```

---

## 🏗️ Datenbankstruktur

ChromaDB speichert die Embeddings in: **`data/chroma_db/`**

### Collections

```
chroma_db/
├── conversations.parquet      # Nutzer-Assistent Interaktionen
├── knowledge.parquet          # Projektdokumentation
├── user_preferences.parquet   # Nutzer-Einstellungen
└── [Metadaten und Indizes]
```

### Vektoren-Embedding

ChromaDB nutzt standardmäßig **all-MiniLM-L6-v2** (384-dimensionale Vektoren) für Embeddings. Dies können Sie konfigurieren, falls benötigt.

---

## 📈 Performance & Best Practices

### Retrieval-Schwellenwerte

- **Relevance > 0.7**: Sehr relevant → Immer einbeziehen
- **Relevance 0.3-0.7**: Bedingt relevant → In Anreicherung einbeziehen
- **Relevance < 0.3**: Nicht relevant → Ausschließen

### Speicher-Grenzen

```python
# Große Dokumente splitting
large_doc = "..."  # 10.000+ Zeichen

# Teile in Chunks auf (z.B. pro Absatz)
chunks = [...]
for chunk in chunks:
    cm.store_knowledge(chunk, source="docs")
```

### Cleanup alter Memory

```python
# Entferne Konversationen älter als 30 Tage
cm.clear_old_conversations(days=30)
```

---

## 🧪 Beispiele

Siehe `examples/rag_example.py` für vollständige Beispiele:

```bash
python examples/rag_example.py
```

---

## ⚙️ Konfiguration

Änderere ChromaDB-Verhalten in `lib/context_manager.py`:

```python
settings = Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory=str(db_path),
    anonymized_telemetry=False,
)
```

---

## 🐛 Debugging

### Logging aktivieren

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### ChromaDB Stats prüfen

```python
stats = rag.get_memory_stats()
print(f"Total Memory Entries: {sum(stats.values())}")
```

---

## 📚 Referenzen

- **ChromaDB Docs**: https://docs.trychroma.com
- **RAG Pattern**: https://research.ibm.com/blog/retrieval-augmented-generation
- **Semantic Search**: https://en.wikipedia.org/wiki/Semantic_search

---

**Version**: 1.0
**Letzte Aktualisierung**: 2025-02-26
**Autor**: Claude Code (André Rochlitz)
