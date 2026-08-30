from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import re

from app.agents.shift.contracts import ShiftHandoverData, ShiftHandover, SafetyCriticalItem


class HandoverQualityReport(BaseModel):
    """
    Structured domain evaluation report produced by the Shift Handover Quality Gate.
    """
    handover_id: Optional[str] = None
    unit_id: str
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall quality score (0-100%)")
    is_passing: bool = Field(..., description="True if score >= passing_threshold (default 75%)")
    passing_threshold: float = 75.0
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    missing_items: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    summary_evaluation: str = ""


class ShiftHandoverQualityGate:
    """
    AI Quality Gate & Completeness Evaluator for Shift Handover packages.
    Evaluates packages against 5 industrial compliance dimensions prior to submission.
    """

    EQUIPMENT_TAG_REGEX = re.compile(r"\b([PCEVKTX]-[0-9]{3,4}[A-Z]?|XV-[0-9]{3,4}|MOV-[0-9]{3,4})\b", re.IGNORECASE)
    MEASUREMENT_REGEX = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mm/s|bar|psi|°c|deg c|%|kg/h|bpd|gpm|m3/h|rpm|rpm|kpa)\b", re.IGNORECASE)

    def __init__(self, passing_threshold: float = 75.0):
        self.passing_threshold = passing_threshold

    def evaluate(self, handover_data: ShiftHandoverData, handover_id: Optional[str] = None) -> HandoverQualityReport:
        """
        Evaluate a ShiftHandoverData domain payload and generate a HandoverQualityReport.
        """
        missing_items: List[str] = []
        recommendations: List[str] = []
        dimension_scores: Dict[str, float] = {}

        # 1. Operational Summary Evaluation (25 pts)
        summary = (handover_data.operational_summary or "").strip()
        summary_score = 0.0
        if not summary:
            missing_items.append("Operational summary is completely empty.")
            recommendations.append("Add a summary detailing throughput, operating mode, and major shift events.")
        else:
            if len(summary) >= 30:
                summary_score += 10.0
            elif len(summary) >= 15:
                summary_score += 5.0
            else:
                missing_items.append("Operational summary is too brief (<15 chars).")

            # Check for throughput or operational numbers
            if re.search(r"\b\d+\b", summary):
                summary_score += 8.0
            else:
                recommendations.append("Include quantitative metrics (e.g. throughput rate, operating pressure/temp) in operational summary.")

            # Check for key operational keywords
            if any(k in summary.lower() for k in ["normal", "stable", "mode", "throughput", "bpd", "rate", "steady", "shutdown", "startup", "run"]):
                summary_score += 7.0
        dimension_scores["summary_clarity"] = round(min(summary_score, 25.0), 1)

        # 2. Equipment Abnormalities Specification (25 pts)
        abnormalities = handover_data.equipment_abnormalities or []
        abnormality_score = 25.0
        if not abnormalities:
            # Having zero abnormalities is acceptable if unit is 100% normal, but give full score
            abnormality_score = 25.0
        else:
            tags_found = 0
            readings_found = 0
            for ab in abnormalities:
                if self.EQUIPMENT_TAG_REGEX.search(ab):
                    tags_found += 1
                if self.MEASUREMENT_REGEX.search(ab) or re.search(r"\b\d+\b", ab):
                    readings_found += 1

            if tags_found < len(abnormalities):
                missing_items.append(f"{len(abnormalities) - tags_found} equipment abnormality item(s) missing specific equipment tags (e.g., P-101A, C-101).")
                recommendations.append("Specify equipment tags for all logged abnormalities.")
                abnormality_score -= 8.0

            if readings_found < len(abnormalities):
                recommendations.append("Include measured values or engineering units (e.g., 4.5 mm/s, 12 bar) for abnormal readings.")
                abnormality_score -= 5.0
        dimension_scores["abnormality_detail"] = round(max(abnormality_score, 0.0), 1)

        # 3. LOTO & Safety Items Integrity (25 pts)
        safety_items = handover_data.safety_items or []
        loto_isolations = handover_data.loto_isolations or []
        open_permits = handover_data.open_permits or []
        safety_score = 25.0

        total_safety_count = len(safety_items) + len(loto_isolations) + len(open_permits)
        if total_safety_count == 0:
            # Clean shift, full points
            safety_score = 25.0
        else:
            # Verify safety items have valid categories and tags
            untagged_items = 0
            for s_item in safety_items:
                if not s_item.equipment_tag or s_item.equipment_tag == "GENERAL":
                    untagged_items += 1
            for loto in loto_isolations:
                if not self.EQUIPMENT_TAG_REGEX.search(loto):
                    untagged_items += 1

            if untagged_items > 0:
                missing_items.append(f"{untagged_items} LOTO / safety critical item(s) lack specific equipment tags.")
                recommendations.append("Tag all LOTO isolations and safety permits with target equipment tag.")
                safety_score -= 10.0

        dimension_scores["safety_integrity"] = round(max(safety_score, 0.0), 1)

        # 4. Carry-Forward Actions Tracking (15 pts)
        actions = handover_data.carry_forward_actions or []
        action_score = 15.0
        if actions:
            vague_actions = [a for a in actions if len(a.strip()) < 10]
            if vague_actions:
                missing_items.append(f"{len(vague_actions)} carry-forward action item(s) are vague or too short.")
                recommendations.append("Provide actionable details and target roles for carry-forward actions.")
                action_score -= 5.0
        dimension_scores["carry_forward_actions"] = round(action_score, 1)

        # 5. Safety Acknowledgement Readiness (10 pts)
        ack_score = 10.0
        if safety_items:
            unacked = [s for s in safety_items if s.active and not s.acknowledged_by_incoming]
            if unacked:
                recommendations.append(f"{len(unacked)} safety-critical item(s) await incoming operator acknowledgement.")
                ack_score -= 3.0
        dimension_scores["acknowledgement_readiness"] = round(ack_score, 1)

        # Calculate Overall Score (0-100)
        overall_score = round(sum(dimension_scores.values()), 1)
        is_passing = overall_score >= self.passing_threshold

        summary_eval = (
            f"Handover package quality score is {overall_score:.1f}% ({'PASSED' if is_passing else 'NEEDS IMPROVEMENT'}). "
            f"Threshold: {self.passing_threshold:.1f}%."
        )

        return HandoverQualityReport(
            handover_id=handover_id,
            unit_id=handover_data.unit_id,
            overall_score=overall_score,
            is_passing=is_passing,
            passing_threshold=self.passing_threshold,
            dimension_scores=dimension_scores,
            missing_items=missing_items,
            recommendations=recommendations,
            summary_evaluation=summary_eval
        )


# Global singleton instance
shift_quality_gate = ShiftHandoverQualityGate()
