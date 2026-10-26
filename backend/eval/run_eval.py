"""Measure how well /ask works on a fixed set of 15 questions.

Two modes:
  python eval/run_eval.py --mode retrieval
      No API key needed. Checks only the search step: is the right document
      ranked first, and are off-topic questions refused?
  python eval/run_eval.py --mode full
      Calls the real LLM (set ANTHROPIC_API_KEY or OPENAI_API_KEY). Checks the
      answer contains the expected fact, cites the right document, and that
      off-topic questions get "I don't have information on this."

Runs in-process on a throwaway SQLite database, so it never touches real data.
Results are printed and saved to eval/results.json.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'eval.db')}"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import rag  # noqa: E402


def load_questions() -> list[dict]:
    return json.loads((EVAL_DIR / "questions.json").read_text())


def setup_client() -> tuple[TestClient, dict, int]:
    client = TestClient(app)
    client.__enter__()  # runs the startup hook, which creates the tables
    token = client.post("/auth/signup", json={"team_name": "Eval", "email": "eval@example.com",
                                              "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    for path in sorted((EVAL_DIR.parent / "app" / "demo_docs").iterdir()):
        response = client.post("/documents", files={"file": (path.name, path.read_bytes(), "text/plain")}, headers=headers)
        response.raise_for_status()
    team_id = client.get("/auth/me", headers=headers).json()["team_id"]
    return client, headers, team_id


def grade_retrieval(item: dict, team_id: int) -> dict:
    with SessionLocal() as db:
        hits = rag.search(db, team_id, item["question"])
    top = hits[0] if hits else None
    refused = top is None or top.similarity < settings.min_similarity
    if item["source"] is None:
        passed = refused
    else:
        passed = not refused and top.filename == item["source"]
    return {"got_source": None if refused else top.filename,
            "top_similarity": round(top.similarity, 3) if top else None, "passed": passed}


def grade_full(item: dict, client: TestClient, headers: dict) -> dict:
    body = client.post("/ask", json={"question": item["question"]}, headers=headers).json()
    sources = [s["filename"] for s in body.get("sources", [])]
    if item["source"] is None:
        passed = body.get("refused", False)
    else:
        answer = body.get("answer", "").lower()
        passed = (not body.get("refused", True)
                  and item["source"] in sources
                  and all(k.lower() in answer for k in item["keywords"]))
    return {"answer": body.get("answer"), "sources": sources, "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    parser.add_argument("--min-score", type=float, default=0.0, help="exit with code 1 if the pass rate is lower")
    args = parser.parse_args()

    client, headers, team_id = setup_client()
    results = []
    for item in load_questions():
        graded = grade_retrieval(item, team_id) if args.mode == "retrieval" else grade_full(item, client, headers)
        results.append({"question": item["question"], "expected_source": item["source"], **graded})
        mark = "PASS" if graded["passed"] else "FAIL"
        print(f"[{mark}] {item['question']}")
        if not graded["passed"]:
            print(f"        expected {item['source']}, got {json.dumps({k: v for k, v in graded.items() if k != 'passed'})}")

    passed = sum(r["passed"] for r in results)
    answerable = [r for r in results if r["expected_source"]]
    refusals = [r for r in results if not r["expected_source"]]
    summary = {
        "mode": args.mode,
        "embedding_provider": settings.embedding_provider,
        "min_similarity": settings.min_similarity,
        "passed": passed,
        "total": len(results),
        "answerable_passed": f"{sum(r['passed'] for r in answerable)}/{len(answerable)}",
        "refusals_passed": f"{sum(r['passed'] for r in refusals)}/{len(refusals)}",
    }
    print(f"\n{passed}/{len(results)} passed  (answerable {summary['answerable_passed']}, "
          f"off-topic refused {summary['refusals_passed']})")
    (EVAL_DIR / "results.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    client.__exit__(None, None, None)
    return 0 if passed / len(results) >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
