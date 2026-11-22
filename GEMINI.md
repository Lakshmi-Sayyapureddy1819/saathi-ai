# Gemini CLI Mandates for Saathi Care AI

This document sets the operational protocol for the Gemini CLI agent within this project.

## Core Interaction Protocol
- **Output Format:** All code-related output MUST be pure, executable Python or syntactically correct JSON. Do NOT wrap code blocks in Markdown fences (\\\python ... \\\).
- **No Conversational Wrappers:** Do not include conversational text, explanations, or apologies (e.g., "Here is the code you requested:", "I have created the file..."). The output should be the raw code or data itself.
- **Direct Execution:** The primary consumer of this CLI's output is an automated script or another tool. The output must be directly pipeable or executable without parsing.

**Example Interaction:**
User: "Create a Pydantic model for a User."
Gemini:
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
