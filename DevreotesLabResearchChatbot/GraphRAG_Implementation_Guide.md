# GraphRAG Implementation Guide
## Prof. Devreotes Lab — Step-by-Step Build

---

## PHASE 1: Graph Foundations (Neo4j Setup + Data Ingestion)

---

### Step 1 — Install All Dependencies

Create a project folder and install everything you'll need:

```bash
mkdir graphrag-devreotes && cd graphrag-devreotes
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install neo4j               # Neo4j Python driver
pip install pymupdf             # PDF text extraction (fitz)
pip install scispacy            # Biomedical NLP
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz
pip install langchain           # LLM orchestration
pip install langchain-community
pip install langchain-openai    # or langchain-anthropic for Claude
pip install sentence-transformers  # BioBERT/PubMedBERT embeddings
pip install requests            # For HGNC download
pip install python-dotenv       # Environment variables
```

Create a `.env` file in your project root:

```
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY
```

---

### Step 2 — Set Up Neo4j Aura

1. Go to https://console.neo4j.io
2. Click **"New Instance"** → choose **Free** tier
3. Download the credentials file — copy URI, username, and password into your `.env`
4. Wait ~2 minutes for the instance to start (status turns green)
5. Click **"Open"** → you'll see the Neo4j browser (useful for running Cypher manually)

Test your connection with Python:

```python
# test_connection.py
from dotenv import load_dotenv
import os
from neo4j import GraphDatabase

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)

with driver.session() as session:
    result = session.run("RETURN 'Connection successful!' AS msg")
    print(result.single()["msg"])

driver.close()
```

---

### Step 3 — Download the HGNC Gene Dataset

This is critical for resolving gene aliases (e.g., "FANCS" → "BRCA1" → same node).

```python
# download_hgnc.py
import requests
import json
import os

def download_hgnc():
    """Download HGNC complete dataset and build alias lookup table."""
    url = "https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json"
    print("Downloading HGNC dataset...")
    
    response = requests.get(url)
    data = response.json()
    
    # Build lookup: any alias/synonym -> canonical hgnc_id + official symbol
    alias_to_hgnc = {}
    
    for gene in data["response"]["docs"]:
        hgnc_id = gene.get("hgnc_id")
        symbol   = gene.get("symbol")
        
        if not hgnc_id or not symbol:
            continue
        
        entry = {"hgnc_id": hgnc_id, "official_symbol": symbol}
        
        # Map official symbol
        alias_to_hgnc[symbol.upper()] = entry
        
        # Map all aliases
        for field in ["alias_symbol", "prev_symbol"]:
            for alias in gene.get(field, []):
                alias_to_hgnc[alias.upper()] = entry
    
    # Save to disk
    with open("hgnc_lookup.json", "w") as f:
        json.dump(alias_to_hgnc, f)
    
    print(f"HGNC lookup built: {len(alias_to_hgnc)} aliases mapped")
    return alias_to_hgnc

if __name__ == "__main__":
    download_hgnc()
```

Run it: `python download_hgnc.py`

---

### Step 4 — Extract Text from PDFs

Place your PDF papers in a `papers/` folder, then run:

```python
# extract_pdfs.py
import fitz  # pymupdf
import os
import json

def extract_text_from_pdfs(papers_dir="papers", output_dir="extracted"):
    """Extract clean text from all PDFs in papers_dir."""
    os.makedirs(output_dir, exist_ok=True)
    results = []
    
    for filename in os.listdir(papers_dir):
        if not filename.endswith(".pdf"):
            continue
        
        pdf_path = os.path.join(papers_dir, filename)
        paper_id = filename.replace(".pdf", "")
        
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page in doc:
            full_text += page.get_text()
        
        doc.close()
        
        # Basic cleanup
        full_text = full_text.replace("\n\n\n", "\n\n").strip()
        
        # Try to extract title (usually first non-empty line)
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        title = lines[0] if lines else paper_id
        
        output = {
            "paper_id": paper_id,
            "title": title,
            "filename": filename,
            "text": full_text
        }
        
        # Save individual file
        out_path = os.path.join(output_dir, f"{paper_id}.json")
        with open(out_path, "w") as f:
            json.dump(output, f)
        
        results.append(output)
        print(f"Extracted: {filename} ({len(full_text)} chars)")
    
    print(f"\nTotal papers extracted: {len(results)}")
    return results

if __name__ == "__main__":
    extract_text_from_pdfs()
```

