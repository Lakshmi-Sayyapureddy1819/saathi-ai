"""
This module contains tools for explaining lab reports.
"""
from app.workflow.model_client import ModelClient

class ReportTools:
    def __init__(self):
        self.model_client = ModelClient(quality_optimized=True)

    def explain_report(self, report_text: str, trace_id: str) -> str:
        """
        Generates a simplified explanation of a lab report using an LLM.
        """
        prompt = f"""
        You are an expert medical assistant. Your task is to explain the following lab report in simple, easy-to-understand terms.
        Do not provide a diagnosis or medical advice.
        Focus on explaining what each test measures and what the normal ranges are.

        Here is the lab report:
        {report_text}
        """
        
        try:
            res = self.model_client.generate(prompt, trace_id)
            return res.text
        except Exception as e:
            return f"An error occurred while explaining the report: {e}"

report_tools = ReportTools()
