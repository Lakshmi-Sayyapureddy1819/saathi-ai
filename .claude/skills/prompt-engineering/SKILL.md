# SKILL: Prompt Engineering Lifecycle

This skill defines the process for creating, managing, and evaluating prompts to ensure quality, safety, and consistency.

## 1. Version Control
- All prompts are stored in the \/prompts\ directory.
- Each significant change to a prompt requires a new versioned file (e.g., \1/triage_intent.txt\, \2/triage_intent.txt\).
- The version used for any given LLM call must be logged in the corresponding Langfuse span.

## 2. Negative Constraints
- Prompts must include explicit "negative constraints" that clearly define what the model *should not* do.
- **Example:** "Do NOT provide a medical diagnosis. Do NOT interpret lab results. Instead, guide the user to book an appointment with a doctor."

## 3. Evaluation-Driven Development
- Any change to a prompt must be validated against a relevant evaluation dataset from \/evaluations/datasets\.
- The delta (improvement or regression) in key metrics (e.g., accuracy, safety recall, latency) must be recorded before the new prompt is deployed.
- A "no-regression" policy is enforced for safety-critical metrics.
