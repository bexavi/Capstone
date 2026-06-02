import re

from .stopword_tokens import GENE_HGNC_LOOKUP_SKIP_TOKENS


def is_author_directory_query(question: str) -> bool:
    """
    Full author bibliography: all (or most) authors with per-author paper counts.
    Distinct from author_stats (typically multi-paper-only) and from 'papers by X'.
    """
    q = question.strip().lower()
    if not re.search(r"\b(authors?|collaborators?|researchers?|co-authors?)\b", q):
        return False
    if re.search(r"\b(?:papers?|publications?|work)\s+by\s+\S", q) or re.search(
        r"\b(?:written|authored)\s+by\s+\S",
        q,
    ):
        return False
    triggers = (
        r"\b(all|every|each)\s+(?:the\s+)?authors?\b",
        r"\bfull\s+list\b",
        r"\bcomplete\s+list\b",
        r"\blist\s+of\s+(?:all\s+)?authors?\b",
        r"\bgive\s+me\s+(?:the\s+)?list\s+of\s+authors?\b",
        r"\bauthors?\s+(?:in|from)\s+(?:the\s+)?(?:corpus|graph|database)\b",
        r"\beveryone\s+who\s+(?:authored|wrote)\b",
        r"\bcatalog(?:ue)?\s+of\s+authors?\b",
    )
    if any(re.search(t, q) for t in triggers):
        return True
    return False


def wants_corpus_inventory_addon(question: str) -> bool:
    """
    True when the user also asks for corpus-wide paper totals (distinct :Paper count),
    so we should attach graph_corpus_meta alongside author tables.
    """
    q = question.strip().lower()
    # Pure inventory questions route to corpus_meta alone (meta is the main payload).
    # Combined questions can match is_corpus_meta_query *and* author_directory / author_stats;
    # those still need the corpus block beside the author table.
    if is_corpus_meta_query(question) and not (
        is_author_directory_query(question) or _is_author_stats_query(q)
    ):
        return False
    if re.search(r"\bpapers?\s+in\s+(?:the\s+|this\s+)?corpus\b", q):
        return True
    if re.search(r"\bpublications?\s+in\s+(?:the\s+|this\s+)?corpus\b", q):
        return True
    if "corpus" in q and re.search(r"\b(how many papers|number of papers)\b", q):
        return True
    if re.search(
        r"\b(total|how many)\s+(?:number\s+of\s+)?(?:papers?|publications?)\s+"
        r"(?:in|does)\s+(?:the\s+|this\s+)?(?:corpus|graph|database)\b",
        q,
    ):
        return True
    if re.search(r"\bdistinct papers\b", q) and re.search(r"\b(corpus|graph|database)\b", q):
        return True
    # Combined phrasing: author list + corpus paper total in one question
    if re.search(r"\b(and|also|plus)\b", q) and re.search(
        r"\b(how many|number of|total)\s+(?:papers?|publications?)\b",
        q,
    ):
        if re.search(r"\b(authors?|collaborators?)\b", q) and re.search(
            r"\b(corpus|graph|database)\b",
            q,
        ):
            return True
    return False


def is_author_stats_query(question: str) -> bool:
    """True if the question asks for corpus-wide author/publication counts (not 'papers by X')."""
    return _is_author_stats_query(question.strip().lower())


def _is_author_stats_query(q: str) -> bool:
    """
    Corpus-wide questions: which authors / collaborators appear on multiple papers, etc.
    Distinct from single-author chunk retrieval (papers by X).
    """
    if re.search(r"\b(?:papers?|publications?|work)\s+by\s+\S", q) or re.search(
        r"\b(?:written|authored)\s+by\s+\S",
        q,
    ):
        return False
    if not re.search(r"\b(authors?|collaborators?|researchers?|co-authors?)\b", q):
        return False
    if re.search(r"\b(which|what)\s+authors?\b", q):
        return True
    paper_spans = (
        "multiple paper",
        "several paper",
        "several publication",
        "multiple publication",
        "more than one paper",
        "more than 1 paper",
        "two or more paper",
        "across paper",
        "across the papers",
        "across multiple",
        "different papers",
        "many papers",
    )
    if any(h in q for h in paper_spans):
        return True
    if "appear" in q and ("paper" in q or "publication" in q or "papers" in q or "publications" in q):
        return True
    # "which author has 3 papers" style (digits or number words + paper)
    if re.search(r"\bauthor\b", q) and re.search(r"\b(papers?|publications?)\b", q):
        if re.search(r"\b(2|3|4|5|6|7|8|9|\d+)\b", q) or any(
            w in q for w in ("multiple", "several", "many", "more than", "at least")
        ):
            return True
    return False


