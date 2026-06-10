import json

with open('data/sample_candidates.json', 'r') as f:
    candidates = json.load(f)

with open('data/sample.jsonl', 'w') as f:
    for cand in candidates:
        f.write(json.dumps(cand) + '\n')

print("Converted sample_candidates.json to sample.jsonl")