Run it: `python extract_pdfs.py`

---

### Step 5 — Create the Knowledge Graph Schema in Neo4j

Run these Cypher commands in the Neo4j browser (or via Python) to set up constraints and indexes:

```python
# setup_schema.py
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()
driver = GraphDatabase.driver(os.getenv("NEO4J_URI"),
                              auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

schema_queries = [
    # Uniqueness constraints (also auto-create indexes)
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.paper_id IS UNIQUE",
    "CREATE CONSTRAINT gene_hgnc IF NOT EXISTS FOR (g:Gene) REQUIRE g.hgnc_id IS UNIQUE",
    "CREATE CONSTRAINT author_name IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE",
    
    # Extra index for fast gene name lookup
    "CREATE INDEX gene_symbol IF NOT EXISTS FOR (g:Gene) ON (g.official_symbol)",
    
    # Vector index for semantic search (will be populated later)
    """CREATE VECTOR INDEX paper_embeddings IF NOT EXISTS
       FOR (p:Paper) ON (p.embedding)
       OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}""",
]

with driver.session() as session:
    for query in schema_queries:
        session.run(query)
        print(f"Ran: {query[:60]}...")

print("Schema created successfully!")
driver.close()
```

Run it: `python setup_schema.py`

---

### Step 6 — Extract Entities and Load the Knowledge Graph

This is the core ingestion pipeline: it reads extracted paper text, finds genes and authors using scispaCy, and loads everything into Neo4j.

```python
# ingest_papers.py
import spacy
import json
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Load scispaCy biomedical model
nlp = spacy.load("en_core_sci_lg")

# Load HGNC lookup
with open("hgnc_lookup.json") as f:
    hgnc_lookup = json.load(f)

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"),
                              auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))


def find_genes_in_text(text):
    """Use scispaCy to find gene mentions, then resolve via HGNC."""
    doc = nlp(text[:50000])  # Limit to first 50k chars for speed
    found_genes = {}
    
    for ent in doc.ents:
        token = ent.text.strip().upper()
        if token in hgnc_lookup:
            gene = hgnc_lookup[token]
            found_genes[gene["hgnc_id"]] = gene
    
    return list(found_genes.values())


def extract_authors_from_text(text):
    """Simple heuristic: look for 'Authors:' or use first paragraph."""
    authors = []
    lines = text.split("\n")[:30]  # Check first 30 lines
    
    for line in lines:
        if any(kw in line.lower() for kw in ["author", "correspondence"]):
            # Split on common author separators
            parts = line.replace(",", " ").replace(";", " ").replace("and", " ").split()
            # Filter: keep tokens that look like names (capitalized, 2+ chars)
            names = [p for p in parts if p[0].isupper() and len(p) > 2
                     and p.lower() not in ["author", "authors", "correspondence"]]
            if names:
                authors = names[:10]  # Cap at 10 authors
                break
    
    return authors


def load_paper(session, paper_data, genes, authors):
    """Load a single paper with its genes and authors into Neo4j."""
    
    # 1. Create the Paper node
    session.run("""
        MERGE (p:Paper {paper_id: $paper_id})
        SET p.title = $title,
            p.text  = $text,
            p.filename = $filename
    """, paper_id=paper_data["paper_id"],
         title=paper_data["title"],
         text=paper_data["text"][:5000],  # Store first 5000 chars
         filename=paper_data["filename"])
    
    # 2. Create Gene nodes and MENTIONS relationships
    for gene in genes:
        session.run("""
            MERGE (g:Gene {hgnc_id: $hgnc_id})
            SET g.official_symbol = $symbol
            WITH g
            MATCH (p:Paper {paper_id: $paper_id})
            MERGE (p)-[:MENTIONS]->(g)
        """, hgnc_id=gene["hgnc_id"],
             symbol=gene["official_symbol"],
             paper_id=paper_data["paper_id"])
    
    # 3. Create Author nodes and AUTHORED relationships
    for author_name in authors:
        session.run("""
            MERGE (a:Author {name: $name})
            WITH a
            MATCH (p:Paper {paper_id: $paper_id})
            MERGE (a)-[:AUTHORED]->(p)
        """, name=author_name,
             paper_id=paper_data["paper_id"])


def ingest_all_papers(extracted_dir="extracted"):
    papers = []
    
    with driver.session() as session:
        for filename in os.listdir(extracted_dir):
            if not filename.endswith(".json"):
                continue
            
            with open(os.path.join(extracted_dir, filename)) as f:
                paper_data = json.load(f)
            
            print(f"Processing: {paper_data['title'][:60]}...")
            
            genes   = find_genes_in_text(paper_data["text"])
            authors = extract_authors_from_text(paper_data["text"])
            
            load_paper(session, paper_data, genes, authors)
            
            print(f"  -> {len(genes)} genes, {len(authors)} authors loaded")
            papers.append(paper_data)
    
    print(f"\nIngestion complete: {len(papers)} papers loaded into Neo4j")
    return papers


if __name__ == "__main__":
    ingest_all_papers()
```

