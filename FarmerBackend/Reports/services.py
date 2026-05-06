# """
# services.py  – Report generation orchestrator
# """

# import logging
# from datetime import datetime, date
# from typing import Optional, List

# from django.core.exceptions import ObjectDoesNotExist
# from django.core.files.base import ContentFile
# from django.utils import timezone

# from User.models import CustomUser, Farms
# from CropsRecomendations.models import Recommendation, RecommendationItem
# from Reports.models import Reports
# from .pdf_generator import PDFGenerator
# from .filters import RecommendationFilter, get_days_since_sowing, get_stage_for_days
# from .ndvi_service import fetch_ndvi_images
# from .weather_service import fetch_weather

# logger = logging.getLogger(__name__)


# class ReportGenerationService:
#     """
#     Orchestrates report generation for a single farm.

#     report_type
#     -----------
#     "farmer"  – single index per stage (simpler, farmer-facing PDF)
#     "agro"    – multiple indices per stage (detailed, agronomist PDF)
#     """

#     def __init__(self, user: CustomUser, farm_id: int, report_type: str = "farmer"):
#         self.user        = user
#         self.farm_id     = farm_id
#         self.report_type = report_type   # "farmer" | "agro"

#         self.farm: Optional[Farms]               = None
#         self.recommendations: List[Recommendation]     = []
#         self.recommendation_items: List[RecommendationItem] = []

#         # Stage info populated after _filter_recommendation_items()
#         self.stage_info: dict = {}
#         self.indices_to_fetch: List[str] = []

#         # Satellite results  key = index name, value = PNG bytes
#         self._index_pngs:  dict           = {}
#         self._kmeans_png:  Optional[bytes] = None
#         self._basemap_png: Optional[bytes] = None
#         self._ndvi_stats:  dict            = {}
#         self._weather:     dict            = {}

#     # ── Cache check ────────────────────────────────────────────────────────

#     def get_todays_successful_report(self) -> Optional[Reports]:
#         try:
#             self._load_farm()
#         except Exception as e:
#             logger.error(f"Farm loading failed: {e}")
#             return None

#         today_start = timezone.now().replace(hour=0,  minute=0,  second=0,  microsecond=0)
#         today_end   = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

#         report = Reports.objects.filter(
#             farm_id=self.farm_id,
#             generated_at__gte=today_start,
#             generated_at__lte=today_end,
#             is_successful=True,
#             # report_type=self.report_type,     # cache is per report_type
#         ).order_by('-generated_at').first()

#         if report:
#             logger.info(f"Cached {self.report_type} report {report.id} for farm {self.farm_id}")
#         return report

#     # ── Main ───────────────────────────────────────────────────────────────

#     def generate(self) -> Reports:
#         self._load_farm()
#         self._filter_recommendations()
#         self._filter_recommendation_items()   # also sets self.stage_info & indices_to_fetch
#         self._fetch_satellite_images()
#         self._fetch_weather_data()
#         pdf_content = self._generate_pdf()
#         return self._save_report(pdf_content, is_successful=True)

#     def generate_fallback(self) -> Reports:
#         try:
#             self._load_farm()
#         except Exception as e:
#             logger.error(f"Farm loading failed in fallback: {e}")
#             raise
#         pdf_content = self._generate_fallback_pdf()
#         return self._save_report(pdf_content, is_successful=False)

#     # ── Pipeline steps ─────────────────────────────────────────────────────

#     def _load_farm(self) -> None:
#         try:
#             self.farm = Farms.objects.select_related(
#                 'crop_season', 'crop', 'created_by'
#             ).get(id=self.farm_id)
#         except ObjectDoesNotExist:
#             raise ValueError(f"Farm {self.farm_id} not found")
#         if not self.farm.crop_season or not self.farm.crop:
#             raise ValueError("Farm must have crop_season and crop assigned")
#         if not self.farm.sowing_date:
#             raise ValueError("Farm must have a sowing_date")

#     def _filter_recommendations(self) -> None:
#         self.recommendations = list(
#             Recommendation.objects.filter(
#                 season=self.farm.crop_season,
#                 crop=self.farm.crop,
#             ).prefetch_related('items')
#         )
#         if not self.recommendations:
#             logger.warning(
#                 f"No recommendations for season={self.farm.crop_season.id}, "
#                 f"crop={self.farm.crop.id}"
#             )

