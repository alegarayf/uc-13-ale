"""
Shared base class, data structures, and helpers for all Phase 3 workstream agents.

All Phase 3 agents extend WorkstreamAgent. The base class provides:
  - ToolResult, Flag, Citation dataclasses
  - _tool_call(): logs every retrieval step to the reasoning trace
  - _call_llm(): calls the Databricks MLflow LLM endpoint
  - _parse_json_response(): strips markdown fences, parses JSON
  - _add_flag(), _add_citation(), _add_gap(): accumulate findings
  - _reset_state(): clears state at the start of each run()
  - predict(): required by mlflow.pyfunc.PythonModel — delegates to run()
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import mlflow.pyfunc
import mlflow.deployments


@dataclass
class ToolResult:
    tool_name: str
    input_summary: str    # human-readable description of what was queried
    output_summary: str   # human-readable description of what was found
    data: Any             # the actual data (chunks list, dict, etc.)
    confidence: str       # "high" | "medium" | "low"
    source_docs: list     # filenames that contributed data


@dataclass
class Flag:
    metric: str
    value: str        # as extracted from documents — always a string, never recomputed
    threshold: str    # the threshold from the spec (e.g. "<~40%")
    severity: str     # "Red" | "Yellow" | "Green"
    note: str         # Austin's note or spec context — presented neutrally
    source_doc: str   # filename this value came from
    confidence: str   # "high" | "medium" | "low"


@dataclass
class Citation:
    claim: str
    document: str
    location: str     # page number, tab name, section title, or cell reference
    confidence: str   # "high" | "medium" | "low"
    raw_text: str     # ≤30-word supporting quote from the source


class WorkstreamAgent(mlflow.pyfunc.PythonModel):
    """Base class for all Phase 3 workstream agents.

    Subclasses implement:
      - agent_name (class attribute, str)
      - run(company_name: str, spark, llm_endpoint: str) -> dict
    """

    agent_name: str = "base"

    def __init__(self):
        self._trace: list[dict] = []
        self._flags: list[Flag] = []
        self._citations: list[Citation] = []
        self._data_room_gaps: list[str] = []
        self._llm_client = None
        self._company_name: Optional[str] = None  # set at the top of each run()

    def _get_llm_client(self):
        if self._llm_client is None:
            self._llm_client = mlflow.deployments.get_deploy_client("databricks")
        return self._llm_client

    def _call_llm(self, system_prompt: str, user_prompt: str, endpoint: str) -> str:
        """Call the Databricks MLflow LLM endpoint. Returns response text."""
        client = self._get_llm_client()
        response = client.predict(
            endpoint=endpoint,
            inputs={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "max_tokens": 4000,
                "temperature": 0.0,  # deterministic extraction
            },
        )
        return response["choices"][0]["message"]["content"]

    def _parse_json_response(self, raw: str) -> dict:
        """Strip markdown fences and parse JSON. Raises ValueError on failure."""
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\nRaw response:\n{raw[:500]}")

    def _tool_call(
        self,
        tool_name: str,
        input_summary: str,
        data: Any,
        output_summary: str,
        confidence: str,
        source_docs: list,
    ) -> ToolResult:
        """Log a tool call to the reasoning trace and return a ToolResult.

        Every retrieval or SQL read must go through this method so the trace
        is complete. The trace is printed live and stored in the output.
        """
        step = len(self._trace) + 1
        self._trace.append({
            "step":       step,
            "tool":       tool_name,
            "input":      input_summary,
            "output":     output_summary,
            "confidence": confidence,
            "sources":    source_docs,
        })
        print(f"  Step {step} [{tool_name}]: {output_summary}  (confidence={confidence})")
        return ToolResult(
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            data=data,
            confidence=confidence,
            source_docs=source_docs,
        )

    def _add_flag(self, metric, value, threshold, severity, note, source_doc, confidence):
        """Add a flag and log it to the trace so every flag evaluation is visible."""
        flag = Flag(
            metric=metric, value=value, threshold=threshold,
            severity=severity, note=note, source_doc=source_doc, confidence=confidence,
        )
        self._flags.append(flag)
        step = len(self._trace) + 1
        self._trace.append({
            "step":       step,
            "tool":       "apply_threshold_flag",
            "input":      f"metric={metric}, extracted_value={value}, threshold={threshold}",
            "output":     f"{severity} flag — {note}",
            "confidence": confidence,
            "sources":    [source_doc] if source_doc else [],
        })
        print(f"  Step {step} [apply_threshold_flag]: [{severity}] {metric}={value} vs {threshold}")

    def _add_citation(self, claim, document, location, confidence, raw_text):
        self._citations.append(Citation(
            claim=claim, document=document, location=location,
            confidence=confidence, raw_text=raw_text,
        ))

    def _add_gap(self, gap: str):
        self._data_room_gaps.append(gap)
        print(f"  [data_room_gap] {gap}")

    def _reset_state(self):
        self._trace = []
        self._flags = []
        self._citations = []
        self._data_room_gaps = []

    def _flags_as_dicts(self) -> list[dict]:
        return [
            {"metric": f.metric, "value": f.value, "threshold": f.threshold,
             "severity": f.severity, "note": f.note, "source_doc": f.source_doc,
             "confidence": f.confidence}
            for f in self._flags
        ]

    def _citations_as_dicts(self) -> list[dict]:
        return [
            {"claim": c.claim, "document": c.document, "location": c.location,
             "confidence": c.confidence, "raw_text": c.raw_text}
            for c in self._citations
        ]

    def predict(self, context, model_input):
        """Required by mlflow.pyfunc.PythonModel. Delegates to run()."""
        company_name  = model_input.get("company_name")
        llm_endpoint  = model_input.get("llm_endpoint",
                                        "databricks-meta-llama-3-3-70b-instruct")
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
        return self.run(company_name=company_name, spark=spark,
                        llm_endpoint=llm_endpoint)

    def run(self, company_name: str, spark, llm_endpoint: str) -> dict:
        raise NotImplementedError("Subclasses must implement run().")
