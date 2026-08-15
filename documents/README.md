# xyberos-documents

**Filesystem + document loaders plugin — RFC-0019, M1.** Turns plain-text-only
ingestion into real document ingestion.

Loaders return text chunks consumed by
[`IngestingKnowledge.ingest`](https://docs.xyberos.com):

| Loader | Formats | Dependency |
| ------ | ------- | ---------- |
| `FileLoader` | `.md .txt .json .py .rst …` + directory walks | stdlib only |
| `HtmlLoader` | `.html .htm` (tag stripping) | stdlib only |
| `CsvLoader` | `.csv` | stdlib only |
| `PdfLoader` | `.pdf` | lazy `pypdf` / `PyPDF2` / `pymupdf` |
| `DocxLoader` | `.docx` | lazy `python-docx` |
| `XlsxLoader` | `.xlsx .xlsm` | lazy `openpyxl` |

The stdlib loaders keep the zero-dependency core sacred; the binary loaders
import their backend lazily and raise a clear `ProviderError` when missing.

## Install

```bash
pip install -e ./documents
# PDF/DOCX/XLSX backends (also available as the core extra):
pip install xyberos[documents]     # pypdf, python-docx, openpyxl
```

## Usage

Load a document as text chunks, then feed `IngestingKnowledge`:

```python
from xyberos import create_app
from xyberos.knowledge import IngestingKnowledge
from xyberos.llm import HashEmbedder
from xyberos.vector import SqliteVectorStore
from xyberos_documents import DocumentsPlugin, load_document

app = create_app(
    knowledge=IngestingKnowledge(SqliteVectorStore("learning.db"), embedder=HashEmbedder())
)
app.load_plugin(DocumentsPlugin())

app.tools.execute("ingest_document", None, path="report.pdf", chunk_size=512)
app.tools.execute("ingest_directory", None, path="docs/", extensions=[".pdf", ".docx"])
```

Each loader can also be used standalone (no app required):

```python
from xyberos_documents import PdfLoader, DocxLoader, HtmlLoader, load_document

for doc in PdfLoader().load("report.pdf"):
    print(doc.text)
```

## Tools registered

- `ingest_document(path, chunk_size=512, loader=None)` — auto-detect by
  extension (`loader` can force `text`/`html`/`pdf`/`docx`/`csv`/`xlsx`).
- `ingest_directory(path, extensions=None, chunk_size=512, recursive=True)` —
  walk a folder and route each file to the right loader.

Both require the registered `knowledge` provider to support `ingest()` (an
`IngestingKnowledge`); otherwise a clear `ProviderError` is raised.

## Examples

- `examples/ingest_documents.py` — generates a sample PDF + DOCX and ingests
  both, then queries the knowledge base.

## Tests

```bash
pip install pytest
pytest tests/
```

Optional-dep tests (`pdf`, `docx`, `xlsx`) skip cleanly when their library is
not installed — the same pattern as the core's `test_sentence_embedder.py`.

## Contract & ship location

- **Contract:** `Knowledge` (via `IngestingKnowledge`), plus `Tool` for the
  two ingest tools.
- **Ship:** `FileLoader` / `HtmlLoader` / `CsvLoader` are stdlib (would be
  Core); `PdfLoader` / `DocxLoader` / `XlsxLoader` map to the `[documents]`
  extra.
- **Dependencies:** `xyberos>=1.0`; optional `[documents]` for binary formats.
