"""
Redrob Hackathon — Sandbox Demo
================================
Run locally:  streamlit run app.py
Deploy to:    HuggingFace Spaces (Streamlit SDK) or Streamlit Cloud

This sandbox accepts a small JSON/JSONL sample of candidates and
produces a ranked CSV — satisfying the sandbox requirement in Section 10.5.
"""

import csv
import io
import json
import sys
import os

# Add parent dir to path so we can import rank.py
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

# Import our scoring functions
from rank import (
    score_candidate,
    build_reasoning,
    load_candidates,
    TODAY,
)

st.set_page_config(
    page_title="Redrob Candidate Ranker",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Redrob Intelligent Candidate Ranker")
st.caption("Hackathon sandbox — upload a candidate sample to see rankings")

st.markdown("""
**How to use:**
1. Upload a `.json` (array) or `.jsonl` (one candidate per line) file with candidate profiles
2. Click **Rank Candidates**
3. Download the resulting ranked CSV
""")

# ── File upload ──────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload candidates (JSON array or JSONL, max 500 candidates for demo)",
    type=["json", "jsonl"],
)

if uploaded:
    raw = uploaded.read().decode("utf-8")

    # Parse candidates
    candidates = []
    try:
        # Try JSON array first
        data = json.loads(raw)
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            candidates = [data]
    except json.JSONDecodeError:
        # Fall back to JSONL
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    candidates.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not candidates:
        st.error("Could not parse any candidates from the uploaded file.")
        st.stop()

    # Cap at 500 for sandbox
    if len(candidates) > 500:
        st.warning(f"Loaded {len(candidates)} candidates — capping at 500 for sandbox.")
        candidates = candidates[:500]
    else:
        st.success(f"Loaded {len(candidates)} candidates.")

    if st.button("🚀 Rank Candidates", type="primary"):
        with st.spinner("Scoring candidates..."):
            scored = []
            honeypots = []

            for c in candidates:
                total_score, components = score_candidate(c)
                if components.get("honeypot"):
                    honeypots.append((c["candidate_id"], components["honeypot"]))
                    continue
                scored.append({
                    "candidate_id": c["candidate_id"],
                    "score": total_score,
                    "components": components,
                    "_candidate": c,
                })

            # Sort
            scored.sort(key=lambda x: (-x["score"], x["candidate_id"]))
            top_n = scored[:100]

            # Build output
            output_rows = []
            for rank, entry in enumerate(top_n, start=1):
                reasoning = build_reasoning(entry["_candidate"], entry["components"], rank)
                output_rows.append({
                    "candidate_id": entry["candidate_id"],
                    "rank": rank,
                    "score": round(entry["score"], 6),
                    "reasoning": reasoning,
                    "title": entry["_candidate"]["profile"]["current_title"],
                    "yoe": entry["_candidate"]["profile"]["years_of_experience"],
                    "country": entry["_candidate"]["profile"]["country"],
                    "title_score": entry["components"]["title"],
                    "career_score": round(entry["components"]["career"], 1),
                    "skills_score": round(entry["components"]["skills"], 1),
                    "beh_mult": entry["components"]["behavioral_mult"],
                })

        # ── Results ──────────────────────────────────────────────────────────
        col1, col2, col3 = st.columns(3)
        col1.metric("Total candidates", len(candidates))
        col2.metric("Ranked (top 100)", min(len(top_n), 100))
        col3.metric("Honeypots detected", len(honeypots))

        st.subheader("Top 20 Results")
        import pandas as pd

        display_cols = ["rank", "candidate_id", "title", "yoe", "country",
                        "score", "title_score", "career_score", "skills_score", "beh_mult", "reasoning"]
        df = pd.DataFrame(output_rows)[display_cols]
        st.dataframe(df.head(20), use_container_width=True)

        if honeypots:
            with st.expander(f"⚠️ {len(honeypots)} honeypot(s) detected and excluded"):
                for cid, reason in honeypots:
                    st.write(f"• `{cid}`: {reason}")

        # ── CSV Download ─────────────────────────────────────────────────────
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for row in output_rows:
            writer.writerow([row["candidate_id"], row["rank"], row["score"], row["reasoning"]])

        st.download_button(
            label="⬇️ Download submission.csv",
            data=csv_buf.getvalue(),
            file_name="submission.csv",
            mime="text/csv",
        )

        # ── Score breakdown chart ─────────────────────────────────────────────
        st.subheader("Score component breakdown (top 20)")
        chart_data = pd.DataFrame([
            {
                "candidate": f"#{r['rank']} {r['candidate_id']}",
                "title": r["title_score"],
                "career": r["career_score"],
                "skills": r["skills_score"],
            }
            for r in output_rows[:20]
        ]).set_index("candidate")
        st.bar_chart(chart_data)

else:
    st.info("Upload a candidate file above to get started. You can use `sample_candidates.json` from the hackathon bundle.")

    with st.expander("📖 About the ranking algorithm"):
        st.markdown("""
**Scoring components (total: 0–100+ pts):**

| Component | Weight | What it measures |
|---|---|---|
| Title/Role fit | 0–30 pts | Is this person actually a ML/AI/NLP engineer? Anti-keyword-stuffer guard |
| Career history | 0–30 pts | Did they ship production ML at product companies (not just consulting)? |
| Skills (trusted) | 0–25 pts | Core skills weighted by endorsements + usage duration |
| Experience years | 0–10 pts | JD target 5–9 yrs; peak weight at 6–8 yrs |
| Location fit | 0–5 pts | India (Pune/Noida preferred), willing to relocate |

**Behavioral multiplier (×0.3 to ×1.2):**
- `last_active_date` — inactive >6 months → ×0.3
- `notice_period_days` — >90 days → ×0.55 penalty
- `recruiter_response_rate` — <0.2 → ×0.7 penalty
- `open_to_work_flag` — ×1.05 bonus

**Honeypot detection:**
- Expert skills with 0 months usage
- Career history months << stated years of experience
- 8+ simultaneous expert skills
- All behavioral signals maxed simultaneously
        """)