#     def _filter_recommendation_items(self) -> None:
#         """
#         1. Calculate days since sowing.
#         2. Determine current stage.
#         3. Filter recommendation items for that stage.
#         4. Store stage_info and which indices to call Sentinel for.
#         """
#         days = get_days_since_sowing(self.farm.sowing_date)
#         stage = get_stage_for_days(days)

#         if stage is None:
#             logger.warning(
#                 f"Day {days} since sowing is outside all crop stages "
#                 f"(farm {self.farm_id}). No items or satellite calls."
#             )
#             self.stage_info = {
#                 "key": None,
#                 "label": "Outside crop cycle",
#                 "days_since_sowing": days,
#                 "day_range": "N/A",
#                 "indices": [],
#             }
#             self.indices_to_fetch = []
#             return

#         # Determine indices based on report type
#         ix_key = "farmer_indices" if self.report_type == "farmer" else "agro_indices"
#         self.indices_to_fetch = stage[ix_key]

#         self.stage_info = {
#             "key":               stage["key"],
#             "label":             stage["label"],
#             "days_since_sowing": days,
#             "day_range":         f"{stage['day_start']}-{stage['day_end']} days",
#             "indices":           self.indices_to_fetch,
#         }

#         logger.info(
#             f"Farm {self.farm_id} | day={days} | stage={stage['key']} | "
#             f"report_type={self.report_type} | indices={self.indices_to_fetch}"
#         )

#         if not self.recommendations:
#             return

#         filter_svc = RecommendationFilter(
#             recommendations=self.recommendations,
#             sowing_date=self.farm.sowing_date,
#             report_type=self.report_type,
#         )
#         self.recommendation_items = filter_svc.get_applicable_items()

#         if not self.recommendation_items:
#             logger.warning(
#                 f"No recommendation items matched stage={stage['key']} "
#                 f"for report_type={self.report_type}"
#             )

#     def _fetch_satellite_images(self) -> None:
#         """
#         Fetch only the indices needed for the current stage.
#         Uses today's date as the centre of the Sentinel-Hub time window
#         (not sowing_date) so we always see current crop condition.
#         """
#         if not self.indices_to_fetch:
#             logger.info(f"No indices to fetch for farm {self.farm_id} — skipping satellite.")
#             return

#         polygon_coords = self._get_polygon_coords()
#         if not polygon_coords:
#             logger.warning(f"Farm {self.farm_id} has no polygon; skipping satellite imagery")
#             return

#         # Use TODAY as the date centre for imagery
#         today_str = datetime.now().strftime("%Y-%m-%d")

#         try:
#             result = fetch_ndvi_images(
#                 polygon_coords=polygon_coords,
#                 date_str=today_str,
#                 date_range_days=15,
#                 indices=self.indices_to_fetch,
#             )
#             if result.get("error"):
#                 logger.error(f"Satellite fetch error: {result['error']}")
#             else:
#                 self._index_pngs  = result.get("index_pngs", {})
#                 self._kmeans_png  = result.get("kmeans_png")
#                 self._basemap_png = result.get("basemap_png")
#                 self._ndvi_stats  = result.get("stats", {})
#                 logger.info(
#                     f"Satellite OK for farm {self.farm_id}: "
#                     f"indices fetched={list(self._index_pngs.keys())}"
#                 )
#         except Exception as e:
#             logger.error(f"_fetch_satellite_images failed: {e}", exc_info=True)

#     def _fetch_weather_data(self) -> None:
#         centroid = self._get_centroid()
#         if not centroid:
#             logger.warning(f"Farm {self.farm_id} has no centroid; skipping weather")
#             return
#         lat, lon = centroid
#         try:
#             self._weather = fetch_weather(lat, lon, days=16)
#             if self._weather.get("error"):
#                 logger.error(f"Weather fetch error: {self._weather['error']}")
#         except Exception as e:
#             logger.error(f"_fetch_weather_data failed: {e}", exc_info=True)

#     # ── Helpers ────────────────────────────────────────────────────────────

#     def _get_polygon_coords(self):
#         import json
#         bbox_field = getattr(self.farm, 'bbox', None)
#         if bbox_field:
#             raw = bbox_field
#             if isinstance(raw, str):
#                 try:
#                     raw = json.loads(raw)
#                 except Exception:
#                     raw = None
#             if isinstance(raw, list) and len(raw) >= 3:
#                 try:
#                     coords = [[float(c[1]), float(c[0])] for c in raw]
#                     if coords[0] != coords[-1]:
#                         coords.append(coords[0])
#                     return coords
#                 except Exception as e:
#                     logger.warning(f"bbox parse failed: {e}")