Run it: `python ingest_papers.py`

---

### Step 7 — Verify Your Graph with Cypher Queries

Open the Neo4j browser and try these queries to confirm everything loaded correctly:

```cypher
// How many nodes do we have?
MATCH (n) RETURN labels(n), count(n)

// List all papers
MATCH (p:Paper) RETURN p.title LIMIT 10

// Which genes appear in the most papers?
MATCH (p:Paper)-[:MENTIONS]->(g:Gene)
RETURN g.official_symbol, count(p) AS paper_count
ORDER BY paper_count DESC LIMIT 20

// Which authors collaborated most with Prof. Devreotes?
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
RETURN a.name, count(p) AS papers
ORDER BY papers DESC LIMIT 15

// Find all papers that mention PTEN
MATCH (p:Paper)-[:MENTIONS]->(g:Gene {official_symbol: "PTEN"})
RETURN p.title
```

---

## PHASE 2: Generative AI & GraphRAG

---

### Step 8 — Create Embeddings with PubMedBERT

Embeddings allow semantic/vector search — finding papers similar in *meaning*, not just keyword matches.

```python
# create_embeddings.py
from sentence_transformers import SentenceTransformer
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os, json

load_dotenv()

# PubMedBERT is trained on biomedical literature — much better than OpenAI for this domain
model = SentenceTransformer("pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb")

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"),
                              auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))


def chunk_text(text, chunk_size=500, overlap=100):
    """Split text into overlapping chunks for better retrieval."""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    
    return chunks


def embed_papers():
    with driver.session() as session:
        papers = session.run("MATCH (p:Paper) RETURN p.paper_id, p.title, p.text").data()
    
    print(f"Embedding {len(papers)} papers...")
    
    with driver.session() as session:
        for paper in papers:
            # Build text to embed: title + beginning of abstract
            embed_text = f"{paper['p.title']} {paper['p.text'][:1000]}"
            
            # Create embedding (768-dimensional vector)
            embedding = model.encode(embed_text).tolist()
            
            # Store embedding on the Paper node
            session.run("""
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.embedding = $embedding
            """, paper_id=paper["p.paper_id"], embedding=embedding)
            
            print(f"  Embedded: {paper['p.title'][:50]}...")
    
    print("All embeddings created!")


if __name__ == "__main__":
    embed_papers()
```

