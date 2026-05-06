from datetime import datetime, date
from typing import List, Optional, Tuple
from CropsRecomendations.models import Recommendation, RecommendationItem
import logging

logger = logging.getLogger(__name__)


# ── Stage definitions ──────────────────────────────────────────────────────
#  Each entry: (stage_key, label, day_start, day_end, farmer_indices, agro_indices)

STAGE_DEFINITIONS = [
    {
        "key":           "pre_planting_early",
        "label":         "Pre Planting (Early Growth)",
        "day_start":     0,
        "day_end":       30,
        "farmer_indices": ["MSAVI"],
        "agro_indices":   ["MSAVI", "NDVI"],
    },
    {
        "key":           "vegetative_growth",
        "label":         "Vegetative Growth",
        "day_start":     30,
        "day_end":       65,
        "farmer_indices": ["NDVI"],
        "agro_indices":   ["NDVI", "NDMI", "NDRE"],
    },
    {
        "key":           "flowering_reproductive",
        "label":         "Flowering/Reproductive",
        "day_start":     65,
        "day_end":       95,
        "farmer_indices": ["NDVI"],
        "agro_indices":   ["NDVI", "NDMI", "NDRE"],
    },
    {
        "key":           "maturity_pre_harvest",
        "label":         "Maturity/Pre-Harvest",
        "day_start":     95,
        "day_end":       135,
        "farmer_indices": ["NDVI"],
        "agro_indices":   ["NDVI", "ReCL"],
    },
]


def get_stage_for_days(days_since_sowing: int) -> Optional[dict]:
    """Return the stage definition dict for the given days since sowing, or None."""
    for stage in STAGE_DEFINITIONS:
        if stage["day_start"] <= days_since_sowing <= stage["day_end"]:
            return stage
    return None


def get_days_since_sowing(sowing_date: date) -> int:
    return (datetime.now().date() - sowing_date).days


class RecommendationFilter:
    """
    Filters RecommendationItems by the current crop stage,
    determined from days elapsed since sowing_date.

    Report types
    ------------
    - "farmer" : single index per stage (simpler report for the farmer)
    - "agro"   : multiple indices per stage (detailed report for agronomists)
    """

    def __init__(
        self,
        recommendations: List[Recommendation],
        sowing_date: date,
        report_type: str = "farmer",   # "farmer" | "agro"
    ):
        self.recommendations = recommendations
        self.sowing_date     = sowing_date
        self.report_type     = report_type
        self.current_date    = datetime.now().date()

        self.days_since_sowing: int        = get_days_since_sowing(sowing_date)
        self.current_stage: Optional[dict] = get_stage_for_days(self.days_since_sowing)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_applicable_items(self) -> List[RecommendationItem]:
        """
        Return RecommendationItems whose crop_stage and indice match the
        current stage and the report_type's allowed indices.
        """
        if self.current_stage is None:
            logger.warning(
                f"RecommendationFilter: day {self.days_since_sowing} is outside "
                f"all defined stages — no items returned."
            )
            return []

        all_items  = self._get_all_items()
        stage_key  = self.current_stage["key"]
        allowed_ix = self._allowed_indices()

        applicable = [
            item for item in all_items
            if item.crop_stage == stage_key and item.indice in allowed_ix
        ]

        logger.info(
            f"RecommendationFilter [{self.report_type}]: "
            f"day={self.days_since_sowing}, stage={stage_key}, "
            f"allowed_indices={allowed_ix}, "
            f"matched {len(applicable)}/{len(all_items)} items"
        )
        return applicable

    def get_stage_info(self) -> dict:
        """Return metadata about the current stage (useful for PDF headers)."""
        if self.current_stage is None:
            return {
                "key":             None,
                "label":           "Unknown Stage",
                "days_since_sowing": self.days_since_sowing,
                "indices":         [],
            }
        return {
            "key":               self.current_stage["key"],
            "label":             self.current_stage["label"],
            "days_since_sowing": self.days_since_sowing,
            "day_range":         f"{self.current_stage['day_start']}-{self.current_stage['day_end']} days",
            "indices":           self._allowed_indices(),
        }

    # ── Private helpers ────────────────────────────────────────────────────

    def _get_all_items(self) -> List[RecommendationItem]:
        items = []
        for rec in self.recommendations:
            items.extend(rec.items.all())
        return items

    def _allowed_indices(self) -> List[str]:
        if self.current_stage is None:
            return []
        key = "farmer_indices" if self.report_type == "farmer" else "agro_indices"
        return self.current_stage[key]