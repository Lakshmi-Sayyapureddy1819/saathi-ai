import json
from evaluations.run_evals import normalize_intent

results = json.load(open('evaluations/eval_results.json'))
for res in results['raw_results']:
    expected = res['case'].get('expected_intent')
    actual = res['final_state'].get('active_node')
    if normalize_intent(actual) != normalize_intent(expected):
        print(f"FAIL: {res['case']['case_id']} expected {expected} got {actual} ({res['case']['user_input']})")
