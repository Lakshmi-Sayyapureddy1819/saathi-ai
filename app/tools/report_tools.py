"""
This module contains tools for explaining lab reports.
"""
from app.observability.redact import redact
from app.observability.tracer import span
from app.workflow.gateway import ADKModelGateway
from google.adk.models import LlmRequest
from google.genai import types


class ReportTools:
    def __init__(self):
        self.gateway = ADKModelGateway(node="quality_optimized")
        # Keep self.model_client pointing to gateway for backwards compatibility
        self.model_client = self.gateway

    def explain_report(self, report_text: str, trace_id: str) -> str:
        """
        Generates a simplified explanation of a lab report using an LLM through ADKModelGateway.
        """
        prompt = f"""
        You are an expert medical assistant. Your task is to explain the following lab report in simple, easy-to-understand terms.
        Do not provide a diagnosis or medical advice.
        Focus on explaining what each test measures and what the normal ranges are.

        Here is the lab report:
        {report_text}
        """
        
        with span("tool:explain_report", trace_id, kind="tool", input=redact(report_text)) as s:
            try:
                req = LlmRequest(
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    model="gateway",
                )
                resp = self.gateway.generate_request(req, trace_id=trace_id)
                text = "".join(p.text for p in resp.content.parts if p.text) if resp.content and resp.content.parts else ""
                s.set_output(redact(text))
                return text
            except Exception as e:
                s.set(error=str(e))
                return f"An error occurred while explaining the report: {e}"


report_tools = ReportTools()