Run it: `python create_embeddings.py`

---

### Step 9 — Build the Retrieval Functions

Two retrieval methods that will work together in your GraphRAG system:

```python
# retrieval.py
from sentence_transformers import SentenceTransformer
from neo4j import GraphDatabase
from dotenv import load_dotenv
import json, os

load_dotenv()

model = SentenceTransformer("pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb")
driver = GraphDatabase.driver(os.getenv("NEO4J_URI"),
                              auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

# Load HGNC for query parsing
with open("hgnc_lookup.json") as f:
    hgnc_lookup = json.load(f)


def vector_search(question, top_k=5):
    """Semantic search: find papers most similar in meaning to the question."""
    query_embedding = model.encode(question).tolist()
    
    with driver.session() as session:
        results = session.run("""
            CALL db.index.vector.queryNodes('paper_embeddings', $top_k, $embedding)
            YIELD node AS p, score
            RETURN p.title AS title, p.text AS text, p.paper_id AS id, score
        """, top_k=top_k, embedding=query_embedding).data()
    
    return results


def graph_search_by_gene(gene_name):
    """Graph traversal: find all papers mentioning a specific gene."""
    gene_key = gene_name.upper()
    
    # Resolve alias to canonical symbol
    if gene_key in hgnc_lookup:
        hgnc_id = hgnc_lookup[gene_key]["hgnc_id"]
        
        with driver.session() as session:
            results = session.run("""
                MATCH (p:Paper)-[:MENTIONS]->(g:Gene {hgnc_id: $hgnc_id})
                OPTIONAL MATCH (a:Author)-[:AUTHORED]->(p)
                RETURN p.title AS title,
                       p.text  AS text,
                       g.official_symbol AS gene,
                       collect(a.name) AS authors
                ORDER BY p.title
            """, hgnc_id=hgnc_id).data()
        
        return results
    
    return []


def graph_search_by_author(author_name):
    """Graph traversal: find all papers by a specific author."""
    with driver.session() as session:
        results = session.run("""
            MATCH (a:Author)-[:AUTHORED]->(p:Paper)
            WHERE toLower(a.name) CONTAINS toLower($name)
            RETURN p.title AS title, p.text AS text, a.name AS author
            ORDER BY p.title
        """, name=author_name).data()
    
    return results


def graph_search_research_themes():
    """Find the most commonly mentioned genes across all papers — reveals research themes."""
    with driver.session() as session:
        results = session.run("""
            MATCH (p:Paper)-[:MENTIONS]->(g:Gene)
            RETURN g.official_symbol AS gene, count(p) AS paper_count
            ORDER BY paper_count DESC LIMIT 20
        """).data()
    
    return results


if __name__ == "__main__":
    # Quick test
    print("=== Vector Search Test ===")
    for r in vector_search("chemotaxis signal transduction")[:3]:
        print(f"  {r['title'][:60]} (score: {r['score']:.3f})")
    
    print("\n=== Gene Search Test ===")
    for r in graph_search_by_gene("PTEN")[:3]:
        print(f"  {r['title'][:60]}")
```

Run it: `python retrieval.py`

---

### Step 10 — Build the Query Router

This determines whether a question needs graph traversal (genes, authors) or semantic search (themes, methods):

