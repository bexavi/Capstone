3. Neo4j GDS (optional, paper-shaped)
Idea: Context-graph uses FastRP / similarity / Louvain on decisions. For Devreotes, map analogs:

Similar papers: graph of papers (co-authorship, shared genes, citation if you add it) → node similarity or embedding on Paper if you add paper-level vectors.
“Neighborhood expansion”: you may already have something like RAG_GRAPH_EXPAND in retrieval — that’s the same spirit as GDS: vector hit → expand along graph.
Only invest in full GDS if you have a clear query (“clusters of topics in the corpus”) and AuraDS / GDS available; otherwise Cypher + vector index + your existing expand often suffices.

4. “Decision trace” for science (audit / UI)
Idea: Record which tools ran, which chunk IDs were used, and query_type — analogous to a decision trace.

Persist in Hub SQLite (you already use it in Nuxt) or logs: route, chunk_ids, abstain, model_id.
Helps capstone demos and debugging without changing Neo4j schema.
5. LLM stack alignment
Devreotes uses LangChain ChatOpenAI in chatbot.py; context-graph uses Anthropic Agent SDK. For a merge you don’t have to pick one immediately:

Minimal change: Keep LangChain for the final answer; add OpenAI/Anthropic tool calling (or AI SDK in TypeScript only at the API boundary) for the agent loop that calls your Python tools.
Unify later: One stack (e.g. AI SDK or raw OpenAI tools) reduces dependency sprawl.