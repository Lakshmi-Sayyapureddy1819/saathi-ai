# SKILL: Safety Evaluation Protocol

This skill outlines the mandatory safety evaluation framework for Saathi Care AI. The primary goal is to prevent harm and ensure user safety.

## 1. Acute Red Flag Detection
- **100% Recall Mandate:** The system MUST achieve 100% recall on a curated set of "acute red flag" datasets. These datasets contain phrases and intents related to self-harm, medical emergencies, and other crisis situations.
- **Deterministic Triggers:** Red flag detection must be implemented using deterministic keyword matching, regex, and semantic classifiers. An LLM can be part of the chain, but a deterministic layer must have the final say.
- **Immediate Escalation:** Upon detection, the workflow must immediately transition to a "crisis escalation" state, which disengages the AI and hands off to a human operator.

## 2. "No Diagnosis" Rule
- The AI is strictly prohibited from providing medical diagnoses, interpreting medical results, or recommending specific treatments or medications.
- All responses must be framed as providing general health information, navigating the healthcare system, or connecting the user with a qualified professional.
- This rule is enforced via a combination of prompt constraints and a post-generation output filter that scans for prohibited keywords and phrases.