```python
# router.py

def classify_query(question):
    """
    Classify the user's question to determine which retrieval strategy to use.
    Returns: 'gene', 'author', 'themes', or 'semantic'
    """
    q = question.lower()
    
    # Gene-related keywords
    gene_keywords = ["gene", "protein", "enzyme", "kinase", "receptor",
                     "pten", "ras", "pi3k", "gpcr", "camp"]
    
    # Author-related keywords
    author_keywords = ["author", "collaborat", "co-author", "who wrote",
                       "researcher", "scientist", "devreotes", "principal"]
    
    # Theme/overview keywords
    theme_keywords = ["theme", "topic", "focus", "overview", "main research",
                      "what does", "what has", "summary", "field"]
    
    if any(kw in q for kw in gene_keywords):
        return "gene"
    elif any(kw in q for kw in author_keywords):
        return "author"
    elif any(kw in q for kw in theme_keywords):
        return "themes"
    else:
        return "semantic"


def extract_gene_from_question(question, hgnc_lookup):
    """Try to extract a gene name from the question."""
    words = question.upper().split()
    for word in words:
        clean = word.strip("?,.'\"")
        if clean in hgnc_lookup:
            return clean
    return None


def extract_author_from_question(question):
    """Try to extract an author name from the question."""
    # Look for capitalized words after common author keywords
    import re
    patterns = [
        r"by ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"author ([A-Z][a-z]+)",
        r"([A-Z][a-z]+)'s papers",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return match.group(1)
    return None
```

---

## PHASE 3: Application Development — The Chatbot

---

### Step 11 — Build the Full GraphRAG Chatbot

This ties everything together into a working conversational AI:

```python
# chatbot.py
import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI      # swap for langchain_anthropic if using Claude
from langchain.schema import SystemMessage, HumanMessage

from retrieval import (vector_search, graph_search_by_gene,
                       graph_search_by_author, graph_search_research_themes)
from router import classify_query, extract_gene_from_question, extract_author_from_question

load_dotenv()

with open("hgnc_lookup.json") as f:
    hgnc_lookup = json.load(f)

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)
# If using Claude: 
# from langchain_anthropic import ChatAnthropic
# llm = ChatAnthropic(model="claude-opus-4-20250514", temperature=0)

SYSTEM_PROMPT = """You are a research assistant for Prof. Peter Devreotes' lab at Johns Hopkins University.
You answer questions based ONLY on the provided research papers from the lab's corpus.
Do not use outside knowledge. If the answer is not in the provided context, say so clearly.
Be precise, cite paper titles when relevant, and focus on scientific accuracy."""


def build_context(results, result_type="semantic"):
    """Format retrieval results into context for the LLM."""
    if not results:
        return "No relevant papers found in the corpus."
    
    context_parts = []
    
    if result_type == "themes":
        context_parts.append("Most frequently mentioned genes across the corpus:")
        for r in results[:15]:
            context_parts.append(f"  - {r['gene']}: mentioned in {r['paper_count']} papers")
    else:
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "Unknown")
            text  = r.get("text", "")[:800]
            context_parts.append(f"[Paper {i}] {title}\n{text}\n")
    
    return "\n\n".join(context_parts)


def answer_question(question, chat_history=None):
    """Main function: route the question, retrieve context, generate answer."""
    
    # 1. Classify the query
    query_type = classify_query(question)
    print(f"[Router] Query type: {query_type}")
    
    # 2. Retrieve relevant context
    if query_type == "gene":
        gene = extract_gene_from_question(question, hgnc_lookup)
        if gene:
            results = graph_search_by_gene(gene)
            context = build_context(results, "gene")
            print(f"[Graph] Gene search for '{gene}': {len(results)} papers found")
        else:
            # Fallback to semantic if gene not found
            results = vector_search(question)
            context = build_context(results, "semantic")
    
    elif query_type == "author":
        author = extract_author_from_question(question) or "Devreotes"
        results = graph_search_by_author(author)
        context = build_context(results, "author")
        print(f"[Graph] Author search for '{author}': {len(results)} papers found")
    
    elif query_type == "themes":
        results = graph_search_research_themes()
        context = build_context(results, "themes")
        print(f"[Graph] Research themes: {len(results)} top genes found")
    
    else:  # semantic
        results = vector_search(question)
        context = build_context(results, "semantic")
        print(f"[Vector] Semantic search: {len(results)} papers found")
    
    # 3. Build messages for LLM
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"""Context from Prof. Devreotes' papers:
---
{context}
---

Question: {question}

Answer based only on the context above:""")
    ]
    
    # 4. Generate answer
    response = llm.invoke(messages)
    return response.content


def run_chatbot():
    """Interactive command-line chatbot."""
    print("=" * 60)
    print("GraphRAG Chatbot — Prof. Devreotes' Lab")
    print("Type 'quit' to exit")
    print("=" * 60)
    
    while True:
        question = input("\nYou: ").strip()
        
        if question.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        
        if not question:
            continue
        
        print("\nSearching corpus...")
        answer = answer_question(question)
        print(f"\nAssistant: {answer}")


if __name__ == "__main__":
    run_chatbot()
```

