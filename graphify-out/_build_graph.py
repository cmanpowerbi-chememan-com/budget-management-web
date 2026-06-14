"""One-shot controlled graphify build. Code->AST (free, local), docs+paper->Azure OpenAI
(Chememan tenant, eastus2). Reads Azure creds from .env. Temp script — safe to delete after."""
import json, sys, os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.llm import extract_corpus_parallel, generate_community_labels
from graphify.build import build
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html, _git_head

ROOT = Path(".")
OUT = Path("graphify-out")
OUT.mkdir(exist_ok=True)

BACKEND = "azure"  # Azure OpenAI in Chememan tenant (eastus2)

print(">> detect")
det = detect(ROOT)
files = det.get("files", {})
code_paths, sem_paths = [], []
for f in files.get("code", []):
    p = Path(f)
    code_paths.extend(collect_files(p) if p.is_dir() else [p])
for cat in ("document", "paper"):
    for f in files.get(cat, []):
        sem_paths.append(Path(f))
print(f"   code={len(code_paths)} semantic={len(sem_paths)}")

extractions = []

print(">> AST extract (free, local)")
if code_paths:
    ast = extract(code_paths, cache_root=ROOT, parallel=False)  # parallel=False: Windows pool crash fix
    print(f"   AST: {len(ast['nodes'])} nodes / {len(ast['edges'])} edges", flush=True)
    extractions.append(ast)

print(f">> {BACKEND} semantic extract (docs+paper) · {len(sem_paths)} files, chunk=8", flush=True)
if sem_paths:
    _done = {"n": 0}
    def _progress(*a, **k):
        _done["n"] += 1
        print(f"   chunk {_done['n']} done", flush=True)
    sem = extract_corpus_parallel(
        sem_paths, backend=BACKEND, root=ROOT,
        chunk_size=8, max_concurrency=4, token_budget=60000,
        on_chunk_done=_progress,
    )
    print(f"   SEM: {len(sem.get('nodes', []))} nodes / {len(sem.get('edges', []))} edges", flush=True)
    extractions.append(sem)

print(">> build graph")
G = build(extractions, root=str(ROOT))
print(f"   G: {G.number_of_nodes()} nodes / {G.number_of_edges()} edges")

print(">> cluster")
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
print(f"   {len(communities)} communities, {len(gods)} god-nodes")

print(f">> label communities ({BACKEND})")
labels, _ = generate_community_labels(G, communities, backend=BACKEND, model=None, gods=gods)
questions = suggest_questions(G, communities, labels)

# sum token cost from extractions (gemini may report; AST is 0)
tok = {"input": sum(e.get("input_tokens", 0) for e in extractions),
       "output": sum(e.get("output_tokens", 0) for e in extractions)}

print(">> report + write")
report = generate(G, communities, cohesion, labels, gods, surprises,
                  det, tok, str(ROOT), suggested_questions=questions,
                  built_at_commit=_git_head())
(OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
to_json(G, communities, str(OUT / "graph.json"))
(OUT / ".graphify_labels.json").write_text(
    json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False), encoding="utf-8")
try:
    to_html(G, communities, str(OUT / "graph.html"), community_labels=labels or None)
    print("   graph.html written")
except Exception as e:
    print(f"   graph.html skipped: {e}")

print(f"\nDONE. {G.number_of_nodes()} nodes, {len(communities)} communities.")
print("Outputs: graphify-out/graph.json, GRAPH_REPORT.md, graph.html")