#         polygon_field = getattr(self.farm, 'polygon', None)
#         if polygon_field:
#             if isinstance(polygon_field, dict):
#                 coords = polygon_field.get('coordinates', [])
#                 if coords:
#                     return coords[0]
#             if hasattr(polygon_field, 'coords'):
#                 return list(polygon_field.coords[0])

#         coords_field = getattr(self.farm, 'coordinates', None)
#         if coords_field:
#             if isinstance(coords_field, list):
#                 return coords_field
#             if isinstance(coords_field, str):
#                 try:
#                     return json.loads(coords_field)
#                 except Exception:
#                     pass
#         return None

#     def _get_centroid(self):
#         import json
#         bbox_field = getattr(self.farm, 'bbox', None)
#         if bbox_field:
#             raw = bbox_field
#             if isinstance(raw, str):
#                 try:
#                     raw = json.loads(raw)
#                 except Exception:
#                     raw = None
#             if isinstance(raw, list) and len(raw) >= 3:
#                 try:
#                     lats = [float(c[0]) for c in raw]
#                     lons = [float(c[1]) for c in raw]
#                     return (sum(lats) / len(lats), sum(lons) / len(lons))
#                 except Exception:
#                     pass

#         coords = self._get_polygon_coords()
#         if coords:
#             lons = [c[0] for c in coords]
#             lats = [c[1] for c in coords]
#             return (sum(lats) / len(lats), sum(lons) / len(lons))
#         return None

#     def _get_soil_data(self) -> dict:
#         f = self.farm
#         return {
#             "ec":         getattr(f, 'soil_ec',         getattr(f, 'ec',             None)),
#             "om":         getattr(f, 'soil_om',         getattr(f, 'organic_matter',  None)),
#             "ph":         getattr(f, 'soil_ph',         getattr(f, 'ph',             None)),
#             "nitrogen":   getattr(f, 'soil_nitrogen',   getattr(f, 'nitrogen',        None)),
#             "phosphorus": getattr(f, 'soil_phosphorus', getattr(f, 'phosphorus',      None)),
#             "potassium":  getattr(f, 'soil_potassium',  getattr(f, 'potassium',       None)),
#             "zinc":       getattr(f, 'soil_zinc',       getattr(f, 'zinc',            None)),
#             "copper":     getattr(f, 'soil_copper',     getattr(f, 'copper',          None)),
#             "iron":       getattr(f, 'soil_iron',       getattr(f, 'iron',            None)),
#             "manganese":  getattr(f, 'soil_manganese',  getattr(f, 'manganese',       None)),
#             "boron":      getattr(f, 'soil_boron',      getattr(f, 'boron',           None)),
#             "saturation": getattr(f, 'soil_saturation', getattr(f, 'saturation',      None)),
#             "soil_type":  getattr(f, 'soil_type',       None),
#         }

#     def _generate_pdf(self) -> bytes:
#         generator = PDFGenerator(
#             farm=self.farm,
#             user=self.user,
#             recommendation_items=self.recommendation_items,
#             # Pass all index PNGs + the primary one for backwards compat
#             index_pngs=self._index_pngs,
#             ndvi_png=self._index_pngs.get("NDVI") or next(iter(self._index_pngs.values()), None),
#             kmeans_png=self._kmeans_png,
#             basemap_png=self._basemap_png,
#             ndvi_stats=self._ndvi_stats,
#             weather_data=self._weather,
#             soil_data=self._get_soil_data(),
#             stage_info=self.stage_info,
#             report_type=self.report_type,
#         )
#         return generator.generate()

#     def _generate_fallback_pdf(self) -> bytes:
#         generator = PDFGenerator(
#             farm=self.farm,
#             user=self.user,
#             recommendation_items=[],
#             report_type=self.report_type,
#         )
#         return generator.generate_fallback()

#     def _save_report(self, pdf_content: bytes, is_successful: bool = True) -> Reports:
#         report = Reports(
#             user=self.user,
#             farm=self.farm,
#             crop_season=self.farm.crop_season,
#             crop_type=self.farm.crop,
#             sowing_date=self.farm.sowing_date,
#             is_successful=is_successful,
#             report_type=self.report_type,     # store so cache lookup works
#         )
#         filename = self._generate_filename()
#         report.report_file.save(filename, ContentFile(pdf_content), save=False)
#         report.save()
#         logger.info(
#             f"Report {report.id} saved "
#             f"({'OK' if is_successful else 'fallback'}, type={self.report_type}) "
#             f"for farm {self.farm_id}"
#         )
#         return report