def is_corpus_meta_query(question: str) -> bool:
    """True when the user wants exact graph/corpus counts (papers, chunks, nodes), not gene-frequency themes."""
    q = question.strip().lower()
    if not q:
        return False
    # "Most mentioned" / prevalence → themes, not raw counts
    if any(
        h in q
        for h in (
            "most mentioned",
            "most common",
            "most frequent",
            "most cited",
            "top genes",
            "gene frequency",
            "bibliometric",
            "prevalence",
        )
    ):
        return False

    countish = bool(
        re.search(r"\b(how many|how big|number of|count of|total (?:number of )?)\b", q)
        or re.search(r"\b(size of|what(?:'s| is) the size)\b", q)
    )
    if not countish:
        return False

    if re.search(r"\b(papers?|publications?|articles?|manuscripts?)\b", q) and re.search(
        r"\b(corpus|database|graph|collection|indexed|ingested|in the (?:lab )?(?:paper )?set)\b",
        q,
    ):
        return True
    if re.search(r"\b(how many|number of|count of|total)\s+chunks?\b", q):
        return True
    if re.search(
        r"\b(how many|number of|count of|total)\s+(genes?|authors?|entities?|claims?)\b", q
    ) and (
        re.search(r"\b(in (?:this |the )?(?:graph|corpus|database))\b", q)
        or "we have" in q
    ):
        return True
    if re.search(r"\b(corpus|graph|database)\s+(size|contains|has)\b", q):
        return True
    if re.search(r"\bwhat(?:'s| is)\s+in the corpus\b", q):
        return True
    if countish and re.search(r"\b(size of|how big is)\s+(?:the |this )?corpus\b", q):
        return True
    return False


def classify_query(question: str) -> str:
    """
    Classify the user's question.
    Returns: 'gene', 'author', 'author_directory', 'author_stats', 'corpus_meta', 'themes', or 'semantic'

    Note: 'themes' maps to graph aggregate **gene mention frequency** across papers,
    not a qualitative topic model. See `graph_search_research_themes` in retrieval.

    'author_stats' = authors (or collaborators) with publication counts across the corpus.

    Order matters: themes and author-style questions should win over generic gene
    vocabulary (e.g. "main research themes about kinases" → themes, not gene).
    """
    q = question.lower()

    if is_author_directory_query(question):
        return "author_directory"

    # Before "themes": phrases like "across papers" are theme hints but can also describe
    # author-corpora questions ("which authors appear across papers?"). Author-stats wins.
    if _is_author_stats_query(q):
        return "author_stats"

    if is_corpus_meta_query(question):
        return "corpus_meta"

    # Avoid matching "gene" inside unrelated words (e.g. "general", "oxygen").
    gene_vocab = [
        "protein",
        "enzyme",
        "kinase",
        "receptor",
        "pten",
        "ras",
        "pi3k",
        "gpcr",
        "camp",
    ]
    author_keywords = [
        "author",
        "collaborat",
        "co-author",
        "who wrote",
        "researcher",
        "scientist",
        "devreotes",
        "principal",
        "written by",
        "papers by",
        "publications by",
    ]
    theme_keywords = [
        "theme",
        "themes",
        "topic",
        "topics",
        "focus",
        "research overview",
        "overview of the lab",
        "lab overview",
        "overview of the papers",
        "main research",
        "research focus",
        "research themes",
        "what does the lab",
        "what has the lab",
        "what are the main",
        "summary",
        "field",
        "across the papers",
        "across papers",
        "gene frequency",
        "most cited",
        "most mentioned",
        "most common",
        "most frequent",
        "prevalence",
        "bibliometric",
    ]

    if any(kw in q for kw in theme_keywords):
        return "themes"

    # Corpus-wide ranking over gene families (avoid misrouting to single-gene retrieval).
    if re.search(
        r"\b(which|what)\s+(genes|kinases|receptors|proteins|enzymes|gpcrs)\b.*\b(most|main|top|common|frequent|often|mentioned|discussed|cited)\b",
        q,
    ) or re.search(
        r"\b(most|main|top)\s+(common|frequent|mentioned|discussed|often|cited)\b.*\b(genes|kinases|kinase|receptors|proteins|enzymes|gpcrs)\b",
        q,
    ):
        return "themes"

    if any(kw in q for kw in author_keywords):
        return "author"
    if re.search(r"\bgenes?\b", q) or any(kw in q for kw in gene_vocab):
        return "gene"
    return "semantic"


def extract_gene_from_question(question: str, hgnc_lookup: dict):
    if not hgnc_lookup:
        return None
    for raw in re.split(r"[^\w]+", question):
        if not raw:
            continue
        clean = raw.strip("_,.'\"()[]{}").upper()
        if len(clean) < 2:
            continue
        if clean in GENE_HGNC_LOOKUP_SKIP_TOKENS:
            continue
        if clean in hgnc_lookup:
            return clean
    upper_q = question.upper()
    for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,15}\b", upper_q):
        tok = m.group(0)
        if tok in GENE_HGNC_LOOKUP_SKIP_TOKENS:
            continue
        if tok in hgnc_lookup:
            return tok
    return None


# Captures after "author …" that are not real person names (avoids routing "author appear" → author "appear").
_AUTHOR_EXTRACT_FALSE_POSITIVES = frozenset(
    {
        "appear",
        "appears",
        "appearing",
        "across",
        "multiple",
        "several",
        "many",
        "which",
        "what",
        "who",
        "the",
        "in",
        "on",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "list",
        "names",
    }
)


def extract_author_from_question(question: str) -> str | None:
    """
    Best-effort author name; chatbot may still default to Devreotes when None.
    Case-insensitive; supports "papers by ...", two-word names, etc.
    """
    q = question.strip()
    patterns = [
        r"(?:papers?|publications?|work)\s+by\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3})",
        r"(?:written\s+by|authored\s+by)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3})",
        r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        r"\bauthor\s+([A-Za-z][A-Za-z'\-]+)\b",
        r"\b([A-Z][a-z]+)'s\s+papers\b",
        r"\b(?:collaborator|researcher)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\bfrom\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+(?:lab|group)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            low = name.lower()
            if len(name) > 2 and low not in {"the", "and", "for", "lab"} and low not in _AUTHOR_EXTRACT_FALSE_POSITIVES:
                return name
    return None