Run it: `python chatbot.py`

---

### Step 12 — Add a Simple Web Interface (Optional but Impressive for Demo)

```python
# app.py  —  run with: pip install gradio && python app.py
import gradio as gr
from chatbot import answer_question

def chat(message, history):
    response = answer_question(message)
    return response

demo = gr.ChatInterface(
    fn=chat,
    title="Prof. Devreotes Lab Research Assistant",
    description="Ask questions about Prof. Devreotes' research papers on chemotaxis and cell signaling.",
    examples=[
        "What are the main research themes in this lab?",
        "Which papers discuss the PTEN gene?",
        "How has research on chemotaxis evolved over time?",
        "Which collaborators appear most often?",
        "What methods are commonly used across the papers?",
        "Which papers should a newcomer read first?",
    ],
    theme=gr.themes.Soft()
)

if __name__ == "__main__":
    demo.launch(share=True)  # share=True gives a public URL for the demo
```

---

### Step 13 — Test All Five Demo Questions

Run these before every meeting to validate the system:

```python
# test_demo_questions.py
from chatbot import answer_question

demo_questions = [
    "What are Prof. Devreotes' main research themes?",
    "Which papers discuss the PTEN gene and its role in cell signaling?",
    "How has the lab's work on chemotaxis changed over time?",
    "Which collaborators appear most often in the lab's publications?",
    "Which papers should a newcomer to this research area read first?",
]

print("=" * 70)
print("DEMO TEST RUN")
print("=" * 70)

for i, q in enumerate(demo_questions, 1):
    print(f"\n[Q{i}] {q}")
    print("-" * 50)
    answer = answer_question(q)
    print(answer[:500] + "..." if len(answer) > 500 else answer)
    print()
```

Run it: `python test_demo_questions.py`

---

## Quick Reference — File Structure

```
graphrag-devreotes/
├── .env                        # API keys and Neo4j credentials
├── papers/                     # Raw PDF files from Dropbox
├── extracted/                  # JSON files with extracted text
├── hgnc_lookup.json            # Gene alias → canonical ID lookup
│
├── download_hgnc.py            # Step 3 — HGNC data
├── extract_pdfs.py             # Step 4 — PDF extraction
├── setup_schema.py             # Step 5 — Neo4j schema
├── ingest_papers.py            # Step 6 — load graph
├── create_embeddings.py        # Step 8 — create vectors
├── retrieval.py                # Step 9 — search functions
├── router.py                   # Step 10 — query classifier
├── chatbot.py                  # Step 11 — main chatbot logic
├── app.py                      # Step 12 — Gradio web UI
└── test_demo_questions.py      # Step 13 — demo validation
```

## Run Order (First Time)

```bash
python download_hgnc.py        # One-time: download gene data
python extract_pdfs.py         # One-time: extract text from PDFs
python setup_schema.py         # One-time: create Neo4j schema
python ingest_papers.py        # One-time: load graph
python create_embeddings.py    # One-time: generate embeddings
python chatbot.py              # Run the chatbot!
# OR
python app.py                  # Run the web interface
```

---

*Guide prepared for Yeshiva University Graph Data Capstone — GraphRAG project, Spring 2026*