#     def _generate_filename(self) -> str:
#         timestamp   = datetime.now().strftime("%Y%m%d_%I%M%p").lower()
#         user_mobile = getattr(self.user, "mobile_number", "user")
#         farm_name   = self.farm.farm_name.replace(" ", "_")
#         return f"{farm_name}_{user_mobile}_{self.report_type}_{timestamp}.pdf"


"""
services.py  – Report generation orchestrator
"""

import logging
from datetime import datetime, date
from typing import Optional, List

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.utils import timezone

from User.models import CustomUser, Farms
from CropsRecomendations.models import Recommendation, RecommendationItem
from Reports.models import Reports
from .pdf_generator import PDFGenerator
from .filters import RecommendationFilter, get_days_since_sowing, get_stage_for_days
from .ndvi_service import fetch_ndvi_images
from .weather_service import fetch_weather

logger = logging.getLogger(__name__)


class ReportGenerationService:
    """
    Orchestrates report generation for a single farm.

    report_type
    -----------
    "farmer"  – single index per stage (simpler, farmer-facing PDF)
    "agro"    – multiple indices per stage (detailed, agronomist PDF)
    """

    def __init__(self, user: CustomUser, farm_id: int, report_type: str = "farmer"):
        self.user        = user
        self.farm_id     = farm_id
        self.report_type = report_type   # "farmer" | "agro"

        self.farm: Optional[Farms]               = None
        self.recommendations: List[Recommendation]     = []
        self.recommendation_items: List[RecommendationItem] = []

        # Stage info populated after _filter_recommendation_items()
        self.stage_info: dict = {}
        self.indices_to_fetch: List[str] = []

        # Satellite results  key = index name, value = PNG bytes
        self._index_pngs:  dict           = {}
        self._kmeans_png:  Optional[bytes] = None
        self._basemap_png: Optional[bytes] = None
        self._ndvi_stats:  dict            = {}
        self._weather:     dict            = {}

    # ── Cache check ────────────────────────────────────────────────────────

    def get_todays_successful_report(self) -> Optional[Reports]:
        try:
            self._load_farm()
        except Exception as e:
            logger.error(f"Farm loading failed: {e}")
            return None

        today_start = timezone.now().replace(hour=0,  minute=0,  second=0,  microsecond=0)
        today_end   = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

        report = Reports.objects.filter(
            farm_id=self.farm_id,
            generated_at__gte=today_start,
            generated_at__lte=today_end,
            is_successful=True,
            # report_type=self.report_type,     # cache is per report_type
        ).order_by('-generated_at').first()

        if report:
            logger.info(f"Cached {self.report_type} report {report.id} for farm {self.farm_id}")
        return report

    # ── Main ───────────────────────────────────────────────────────────────

    def generate(self) -> Reports:
        self._load_farm()
        self._filter_recommendations()
        self._filter_recommendation_items()   # also sets self.stage_info & indices_to_fetch
        self._fetch_satellite_images()
        self._fetch_weather_data()
        pdf_content = self._generate_pdf()
        return self._save_report(pdf_content, is_successful=True)

    def generate_fallback(self) -> Reports:
        try:
            self._load_farm()
        except Exception as e:
            logger.error(f"Farm loading failed in fallback: {e}")
            raise
        pdf_content = self._generate_fallback_pdf()
        return self._save_report(pdf_content, is_successful=False)

    # ── Pipeline steps ─────────────────────────────────────────────────────

    def _load_farm(self) -> None:
        try:
            self.farm = Farms.objects.select_related(
                'crop_season', 'crop', 'created_by'
            ).get(id=self.farm_id)
        except ObjectDoesNotExist:
            raise ValueError(f"Farm {self.farm_id} not found")
        if not self.farm.crop_season or not self.farm.crop:
            raise ValueError("Farm must have crop_season and crop assigned")
        if not self.farm.sowing_date:
            raise ValueError("Farm must have a sowing_date")

    def _filter_recommendations(self) -> None:
        self.recommendations = list(
            Recommendation.objects.filter(
                season=self.farm.crop_season,
                crop=self.farm.crop,
            ).prefetch_related('items')
        )
        if not self.recommendations:
            logger.warning(
                f"No recommendations for season={self.farm.crop_season.id}, "
                f"crop={self.farm.crop.id}"
            )

    def _filter_recommendation_items(self) -> None:
        """
        1. Calculate days since sowing.
        2. Determine current stage.
        3. Filter recommendation items for that stage.
        4. Store stage_info and which indices to call Sentinel for.
        """
        days = get_days_since_sowing(self.farm.sowing_date)
        stage = get_stage_for_days(days)

        if stage is None:
            logger.warning(
                f"Day {days} since sowing is outside all crop stages "
                f"(farm {self.farm_id}). No items or satellite calls."
            )
            self.stage_info = {
                "key": None,
                "label": "Outside crop cycle",
                "days_since_sowing": days,
                "day_range": "N/A",
                "indices": [],
            }
            self.indices_to_fetch = []
            return

        # Determine indices based on report type
        ix_key = "farmer_indices" if self.report_type == "farmer" else "agro_indices"
        self.indices_to_fetch = stage[ix_key]

        self.stage_info = {
            "key":               stage["key"],
            "label":             stage["label"],
            "days_since_sowing": days,
            "day_range":         f"{stage['day_start']}-{stage['day_end']} days",
            "indices":           self.indices_to_fetch,
        }

        logger.info(
            f"Farm {self.farm_id} | day={days} | stage={stage['key']} | "
            f"report_type={self.report_type} | indices={self.indices_to_fetch}"
        )

        if not self.recommendations:
            return

        filter_svc = RecommendationFilter(
            recommendations=self.recommendations,
            sowing_date=self.farm.sowing_date,
            report_type=self.report_type,
        )
        self.recommendation_items = filter_svc.get_applicable_items()

        if not self.recommendation_items:
            logger.warning(
                f"No recommendation items matched stage={stage['key']} "
                f"for report_type={self.report_type}"
            )

    def _fetch_satellite_images(self) -> None:
        """
        Fetch only the indices needed for the current stage.
        Uses today's date as the centre of the Sentinel-Hub time window
        (not sowing_date) so we always see current crop condition.
        """
        if not self.indices_to_fetch:
            logger.info(f"No indices to fetch for farm {self.farm_id} — skipping satellite.")
            return

        polygon_coords = self._get_polygon_coords()
        if not polygon_coords:
            logger.warning(f"Farm {self.farm_id} has no polygon; skipping satellite imagery")
            return

        # Use TODAY as the date centre for imagery
        today_str = datetime.now().strftime("%Y-%m-%d")

        try:
            result = fetch_ndvi_images(
                polygon_coords=polygon_coords,
                date_str=today_str,
                date_range_days=15,
                indices=self.indices_to_fetch,
            )
            if result.get("error"):
                logger.error(f"Satellite fetch error: {result['error']}")
            else:
                self._index_pngs  = result.get("index_pngs", {})
                self._kmeans_png  = result.get("kmeans_png")
                self._basemap_png = result.get("basemap_png")
                self._ndvi_stats  = result.get("stats", {})
                logger.info(
                    f"Satellite OK for farm {self.farm_id}: "
                    f"indices fetched={list(self._index_pngs.keys())}"
                )
        except Exception as e:
            logger.error(f"_fetch_satellite_images failed: {e}", exc_info=True)

    def _fetch_weather_data(self) -> None:
        centroid = self._get_centroid()
        if not centroid:
            logger.warning(f"Farm {self.farm_id} has no centroid; skipping weather")
            return
        lat, lon = centroid
        try:
            self._weather = fetch_weather(lat, lon, days=16)
            if self._weather.get("error"):
                logger.error(f"Weather fetch error: {self._weather['error']}")
        except Exception as e:
            logger.error(f"_fetch_weather_data failed: {e}", exc_info=True)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_polygon_coords(self):
        import json
        bbox_field = getattr(self.farm, 'bbox', None)
        if bbox_field:
            raw = bbox_field
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = None
            if isinstance(raw, list) and len(raw) >= 3:
                try:
                    coords = [[float(c[1]), float(c[0])] for c in raw]
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    return coords
                except Exception as e:
                    logger.warning(f"bbox parse failed: {e}")

        polygon_field = getattr(self.farm, 'polygon', None)
        if polygon_field:
            if isinstance(polygon_field, dict):
                coords = polygon_field.get('coordinates', [])
                if coords:
                    return coords[0]
            if hasattr(polygon_field, 'coords'):
                return list(polygon_field.coords[0])

        coords_field = getattr(self.farm, 'coordinates', None)
        if coords_field:
            if isinstance(coords_field, list):
                return coords_field
            if isinstance(coords_field, str):
                try:
                    return json.loads(coords_field)
                except Exception:
                    pass
        return None

    def _get_centroid(self):
        import json
        bbox_field = getattr(self.farm, 'bbox', None)
        if bbox_field:
            raw = bbox_field
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = None
            if isinstance(raw, list) and len(raw) >= 3:
                try:
                    lats = [float(c[0]) for c in raw]
                    lons = [float(c[1]) for c in raw]
                    return (sum(lats) / len(lats), sum(lons) / len(lons))
                except Exception:
                    pass

        coords = self._get_polygon_coords()
        if coords:
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return (sum(lats) / len(lats), sum(lons) / len(lons))
        return None

    def _get_soil_data(self) -> dict:
        f = self.farm
        return {
            "ec":         getattr(f, 'soil_ec',         getattr(f, 'ec',             None)),
            "om":         getattr(f, 'soil_om',         getattr(f, 'organic_matter',  None)),
            "ph":         getattr(f, 'soil_ph',         getattr(f, 'ph',             None)),
            "nitrogen":   getattr(f, 'soil_nitrogen',   getattr(f, 'nitrogen',        None)),
            "phosphorus": getattr(f, 'soil_phosphorus', getattr(f, 'phosphorus',      None)),
            "potassium":  getattr(f, 'soil_potassium',  getattr(f, 'potassium',       None)),
            "zinc":       getattr(f, 'soil_zinc',       getattr(f, 'zinc',            None)),
            "copper":     getattr(f, 'soil_copper',     getattr(f, 'copper',          None)),
            "iron":       getattr(f, 'soil_iron',       getattr(f, 'iron',            None)),
            "manganese":  getattr(f, 'soil_manganese',  getattr(f, 'manganese',       None)),
            "boron":      getattr(f, 'soil_boron',      getattr(f, 'boron',           None)),
            "saturation": getattr(f, 'soil_saturation', getattr(f, 'saturation',      None)),
            "soil_type":  getattr(f, 'soil_type',       None),
        }

    def _generate_pdf(self) -> bytes:
        # ── Compute zone areas in acres from pixel counts ──────────────────
        zone_acres: dict = {}
        try:
            total_acres_raw = getattr(self.farm, 'total_acres', None)
            total_acres     = float(total_acres_raw) if total_acres_raw else None
            pixel_counts    = self._ndvi_stats.get("zone_pixel_counts", {})
            total_pixels    = self._ndvi_stats.get("total_pixels", 0)
            if total_acres and total_pixels > 0:
                for zone_id, px in pixel_counts.items():
                    zone_acres[int(zone_id)] = round(total_acres * px / total_pixels, 2)
        except Exception as e:
            logger.warning(f"Zone acres calculation failed: {e}")

        generator = PDFGenerator(
            farm=self.farm,
            user=self.user,
            recommendation_items=self.recommendation_items,
            index_pngs=self._index_pngs,
            ndvi_png=self._index_pngs.get("NDVI") or next(iter(self._index_pngs.values()), None),
            kmeans_png=self._kmeans_png,
            basemap_png=self._basemap_png,
            ndvi_stats=self._ndvi_stats,
            weather_data=self._weather,
            soil_data=self._get_soil_data(),
            stage_info=self.stage_info,
            report_type=self.report_type,
            zone_acres=zone_acres,
        )
        return generator.generate()

    def _generate_fallback_pdf(self) -> bytes:
        generator = PDFGenerator(
            farm=self.farm,
            user=self.user,
            recommendation_items=[],
            report_type=self.report_type,
        )
        return generator.generate_fallback()

    def _save_report(self, pdf_content: bytes, is_successful: bool = True) -> Reports:
        report = Reports(
            user=self.user,
            farm=self.farm,
            crop_season=self.farm.crop_season,
            crop_type=self.farm.crop,
            sowing_date=self.farm.sowing_date,
            is_successful=is_successful,
            report_type=self.report_type,     # store so cache lookup works
        )
        filename = self._generate_filename()
        report.report_file.save(filename, ContentFile(pdf_content), save=False)
        report.save()
        logger.info(
            f"Report {report.id} saved "
            f"({'OK' if is_successful else 'fallback'}, type={self.report_type}) "
            f"for farm {self.farm_id}"
        )
        return report

    def _generate_filename(self) -> str:
        timestamp   = datetime.now().strftime("%Y%m%d_%I%M%p").lower()
        user_mobile = getattr(self.user, "mobile_number", "user")
        farm_name   = self.farm.farm_name.replace(" ", "_")
        return f"{farm_name}_{user_mobile}_{self.report_type}_{timestamp}.pdf"