# """
# pdf_generator.py
# ----------------
# Generates PDF reports.  Two report types:

# FARMER  ("farmer")
# ──────────────────
# • Stage badge  – shows the ONE active index + "Farmer Advisory" tag
# • Farm/farmer cards, basemap, soil table, weather chart
# • PAGE 2:
#     - Banner: "Satellite Vegetation Analysis – <Stage>"
#     - ONE index image full-width  (whichever index the stage requires)
#     - K-Means zone map full-width below
#     - Zone legend table
#     - Crop Recommendations (grouped by that single index)

# AGRO  ("agro")
# ──────────────
# • Stage badge  – shows ALL active indices + "Agronomist Report" tag
# • Same page-1 content
# • PAGE 2:
#     - Banner: "Satellite Vegetation Analysis – <Stage>"
#     - ALL index images in a 2-up grid  (1 per cell, wrapping rows)
#     - K-Means zone map side-by-side with zone legend
#     - Crop Recommendations grouped by index with technical sub-headers

# The correct indices per stage come from filters.py → STAGE_DEFINITIONS
# and are already stored in stage_info["indices"] by the time PDFGenerator
# is called. The PDF just honours whatever is in index_pngs.

# FIXES APPLIED (Urdu rendering):
#   1. _clean_urdu_text() now called at the top of _urdu_rl() — strips emojis,
#      \r\n, zero-width chars BEFORE passing to arabic_reshaper.
#   2. get_display() (BiDi) re-enabled at draw time and in get_pixel_width() —
#      both reshape AND get_display are required for correct RTL visual order.
#   3. x_pos clamped to max(H_PAD, ...) so short strings never draw at negative x.
#   4. _section_recommendations() pre-cleans rec_text before calling _urdu_rl().
#   5. Blank paragraph lines preserved as spacer lines in the wrapping loop.
# """

# import io
# import logging
# import os as _os
# from datetime import datetime
# from typing import List, Optional, Dict
# import re

# import numpy as np
# import matplotlib
# matplotlib.use('Agg')
# import matplotlib.pyplot as plt
# from matplotlib.lines import Line2D

# from PIL import Image as PILImage, ImageDraw, ImageFont
# import arabic_reshaper
# from bidi.algorithm import get_display

# from reportlab.lib.pagesizes import A4
# from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
# from reportlab.lib.units import inch
# from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
# from reportlab.lib import colors
# from reportlab.platypus import (
#     SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
#     KeepTogether, Image as RLImage, HRFlowable, PageBreak,
# )

# from User.models import CustomUser, Farms
# from CropsRecomendations.models import RecommendationItem
# from django.conf import settings
import os
# from reportlab.pdfbase import pdfmetrics
# from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(BASE_DIR, 'fonts', 'NotoNastaliqUrdu-VariableFont_wght.ttf')

# pdfmetrics.registerFont(TTFont('UrduFont', font_path))
# logger = logging.getLogger(__name__)

# # ── Page geometry ──────────────────────────────────────────────────────────
# W, H = A4
# LM = RM = 0.55 * inch
# CW = W - LM - RM

# # ── Font registration ──────────────────────────────────────────────────────
# FONT_PATH = os.path.join(BASE_DIR, 'fonts', 'NotoNastaliqUrdu-VariableFont_wght.ttf')

# try:
#     pdfmetrics.registerFont(TTFont('UrduFont', FONT_PATH))
#     HAS_URDU_FONT = True
# except Exception as e:
#     logging.error(f"UrduFont registration failed: {e}")
#     HAS_URDU_FONT = False

# # ── Brand colours ──────────────────────────────────────────────────────────
# C_DARK_GREEN  = colors.HexColor('#1B5E20')
# C_MID_GREEN   = colors.HexColor('#388E3C')
# C_LIGHT_GREEN = colors.HexColor('#E8F5E9')
# C_ACCENT      = colors.HexColor('#F57F17')
# C_NAVY        = colors.HexColor('#1A237E')
# C_WHITE       = colors.white
# C_LGRAY       = colors.HexColor('#F5F5F5')
# C_GRAY        = colors.HexColor('#DDDDDD')
# C_DGRAY       = colors.HexColor('#888888')
# C_GREEN_RAW   = colors.HexColor('#00CC00')
# C_YELLOW_RAW  = colors.HexColor('#FFFF00')
# C_PURPLE_RAW  = colors.HexColor('#CC00FF')

# # ── Index metadata ─────────────────────────────────────────────────────────
# INDEX_META: Dict[str, dict] = {
#     "NDVI":  {"full": "Normalised Difference Vegetation Index",  "color": "#388E3C"},
#     "MSAVI": {"full": "Modified Soil-Adjusted Vegetation Index", "color": "#6A5ACD"},
#     "NDRE":  {"full": "Red-Edge Normalised Difference",          "color": "#C0392B"},
#     "ReCL":  {"full": "Red-Edge Chlorophyll Index",              "color": "#D4AC0D"},
#     "NDMI":  {"full": "Normalised Difference Moisture Index",    "color": "#2980B9"},
# }

# # Plain-language captions for farmer report (no jargon)
# INDEX_FARMER_CAPTION: Dict[str, str] = {
#     "NDVI":  "Crop Health Map",
#     "MSAVI": "Early Growth Vegetation Map",
#     "NDRE":  "Crop Stress Map",
#     "ReCL":  "Chlorophyll Content Map",
#     "NDMI":  "Crop Water Stress Map",
# }

# # ── Zone legend ────────────────────────────────────────────────────────────
# ZONE_COLORS = {
#     4: colors.HexColor('#1E8449'),
#     3: colors.HexColor('#A9DFBF'),
#     2: colors.HexColor('#F4D03F'),
#     1: colors.HexColor('#6C3483'),
# }
# ZONE_LABELS = {4: "Zone 4 – Good",    3: "Zone 3 – Moderate",
#                2: "Zone 2 – Low",     1: "Zone 1 – Poor"}
# ZONE_DESC   = {4: "High vegetation density – crop is thriving",
#                3: "Moderate vegetation – healthy growth",
#                2: "Sparse vegetation – monitor closely",
#                1: "Very low / stressed vegetation or bare soil"}

# # ── Stage colours ──────────────────────────────────────────────────────────
# STAGE_COLORS: Dict[str, str] = {
#     "pre_planting_early":     "#4A235A",
#     "vegetative_growth":      "#1B5E20",
#     "flowering_reproductive": "#B7950B",
#     "maturity_pre_harvest":   "#784212",
# }

# # ── Image sizing ───────────────────────────────────────────────────────────
# BASEMAP_TARGET_W = CW * 0.45
# BASEMAP_MAX_H    = 2.8 * inch
# NDVI_MAX_H       = 3.0 * inch

# # ── Paths ──────────────────────────────────────────────────────────────────
# _HERE     = _os.path.dirname(_os.path.abspath(__file__))
# LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "lims_logo.png")

# # ── Soil rows ──────────────────────────────────────────────────────────────
# SOIL_ROWS = [
#     ("مٹی میں نمکیات کی مقدار", "ec",         "dS/m", "<4",      "4.1-8",    ">8",
#      lambda v: v < 4,       lambda v: 4 <= v <= 8),
#     ("نامیاتی مادہ (%)",         "om",         "%",    ">1.3",    "0.86-1.3", "<0.86",
#      lambda v: v > 1.3,     lambda v: 0.86 <= v <= 1.3),
#     ("زمین کی تیزابیت",          "ph",         "",     "6.5-7.5", "7.5-8.5",  ">8.5",
#      lambda v: 6.5<=v<=7.5, lambda v: 7.5 < v <= 8.5),
#     ("فاسفورس",                  "phosphorus", "ppm",  ">14",     "7-14",     "<7",
#      lambda v: v > 14,      lambda v: 7 <= v <= 14),
#     ("پوٹاش",                    "potassium",  "ppm",  ">180",    "80-180",   "<80",
#      lambda v: v > 180,     lambda v: 80 <= v <= 180),
#     ("زنک",                      "zinc",       "ppm",  ">1",      "0.5-1",    "<0.5",
#      lambda v: v > 1,       lambda v: 0.5 <= v <= 1),
#     ("کاپر",                     "copper",     "ppm",  ">0.2",    "0.1-0.2",  "<0.1",
#      lambda v: v > 0.2,     lambda v: 0.1 <= v <= 0.2),
#     ("آئرن",                     "iron",       "ppm",  ">4.5",    "2-4.5",    "<2",
#      lambda v: v > 4.5,     lambda v: 2 <= v <= 4.5),
#     ("میگانیز",                  "manganese",  "ppm",  ">1",      "0.5-1",    "<0.5",
#      lambda v: v > 1,       lambda v: 0.5 <= v <= 1),
#     ("بوران",                    "boron",      "ppm",  "0.5-1",   "0.2-0.5",  "<0.2",
#      lambda v: v > 0.5,     lambda v: 0.2 <= v <= 0.5),
#     ("مٹی کی سیرابی",            "saturation", "%",    "46-60%",  "30-45%",   "<20%",
#      lambda v: v >= 46,     lambda v: 30 <= v < 46),
# ]

# DUMMY_SOIL = {
#     "ec": 2.51, "om": 0.42, "ph": 5.8, "nitrogen": None,
#     "phosphorus": 5.8, "potassium": 100, "zinc": 0.53,
#     "copper": 2.51, "iron": 4.5, "manganese": 0.6, "boron": 0.5, "saturation": 32,
# }
# DUMMY_WEATHER = {
#     "city": "Farm Location", "country": "PK",
#     "days": [
#         {"date": "20 Apr", "temp_max": 39.5, "temp_min": 25.0, "humidity": 13, "wind_speed": 3.8, "wind_dir": "NW", "description": "Clear Sky"},
#         {"date": "21 Apr", "temp_max": 41.2, "temp_min": 25.0, "humidity": 11, "wind_speed": 4.5, "wind_dir": "N",  "description": "Sunny"},
#         {"date": "22 Apr", "temp_max": 43.5, "temp_min": 27.0, "humidity": 9,  "wind_speed": 3.9, "wind_dir": "NE", "description": "Clear Sky"},
#         {"date": "23 Apr", "temp_max": 44.5, "temp_min": 27.9, "humidity": 9,  "wind_speed": 5.0, "wind_dir": "N",  "description": "Clear Sky"},
#         {"date": "24 Apr", "temp_max": 44.8, "temp_min": 27.5, "humidity": 9,  "wind_speed": 4.8, "wind_dir": "NW", "description": "Sunny"},
#         {"date": "25 Apr", "temp_max": 46.5, "temp_min": 30.1, "humidity": 9,  "wind_speed": 5.2, "wind_dir": "NE", "description": "Hot"},
#         {"date": "26 Apr", "temp_max": 44.8, "temp_min": 31.2, "humidity": 9,  "wind_speed": 4.6, "wind_dir": "N",  "description": "Clear Sky"},
#         {"date": "27 Apr", "temp_max": 44.5, "temp_min": 31.5, "humidity": 9,  "wind_speed": 4.3, "wind_dir": "NW", "description": "Sunny"},
#         {"date": "28 Apr", "temp_max": 46.7, "temp_min": 31.5, "humidity": 11, "wind_speed": 5.5, "wind_dir": "NE", "description": "Rainy"},
#         {"date": "29 Apr", "temp_max": 45.0, "temp_min": 29.8, "humidity": 11, "wind_speed": 4.8, "wind_dir": "N",  "description": "Rainy"},
#         {"date": "30 Apr", "temp_max": 45.0, "temp_min": 29.5, "humidity": 9,  "wind_speed": 4.6, "wind_dir": "NW", "description": "Clear Sky"},
#         {"date": "01 May", "temp_max": 41.5, "temp_min": 26.5, "humidity": 19, "wind_speed": 3.8, "wind_dir": "W",  "description": "Partly Cloudy"},
#         {"date": "02 May", "temp_max": 41.8, "temp_min": 26.8, "humidity": 21, "wind_speed": 4.2, "wind_dir": "SW", "description": "Partly Cloudy"},
#         {"date": "03 May", "temp_max": 42.5, "temp_min": 27.5, "humidity": 21, "wind_speed": 4.0, "wind_dir": "W",  "description": "Rainy"},
#         {"date": "04 May", "temp_max": 42.0, "temp_min": 30.0, "humidity": 21, "wind_speed": 3.5, "wind_dir": "NW", "description": "Clear Sky"},
#         {"date": "05 May", "temp_max": 44.0, "temp_min": 30.0, "humidity": 17, "wind_speed": 5.5, "wind_dir": "N",  "description": "Hot"},
#     ],
# }
# RAIN_KEYWORDS = {"rain", "rainy", "drizzle", "showers", "thunderstorm",
#                  "stormy", "precipitation", "heavy rain", "light rain"}


# # ══════════════════════════════════════════════════════════════════════════════
# #  Pure helpers
# # ══════════════════════════════════════════════════════════════════════════════

# def _soil_bg(val, exc_fn, avg_fn):
#     if val is None:
#         return colors.white
#     try:
#         v = float(val)
#         if exc_fn and exc_fn(v): return C_GREEN_RAW
#         if avg_fn and avg_fn(v): return C_YELLOW_RAW
#         return C_PURPLE_RAW
#     except Exception:
#         return colors.white


# def _rl2rgb(c):
#     return (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


# def _get_urdu_font_path(bold=False):
#     """
#     Returns path to best available Urdu/Arabic font.
#     Amiri is preferred (plain TTF, PIL handles it perfectly).
#     Falls back to NotoNastaliqUrdu variable font.
#     """
#     fonts_dir = os.path.join(BASE_DIR, "fonts")
#     amiri = os.path.join(fonts_dir, "Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf")
#     if os.path.exists(amiri):
#         logger.info(f"_get_urdu_font_path: using {amiri}")
#         return amiri
#     nastaliq = os.path.join(fonts_dir, "NotoNastaliqUrdu-VariableFont_wght.ttf")
#     if os.path.exists(nastaliq):
#         logger.info(f"_get_urdu_font_path: using {nastaliq}")
#         return nastaliq
#     logger.error(f"_get_urdu_font_path: NO FONT FOUND in {fonts_dir}")
#     return None


# def _clean_urdu_text(text: str) -> str:
#     """
#     Strip emojis, smart punctuation, zero-width chars, and
#     normalise whitespace.  Must be called BEFORE arabic_reshaper.
#     """
#     if not text:
#         return ""
#     # Remove emoji / pictographs
#     emoji_pattern = re.compile(
#         "["
#         "\U0001F300-\U0001F9FF"
#         "\U00002600-\U000027BF"
#         "\U0001FA00-\U0001FAFF"
#         "\U00002702-\U000027B0"
#         "\U000024C2-\U0001F251"
#         "]+",
#         flags=re.UNICODE,
#     )
#     text = emoji_pattern.sub('', text)
#     # Smart dashes → plain dash
#     text = text.replace('\u2013', '-').replace('\u2014', '-')
#     # Zero-width / BOM chars
#     text = text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
#     # Collapse multiple spaces/tabs on one line
#     text = re.sub(r'[ \t]+', ' ', text)
#     # Collapse 3+ newlines → 2
#     text = re.sub(r'\n{3,}', '\n\n', text)
#     return text.strip()


# # ── FIX: complete, corrected _urdu_rl ─────────────────────────────────────
# def _urdu_rl(text, w_pt, h_pt, font_size=10, bg=(245, 245, 245), fg=(0, 0, 0), bold=False):
#     """
#     Render Urdu/Arabic text as a PIL image and return an RLImage flowable.

#     Key invariants (all three must hold together):
#       1. _clean_urdu_text() runs first — removes emojis, \\r\\n, ZWJ etc.
#          that break arabic_reshaper.
#       2. Every string that is drawn goes through:
#              get_display(arabic_reshaper.reshape(s))
#          reshape  → connects letter forms (e.g. ک + ا → کا ligature)
#          get_display → reorders glyphs RTL so PIL's LTR renderer shows
#                        them in the correct reading order.
#       3. get_pixel_width() uses the same two-step transform so that the
#          measured width matches what is actually drawn, keeping line-wrap
#          breaks accurate.
#       4. x_pos is clamped to max(H_PAD, ...) so very short strings never
#          produce a negative coordinate (which PIL silently ignores → blank).
#     """
#     # ── Step 0: clean & normalise ────────────────────────────────────────
#     text = _clean_urdu_text(str(text).replace('\r\n', '\n').replace('\r', '\n'))
#     if not text.strip():
#         return Spacer(1, h_pt)

#     try:
#         fp = _get_urdu_font_path(bold=bold)
#         if not fp:
#             raise RuntimeError("Urdu font file not found.")

#         SCALE  = 3
#         pil_fs = max(10, font_size * SCALE)
#         font   = ImageFont.truetype(fp, pil_fs)

#         # Scratch canvas for measurements
#         _tmp = PILImage.new('RGB', (1, 1))
#         _d   = ImageDraw.Draw(_tmp)

#         def get_pixel_width(raw_text):
#             # FIX: must match what we actually draw — reshape THEN get_display
#             s  = get_display(arabic_reshaper.reshape(raw_text))
#             bb = _d.textbbox((0, 0), s, font=font)
#             return bb[2] - bb[0]

#         canvas_px_w = int(w_pt * SCALE * 2)
#         H_PAD       = int(pil_fs * 0.5)
#         max_line_px = canvas_px_w - (H_PAD * 2)

#         # ── Step 1: wrap raw text into display lines ─────────────────────
#         raw_paras      = text.split('\n')
#         lines_to_render = []   # list of (shaped_str, pixel_width)

#         for para in raw_paras:
#             if not para.strip():
#                 # Preserve blank lines as empty spacer rows
#                 lines_to_render.append(('', 0))
#                 continue

#             words        = para.split()
#             current_line = []

#             for word in words:
#                 test_line = " ".join(current_line + [word])
#                 if get_pixel_width(test_line) <= max_line_px:
#                     current_line.append(word)
#                 else:
#                     if current_line:
#                         raw_str = " ".join(current_line)
#                         # FIX: reshape + get_display — BOTH required
#                         shaped  = get_display(arabic_reshaper.reshape(raw_str))
#                         lines_to_render.append((shaped, get_pixel_width(raw_str)))
#                     current_line = [word]

#             # Last (or only) line of paragraph
#             if current_line:
#                 raw_str = " ".join(current_line)
#                 # FIX: reshape + get_display — BOTH required
#                 shaped  = get_display(arabic_reshaper.reshape(raw_str))
#                 lines_to_render.append((shaped, get_pixel_width(raw_str)))

#         # ── Step 2: compute canvas height ───────────────────────────────
#         line_spacing = int(pil_fs * 1.6)
#         v_pad        = int(pil_fs * 0.5)
#         total_h_px   = (line_spacing * len(lines_to_render)) + (v_pad * 2)
#         final_h_pt   = max(float(h_pt), total_h_px / (SCALE * 2))

#         img  = PILImage.new('RGBA', (canvas_px_w, int(final_h_pt * SCALE * 2)), bg + (255,))
#         draw = ImageDraw.Draw(img)

#         # ── Step 3: draw right-aligned ───────────────────────────────────
#         y_cursor = v_pad
#         for shaped_text, line_w in lines_to_render:
#             if shaped_text:
#                 # FIX: clamp so x never goes negative for short strings
#                 x_pos = max(H_PAD, canvas_px_w - line_w - H_PAD)
#                 draw.text((x_pos, y_cursor), shaped_text, fill=fg + (255,), font=font)
#             y_cursor += line_spacing

#         # ── Step 4: downscale & return ───────────────────────────────────
#         img = img.resize((int(w_pt * 2), int(final_h_pt * 2)), PILImage.LANCZOS)
#         buf = io.BytesIO()
#         img.save(buf, 'PNG')
#         buf.seek(0)
#         return RLImage(buf, width=w_pt, height=final_h_pt)

#     except Exception as e:
#         logger.error(f"_urdu_rl rendering failed: {e}")
#         return Paragraph(str(text), getSampleStyleSheet()['Normal'])


# def _scale_image(png_bytes, target_w, max_h):
#     buf = io.BytesIO(png_bytes)
#     pil = PILImage.open(buf)
#     ow, oh = pil.size
#     w = target_w
#     h = oh * (w / ow)
#     if h > max_h:
#         h = max_h
#         w = ow * (h / oh)
#     return w, h


# def _make_weather_chart(days, width_pt, height_pt):
#     dates    = [d["date"]       for d in days]
#     t_max    = [d["temp_max"]   for d in days]
#     t_min    = [d["temp_min"]   for d in days]
#     humidity = [d["humidity"]   for d in days]
#     wind     = [d["wind_speed"] for d in days]
#     n, x, bw, dpi = len(dates), np.arange(len(dates)), 0.35, 150

#     fig, ax1 = plt.subplots(figsize=(width_pt / 72, height_pt / 72), dpi=dpi)
#     fig.patch.set_facecolor('#FAFFFE')
#     ax1.set_facecolor('#F5FFFE')

#     ax2 = ax1.twinx()
#     ax2.bar(x - bw/2, wind,     width=bw, color='#7E57C2', alpha=0.75, zorder=2)
#     ax2.bar(x + bw/2, humidity, width=bw, color='#4CAF50', alpha=0.75, zorder=2)
#     ax2.set_ylim(0, max(max(wind), max(humidity)) * 5.5)
#     ax2.set_ylabel('Wind Speed (m/s)', fontsize=7, color='#555555')
#     ax2.tick_params(axis='y', labelsize=7)

#     ax3 = ax1.twinx()
#     ax3.spines['right'].set_position(('outward', 38))
#     ax3.set_ylim(0, 100)
#     ax3.set_yticks([0, 20, 40, 60, 80, 100])
#     ax3.tick_params(axis='y', labelsize=6, colors='#555555')
#     ax3.set_ylabel('Humidity (%)', fontsize=6, color='#555555')

#     ax1.plot(x, t_max, color='#E65100', linewidth=2.0, marker='o', markersize=4.5, zorder=5)
#     ax1.plot(x, t_min, color='#1565C0', linewidth=2.0, marker='o', markersize=4.5, zorder=5)
#     ax1.set_ylabel('Temperature (°C)', fontsize=8)
#     ax1.tick_params(axis='y', labelsize=7)
#     ax1.set_ylim(0, 55)
#     ax1.grid(axis='y', linestyle='--', alpha=0.35, zorder=1)
#     ax1.set_xlim(-0.5, n - 0.5)
#     ax1.set_xticks(x)
#     ax1.set_xticklabels(dates, rotation=45, ha='right', fontsize=7)
#     ax1.set_xlabel('Date', fontsize=8)

#     for i, d in enumerate(days):
#         if any(kw in d.get("description", "").lower() for kw in RAIN_KEYWORDS):
#             ax1.axvspan(i - 0.5, i + 0.5, alpha=0.18, color='#2196F3', zorder=0)

#     axw = ax1.twinx()
#     axw.plot(x, wind, color='#7B1FA2', linewidth=1.4, marker='o', markersize=3, alpha=0.85, zorder=4)
#     axw.set_ylim(0, max(wind) * 5.5)
#     axw.axis('off')

#     legend_handles = [
#         Line2D([0],[0], color='#E65100', marker='o', markersize=5, linewidth=2,   label='Max Temp (°C)'),
#         Line2D([0],[0], color='#1565C0', marker='o', markersize=5, linewidth=2,   label='Min Temp (°C)'),
#         Line2D([0],[0], color='#7B1FA2', marker='o', markersize=4, linewidth=1.4, label='Wind (m/s)'),
#         plt.Rectangle((0,0),1,1, color='#4CAF50', alpha=0.75, label='Humidity (%)'),
#         plt.Rectangle((0,0),1,1, color='#2196F3', alpha=0.30, label='Rain Day'),
#     ]
#     ax1.legend(handles=legend_handles, loc='upper center', bbox_to_anchor=(0.5, 1.16),
#                ncol=5, fontsize=7, frameon=True, framealpha=0.9,
#                edgecolor='#CCCCCC', handlelength=1.4)
#     plt.tight_layout(pad=0.8)
#     buf = io.BytesIO()
#     fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
#                 facecolor='#FAFFFE', edgecolor='none')
#     plt.close(fig)
#     buf.seek(0)
#     return buf.getvalue()


# def _get_rainy_days(days):
#     return [d["date"] for d in days
#             if any(kw in d.get("description", "").lower() for kw in RAIN_KEYWORDS)]


# # ══════════════════════════════════════════════════════════════════════════════
# #  PDFGenerator
# # ══════════════════════════════════════════════════════════════════════════════

# class PDFGenerator:

#     def __init__(
#         self,
#         farm,
#         user,
#         recommendation_items: List[RecommendationItem],
#         index_pngs:   Optional[Dict[str, bytes]] = None,
#         stage_info:   Optional[dict]             = None,
#         report_type:  str                        = "farmer",   # "farmer" | "agro"
#         # Legacy compat
#         ndvi_png:     Optional[bytes] = None,
#         kmeans_png:   Optional[bytes] = None,
#         basemap_png:  Optional[bytes] = None,
#         ndvi_stats:   Optional[dict]  = None,
#         weather_data: Optional[dict]  = None,
#         soil_data:    Optional[dict]  = None,
#     ):
#         self.farm                 = farm
#         self.user                 = user
#         self.recommendation_items = recommendation_items
#         self.report_type          = report_type
#         self.is_farmer            = (report_type == "farmer")
#         self.stage_info           = stage_info or {}

#         # ── Build unified index_pngs ──────────────────────────────────────
#         self.index_pngs: Dict[str, bytes] = dict(index_pngs or {})
#         if ndvi_png and "NDVI" not in self.index_pngs:
#             self.index_pngs["NDVI"] = ndvi_png

#         # FARMER: enforce exactly ONE index (the first/primary).
#         if self.is_farmer and len(self.index_pngs) > 1:
#             active       = self.stage_info.get("indices", [])
#             primary_name = (active[0] if active and active[0] in self.index_pngs
#                             else ("NDVI" if "NDVI" in self.index_pngs
#                                   else next(iter(self.index_pngs), None)))
#             if primary_name:
#                 self.index_pngs = {primary_name: self.index_pngs[primary_name]}
#             else:
#                 self.index_pngs = {}

#         self.kmeans_png   = kmeans_png
#         self.basemap_png  = basemap_png
#         self.ndvi_stats   = ndvi_stats or {}
#         self.weather_data = (
#             weather_data if (weather_data or {}).get("days") else DUMMY_WEATHER
#         )
#         self.soil_data = (
#             soil_data
#             if soil_data and any(v is not None for v in soil_data.values())
#             else DUMMY_SOIL
#         )
#         self._init_styles()

#     # ── Styles ─────────────────────────────────────────────────────────────

#     def _init_styles(self):
#         self.S = getSampleStyleSheet()
#         self.S.add(ParagraphStyle(
#             name='UrduBody',
#             fontName='UrduFont',
#             fontSize=12,
#             leading=22,
#             alignment=TA_RIGHT,
#             wordWrap='RTL',
#         ))

#         def a(name, **kw):
#             if name not in self.S:
#                 self.S.add(ParagraphStyle(name=name, **kw))

#         a('TITLE',        fontSize=18, fontName='Helvetica-Bold',
#           alignment=TA_CENTER, textColor=C_NAVY, leading=22, spaceAfter=2)
#         a('SUBTITLE',     fontSize=9,  fontName='Helvetica',
#           alignment=TA_CENTER, textColor=C_DGRAY, leading=12)
#         a('B9',           fontSize=9,  fontName='Helvetica',      leading=12)
#         a('B9B',          fontSize=9,  fontName='Helvetica-Bold', leading=12)
#         a('B9C',          fontSize=9,  fontName='Helvetica-Bold', leading=12, alignment=TA_CENTER)
#         a('B8',           fontSize=8,  fontName='Helvetica',      leading=10)
#         a('B8B',          fontSize=8,  fontName='Helvetica-Bold', leading=10)
#         a('B7',           fontSize=7,  fontName='Helvetica',      leading=9)
#         a('B7G',          fontSize=7,  fontName='Helvetica',      leading=9, textColor=C_DGRAY)
#         a('CAP',          fontSize=8,  fontName='Helvetica-Oblique',
#           alignment=TA_CENTER, textColor=colors.HexColor('#555555'))
#         a('ADVISORY_EN',  fontSize=9,  fontName='Helvetica-Bold',
#           textColor=colors.HexColor('#1565C0'), leading=13)
#         a('ADVISORY_BODY',fontSize=8,  fontName='Helvetica',
#           textColor=colors.HexColor('#333333'), leading=11)

#     # ── Public API ──────────────────────────────────────────────────────────

#     def generate(self) -> bytes:
#         buf = io.BytesIO()
#         doc = SimpleDocTemplate(buf, pagesize=A4,
#             leftMargin=LM, rightMargin=RM,
#             topMargin=0.40*inch, bottomMargin=0.40*inch)
#         story = []

#         # PAGE 1
#         story.extend(self._section_header())
#         story.append(Spacer(1, 8))
#         story.extend(self._section_stage_badge())
#         story.append(Spacer(1, 6))
#         story.extend(self._section_farmer_details())
#         story.append(Spacer(1, 6))
#         story.extend(self._section_farm_map())
#         story.append(Spacer(1, 6))
#         story.extend(self._section_soil())
#         story.append(Spacer(1, 6))
#         story.extend(self._section_weather())
#         story.append(Spacer(1, 4))

#         # PAGE 2
#         story.append(PageBreak())
#         if self.is_farmer:
#             story.extend(self._section_satellite_farmer())
#         else:
#             story.extend(self._section_satellite_agro())
#         story.append(Spacer(1, 7))
#         story.extend(self._section_recommendations())
#         story.extend(self._section_footer())

#         doc.build(story)
#         val = buf.getvalue()
#         buf.close()
#         return val

#     def generate_fallback(self) -> bytes:
#         buf = io.BytesIO()
#         doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=RM,
#             topMargin=0.40*inch, bottomMargin=0.40*inch)
#         story = []
#         story.extend(self._section_header())
#         story.append(Spacer(1, 8))
#         story.extend(self._section_stage_badge())
#         story.append(Spacer(1, 8))
#         story.append(Paragraph(
#             "Report generated with default content due to a processing error.",
#             self.S['B9']))
#         story.extend(self._section_footer())
#         doc.build(story)
#         val = buf.getvalue()
#         buf.close()
#         return val

#     # ── Shared helpers ──────────────────────────────────────────────────────

#     def _banner(self, text, color=None):
#         bg = color or C_MID_GREEN
#         p  = Paragraph(text, ParagraphStyle(
#             '_bn', fontSize=11, fontName='Helvetica-Bold',
#             alignment=TA_CENTER, textColor=C_WHITE, leading=14))
#         t = Table([[p]], colWidths=[CW])
#         t.setStyle(TableStyle([
#             ('BACKGROUND',    (0,0),(-1,-1), bg),
#             ('TOPPADDING',    (0,0),(-1,-1), 6),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 6),
#             ('LEFTPADDING',   (0,0),(-1,-1), 8),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 8),
#         ]))
#         return t

#     def _urdu_banner(self, text):
#         return _urdu_rl(text, w_pt=CW, h_pt=22,
#                         font_size=14, bg=(56, 142, 60), fg=(255, 255, 255))

#     def _logo_image(self, max_h=0.55*inch):
#         if not _os.path.exists(LOGO_PATH):
#             return None
#         try:
#             pil = PILImage.open(LOGO_PATH)
#             ow, oh = pil.size
#             h = max_h
#             w = ow * (h / oh)
#             return RLImage(LOGO_PATH, width=w, height=h)
#         except Exception as e:
#             logger.warning(f"Logo load failed: {e}")
#             return None

#     @staticmethod
#     def _png_to_rl(png_bytes, target_w, max_h=None):
#         buf = io.BytesIO(png_bytes)
#         pil = PILImage.open(buf)
#         ow, oh = pil.size
#         buf.seek(0)
#         w = target_w
#         h = oh * (w / ow)
#         if max_h and h > max_h:
#             h = max_h
#             w = ow * (h / oh)
#         return RLImage(buf, width=w, height=h)

#     def _info_card(self, label, value, label_color=None):
#         bg  = label_color or C_MID_GREEN
#         lbl = ParagraphStyle('_lc', fontSize=7, fontName='Helvetica-Bold',
#                              textColor=C_WHITE, alignment=TA_CENTER)
#         val = ParagraphStyle('_vc', fontSize=9, fontName='Helvetica-Bold',
#                              textColor=C_NAVY,  alignment=TA_CENTER)
#         t = Table([
#             [Paragraph(label.upper(), lbl)],
#             [Paragraph(str(value) if value else "N/A", val)],
#         ], colWidths=[(CW/5) - 2])
#         t.setStyle(TableStyle([
#             ('BACKGROUND',    (0,0),(0,0), bg),
#             ('BACKGROUND',    (0,1),(0,1), C_LGRAY),
#             ('BOX',           (0,0),(-1,-1), 0.5, C_GRAY),
#             ('TOPPADDING',    (0,0),(-1,-1), 3),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 3),
#             ('LEFTPADDING',   (0,0),(-1,-1), 4),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 4),
#         ]))
#         return t

#     def _zone_legend_table(self) -> Table:
#         S    = self.S
#         rows = [[Paragraph("<b>Zone</b>",        S['B8B']),
#                  Paragraph("<b>Colour</b>",      S['B8B']),
#                  Paragraph("<b>Description</b>", S['B8B'])]]
#         for zid in [4, 3, 2, 1]:
#             rows.append([
#                 Paragraph(ZONE_LABELS[zid], S['B8']),
#                 Paragraph("", S['B8']),
#                 Paragraph(ZONE_DESC[zid],   S['B7']),
#             ])
#         zt   = Table(rows, colWidths=[1.35*inch, 0.55*inch, CW - 1.35*inch - 0.55*inch])
#         cmds = [
#             ('BACKGROUND',    (0,0),(-1, 0), C_DARK_GREEN),
#             ('TEXTCOLOR',     (0,0),(-1, 0), C_WHITE),
#             ('FONT',          (0,0),(-1, 0), 'Helvetica-Bold', 8),
#             ('FONT',          (0,1),(-1,-1), 'Helvetica', 7),
#             ('GRID',          (0,0),(-1,-1), 0.4, colors.grey),
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',    (0,0),(-1,-1), 3),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 3),
#             ('LEFTPADDING',   (0,0),(-1,-1), 3),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 3),
#         ]
#         for i, zid in enumerate([4, 3, 2, 1], start=1):
#             cmds.append(('BACKGROUND', (1,i),(1,i), ZONE_COLORS[zid]))
#         zt.setStyle(TableStyle(cmds))
#         return zt

#     # ── SECTION: Header ─────────────────────────────────────────────────────

#     def _section_header(self):
#         S    = self.S
#         logo = self._logo_image(max_h=0.60*inch)
#         report_label = ("Farmer Advisory Report"
#                         if self.is_farmer else "Agronomist Detailed Report")
#         title_cell = [
#             Paragraph("LIMS KISSAN KI PEYCHAN", S['TITLE']),
#             Paragraph(
#                 f"Land Information &amp; Management System – {report_label}",
#                 S['SUBTITLE']),
#         ]
#         date_str  = datetime.now().strftime('%d %B %Y')
#         date_cell = Paragraph(
#             f"<b>Report Date</b><br/>{date_str}",
#             ParagraphStyle('_dt', fontSize=8, fontName='Helvetica',
#                            alignment=TA_RIGHT, textColor=C_DGRAY, leading=11))
#         logo_cell = logo if logo else Paragraph("LIMS", S['B9B'])
#         col_w     = [1.2*inch, CW - 1.2*inch - 1.1*inch, 1.1*inch]
#         header_row = Table([[logo_cell, title_cell, date_cell]], colWidths=col_w)
#         header_row.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#         ]))
#         top_line = HRFlowable(width=CW, thickness=3, color=C_DARK_GREEN,
#                               spaceAfter=6, spaceBefore=0)
#         bot_line = HRFlowable(width=CW, thickness=0.5, color=C_GRAY,
#                               spaceAfter=0, spaceBefore=6)
#         return [top_line, header_row, bot_line]

#     # ── SECTION: Stage badge ────────────────────────────────────────────────

#     def _section_stage_badge(self):
#         S  = self.S
#         si = self.stage_info
#         if not si or not si.get("key"):
#             return [self._banner("&#128200;  Crop stage could not be determined", C_DGRAY)]

#         stage_key   = si["key"]
#         stage_label = si.get("label", "Unknown Stage")
#         days        = si.get("days_since_sowing", 0)
#         day_range   = si.get("day_range", "")
#         indices     = si.get("indices", [])
#         display_indices = indices[:1] if self.is_farmer else indices

#         hex_col     = STAGE_COLORS.get(stage_key, "#1B5E20")
#         stage_color = colors.HexColor(hex_col)
#         report_tag  = "Farmer Advisory" if self.is_farmer else "Agronomist Report"

#         stage_para = Paragraph(
#             f"&#127807; &nbsp;<b>{stage_label}</b>",
#             ParagraphStyle('_sp', fontSize=12, fontName='Helvetica-Bold',
#                            textColor=C_WHITE, leading=16))
#         days_para = Paragraph(
#             f"Day <b>{days}</b> since sowing &nbsp;|&nbsp; Stage window: {day_range}"
#             f" &nbsp;|&nbsp; <i>{report_tag}</i>",
#             ParagraphStyle('_dp', fontSize=8, fontName='Helvetica',
#                            textColor=colors.HexColor('#EEEEEE'), leading=11))
#         left_cell = [stage_para, Spacer(1, 3), days_para]

#         idx_parts = []
#         for idx in display_indices:
#             meta = INDEX_META.get(idx, {"color": "#388E3C"})
#             idx_parts.append(
#                 f'<font color="{meta["color"]}">&#9646;</font> <b>{idx}</b>'
#             )
#         idx_text   = "  |  ".join(idx_parts) if idx_parts else "N/A"
#         label_text = "Index Analysed" if self.is_farmer else "Indices Analysed"
#         right_para = Paragraph(
#             f"<b>{label_text}:</b><br/>{idx_text}",
#             ParagraphStyle('_rp', fontSize=9, fontName='Helvetica',
#                            textColor=C_WHITE, alignment=TA_RIGHT, leading=13))

#         left_w  = CW * 0.65
#         right_w = CW * 0.35
#         badge   = Table([[left_cell, right_para]], colWidths=[left_w, right_w])
#         badge.setStyle(TableStyle([
#             ('BACKGROUND',    (0,0),(-1,-1), stage_color),
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',    (0,0),(-1,-1), 8),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 8),
#             ('LEFTPADDING',   (0,0),(0,-1),  10),
#             ('RIGHTPADDING',  (1,0),(1,-1),  10),
#             ('LEFTPADDING',   (1,0),(1,-1),  4),
#         ]))
#         return [badge]

#     # ── SECTION: Farmer details ─────────────────────────────────────────────

#     def _section_farmer_details(self):
#         S = self.S
#         f = self.farm
#         u = self.user
#         sow = f.sowing_date.strftime('%d %b %Y') if f.sowing_date else 'N/A'
#         cards = [
#             self._info_card("Farmer",       u.username or 'N/A',                    C_NAVY),
#             self._info_card("Contact",      getattr(u, 'mobile_number', '') or 'N/A', C_MID_GREEN),
#             self._info_card("Farm",         f.farm_name or 'N/A',                   C_MID_GREEN),
#             self._info_card("Crop",         str(f.crop) if f.crop else 'N/A',        C_ACCENT),
#             self._info_card("Area (Acres)", f.total_acres or 'N/A',                 C_DARK_GREEN),
#         ]
#         cards2 = [
#             self._info_card("Season",      str(f.crop_season) if f.crop_season else 'N/A',                        C_MID_GREEN),
#             self._info_card("Sowing Date", sow,                                                                    C_MID_GREEN),
#             self._info_card("Location",    f.location  if hasattr(f, 'location')  else 'N/A',                     C_DARK_GREEN),
#             self._info_card("District",    str(f.district) if hasattr(f, 'district') and f.district else 'N/A',   C_DARK_GREEN),
#             self._info_card("Province",    f.province  if hasattr(f, 'province')  else 'N/A',                     C_NAVY),
#         ]
#         gap   = 3
#         col_w = [(CW/5) - gap + gap/5] * 5

#         def _row(cl):
#             t = Table([cl], colWidths=col_w)
#             t.setStyle(TableStyle([
#                 ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#                 ('LEFTPADDING',   (0,0),(-1,-1), gap//2),
#                 ('RIGHTPADDING',  (0,0),(-1,-1), gap//2),
#                 ('TOPPADDING',    (0,0),(-1,-1), 0),
#                 ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ]))
#             return t

#         banner = self._banner("&#127807;  Farm &amp; Farmer Details", C_DARK_GREEN)
#         return [banner, Spacer(1, 4), _row(cards), Spacer(1, 3), _row(cards2)]

#     # ── SECTION: Farm map ───────────────────────────────────────────────────

#     def _section_farm_map(self):
#         if not self.basemap_png:
#             return []
#         S = self.S
#         f = self.farm
#         img_w, _ = _scale_image(self.basemap_png, BASEMAP_TARGET_W, BASEMAP_MAX_H)
#         map_img  = self._png_to_rl(self.basemap_png, img_w, BASEMAP_MAX_H)
#         sow      = f.sowing_date.strftime('%B %d, %Y') if f.sowing_date else 'N/A'
#         si       = self.stage_info
#         info_lines = [
#             f"<b>Farm Name:</b> {f.farm_name or 'N/A'}",
#             f"<b>Crop:</b> {str(f.crop) if f.crop else 'N/A'}",
#             f"<b>Season:</b> {str(f.crop_season) if f.crop_season else 'N/A'}",
#             f"<b>Sowing Date:</b> {sow}",
#             f"<b>Total Area:</b> {f.total_acres or 'N/A'} Acres",
#             f"<b>Current Stage:</b> {si.get('label','N/A')} (Day {si.get('days_since_sowing','—')})",
#         ]
#         ndvi_mean = self.ndvi_stats.get("ndvi_mean") or self.ndvi_stats.get("mean")
#         if ndvi_mean is not None:
#             health = "High" if ndvi_mean >= 0.60 else "Moderate" if ndvi_mean >= 0.35 else "Low"
#             info_lines.append(f"<b>NDVI:</b> {ndvi_mean:.3f} ({health} vegetation)")
#         right_w    = CW - img_w - 0.15*inch
#         info_table = Table([[Paragraph(l, S['B9'])] for l in info_lines], colWidths=[right_w])
#         info_table.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',    (0,0),(-1,-1), 4),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 4),
#             ('LEFTPADDING',   (0,0),(-1,-1), 12),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 4),
#         ]))
#         layout = Table([[map_img, info_table]], colWidths=[img_w, right_w])
#         layout.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ('BOX',           (0,0),(0,0),   0.6, colors.HexColor('#AAAAAA')),
#             ('BACKGROUND',    (1,0),(1,0),   C_LGRAY),
#             ('BOX',           (1,0),(1,0),   0.4, C_GRAY),
#         ]))
#         return [self._banner("&#127759;  Farm Satellite Image", C_DARK_GREEN),
#                 Spacer(1, 4), layout, Spacer(1, 4)]

#     # ── SECTION: Soil ───────────────────────────────────────────────────────

#     def _section_soil(self):
#         sd    = self.soil_data
#         ROW_H = 18
#         CWS   = [0.90*inch, 0.82*inch, 0.82*inch, 0.85*inch, 2.05*inch]
#         banner = self._urdu_banner("زمین کی زرخیزی")

#         def hdr_img(txt, w, bg_rgb, fg=(255, 255, 255), bold=True):
#             return _urdu_rl(txt, w_pt=w, h_pt=ROW_H, font_size=10, bg=bg_rgb, fg=fg, bold=bold)

#         pimana_w = CWS[0] + CWS[1] + CWS[2]
#         sub = Table([[
#             hdr_img("پیمانہ",      pimana_w, (56,  142, 60)),
#             hdr_img("اصل حالت",   CWS[3],   (26,  35,  126)),
#             hdr_img("مٹی کی صحت", CWS[4],   (26,  35,  126)),
#         ]], colWidths=[pimana_w, CWS[3], CWS[4]])
#         sub.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#         ]))
#         col = Table([[
#             hdr_img("خراب",   CWS[0], (183, 28,  28)),
#             hdr_img("مناسب",  CWS[1], (230, 81,  0)),
#             hdr_img("بہترین", CWS[2], (27,  94,  32)),
#             Paragraph("", self.S['B8']),
#             Paragraph("", self.S['B8']),
#         ]], colWidths=CWS)
#         col.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#             ('GRID',          (0,0),(-1,-1), 0.3, C_GRAY),
#         ]))
#         rows = []
#         for (ulbl, key, unit, exc, avg, poor, exc_fn, avg_fn) in SOIL_ROWS:
#             val  = sd.get(key)
#             disp = (f"{val} {unit}".strip() if unit else str(val)) if val is not None else "—"
#             bg   = _soil_bg(val, exc_fn, avg_fn)
#             rows.append([
#                 Paragraph(poor, self.S['B8']),
#                 Paragraph(avg,  self.S['B8']),
#                 Paragraph(exc,  self.S['B8']),
#                 _urdu_rl(disp, CWS[3], ROW_H, font_size=10, bg=_rl2rgb(bg)),
#                 _urdu_rl(ulbl, CWS[4], ROW_H, font_size=10, bg=(245, 245, 245)),
#             ])
#         dt = Table(rows, colWidths=CWS)
#         dt.setStyle(TableStyle([
#             ('GRID',           (0,0),(-1,-1), 0.4, C_GRAY),
#             ('ALIGN',          (0,0),(2,-1),  'CENTER'),
#             ('VALIGN',         (0,0),(-1,-1), 'MIDDLE'),
#             ('TOPPADDING',     (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING',  (0,0),(-1,-1), 0),
#             ('LEFTPADDING',    (0,0),(-1,-1), 2),
#             ('RIGHTPADDING',   (0,0),(-1,-1), 2),
#             ('FONT',           (0,0),(2,-1),  'Helvetica', 8),
#             ('ROWBACKGROUNDS', (0,0),(2,-1),  [C_WHITE, C_LIGHT_GREEN]),
#         ]))
#         return [banner, Spacer(1, 2), sub, col, dt]

#     # ── SECTION: Weather ────────────────────────────────────────────────────

#     def _section_weather(self):
#         S    = self.S
#         days = self.weather_data.get("days", [])
#         city = self.weather_data.get("city", "")
#         lbl  = (f"&#9925;  Weather Forecast – {city}"
#                 if city else "&#9925;  Weather Forecast (16-Day)")
#         chart_png = _make_weather_chart(days, CW, 3.0*inch)
#         elements  = [
#             self._banner(lbl, C_NAVY), Spacer(1, 4),
#             self._png_to_rl(chart_png, CW, max_h=3.0*inch), Spacer(1, 8),
#         ]

#         rainy = _get_rainy_days(days)
#         if rainy:
#             rl = ", ".join(rainy)
#             en = (f"Rain is expected on <b>{rl}</b>. "
#                   "Please avoid fertiliser or pesticide application on this day.")
#             ut = "بارش کے دن: " + "  ،  ".join(rainy)
#             un = "براہ کرم ان دنوں میں کھاد اور کیڑے مار ادویات کا استعمال نہ کریں۔"
#         else:
#             en = "No rainy days forecast in the next 16 days. Ensure adequate irrigation."
#             ut = "اگلے 16 دنوں میں کوئی بارش متوقع نہیں ہے۔"
#             un = "فصلوں کے لیے مناسب آبپاشی کو یقینی بنائیں۔"

#         # English card (left)
#         en_card = Table(
#             [[Paragraph("&#9729; Weather Advisory", S['ADVISORY_EN'])],
#              [Paragraph(en, S['ADVISORY_BODY'])]],
#             colWidths=[CW * 0.50 - 6])
#         en_card.setStyle(TableStyle([
#             ('BACKGROUND',    (0,0),(0,0), colors.HexColor('#E3F2FD')),
#             ('BACKGROUND',    (0,1),(0,1), colors.HexColor('#F8FBFF')),
#             ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#1565C0')),
#             ('TOPPADDING',    (0,0),(-1,-1), 5),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 5),
#             ('LEFTPADDING',   (0,0),(-1,-1), 8),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 8),
#             ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#         ]))

#         # Urdu card (right) — dynamic height via _urdu_rl auto-expand
#         ulb = _urdu_rl("موسم کی ہدایات", w_pt=CW*0.48, h_pt=20, font_size=11,
#                        bg=(245, 127, 17), fg=(255, 255, 255), bold=True)
#         ui1 = _urdu_rl(ut, w_pt=CW*0.48, h_pt=10, font_size=13, bg=(255, 248, 225), fg=(100, 60, 0))
#         ui2 = _urdu_rl(un, w_pt=CW*0.48, h_pt=10, font_size=13, bg=(255, 253, 231), fg=(80,  40, 0))

#         ur_card = Table([[ulb], [ui1], [ui2]], colWidths=[CW*0.50 - 6])
#         ur_card.setStyle(TableStyle([
#             ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#F57F17')),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#             ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#         ]))

#         adv = Table([[en_card, ur_card]], colWidths=[CW*0.50, CW*0.50])
#         adv.setStyle(TableStyle([
#             ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#             ('LEFTPADDING',   (0,0),(-1,-1), 0),
#             ('RIGHTPADDING',  (0,0),(-1,-1), 4),
#             ('TOPPADDING',    (0,0),(-1,-1), 0),
#             ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#         ]))
#         elements.append(adv)
#         return elements

#     # ══════════════════════════════════════════════════════════════════════
#     #  SATELLITE SECTION
#     # ══════════════════════════════════════════════════════════════════════

#     def _section_satellite_farmer(self):
#         S         = self.S
#         stage_lbl = self.stage_info.get("label", "Current Stage")
#         elements  = [
#             self._banner(
#                 f"&#127947;  Satellite Vegetation Analysis – {stage_lbl}",
#                 C_NAVY),
#             Spacer(1, 6),
#         ]

#         ndvi_mean = self.ndvi_stats.get("ndvi_mean") or self.ndvi_stats.get("mean")
#         if ndvi_mean is not None:
#             health = "High" if ndvi_mean >= 0.60 else "Moderate" if ndvi_mean >= 0.35 else "Low"
#             elements.append(Paragraph(
#                 f"<b>Mean NDVI: {ndvi_mean:.3f}</b> – {health} vegetation density", S['B9']))
#             elements.append(Spacer(1, 5))

#         has_index  = bool(self.index_pngs)
#         has_kmeans = bool(self.kmeans_png)

#         if has_index and has_kmeans:
#             GUTTER    = 0.12 * inch
#             cell_w    = (CW - GUTTER) / 2
#             img_max_h = 3.2 * inch

#             idx_name  = next(iter(self.index_pngs))
#             png_bytes = self.index_pngs[idx_name]
#             caption   = INDEX_FARMER_CAPTION.get(idx_name, idx_name)
#             meta      = INDEX_META.get(idx_name, {"color": "#388E3C"})
#             hdr_color = colors.HexColor(meta["color"])

#             hdr_p_left = Paragraph(
#                 f"<b>{caption}</b>",
#                 ParagraphStyle('_fhdr_l', fontSize=9, fontName='Helvetica-Bold',
#                                textColor=C_WHITE, leading=12))
#             img_left  = self._png_to_rl(png_bytes, cell_w - 2, img_max_h)
#             card_left = Table([[hdr_p_left], [img_left]], colWidths=[cell_w])
#             card_left.setStyle(TableStyle([
#                 ('BACKGROUND',    (0,0),(0,0), hdr_color),
#                 ('TOPPADDING',    (0,0),(0,0), 5),
#                 ('BOTTOMPADDING', (0,0),(0,0), 5),
#                 ('LEFTPADDING',   (0,0),(0,0), 8),
#                 ('RIGHTPADDING',  (0,0),(0,0), 8),
#                 ('TOPPADDING',    (0,1),(0,1), 2),
#                 ('BOTTOMPADDING', (0,1),(0,1), 2),
#                 ('LEFTPADDING',   (0,1),(0,1), 1),
#                 ('RIGHTPADDING',  (0,1),(0,1), 1),
#                 ('ALIGN',         (0,1),(0,1), 'CENTER'),
#                 ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
#             ]))

#             hdr_p_right = Paragraph(
#                 "<b>Vegetation Zone Map</b>",
#                 ParagraphStyle('_fhdr_r', fontSize=9, fontName='Helvetica-Bold',
#                                textColor=C_WHITE, leading=12))
#             img_right  = self._png_to_rl(self.kmeans_png, cell_w - 2, img_max_h)
#             card_right = Table([[hdr_p_right], [img_right]], colWidths=[cell_w])
#             card_right.setStyle(TableStyle([
#                 ('BACKGROUND',    (0,0),(0,0), C_DARK_GREEN),
#                 ('TOPPADDING',    (0,0),(0,0), 5),
#                 ('BOTTOMPADDING', (0,0),(0,0), 5),
#                 ('LEFTPADDING',   (0,0),(0,0), 8),
#                 ('RIGHTPADDING',  (0,0),(0,0), 8),
#                 ('TOPPADDING',    (0,1),(0,1), 2),
#                 ('BOTTOMPADDING', (0,1),(0,1), 2),
#                 ('LEFTPADDING',   (0,1),(0,1), 1),
#                 ('RIGHTPADDING',  (0,1),(0,1), 1),
#                 ('ALIGN',         (0,1),(0,1), 'CENTER'),
#                 ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
#             ]))

#             side_by_side = Table(
#                 [[card_left, card_right]],
#                 colWidths=[cell_w, cell_w],
#             )
#             side_by_side.setStyle(TableStyle([
#                 ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#                 ('LEFTPADDING',   (0,0),(-1,-1), 0),
#                 ('RIGHTPADDING',  (0,0),(0,-1),  GUTTER),
#                 ('RIGHTPADDING',  (1,0),(1,-1),  0),
#                 ('TOPPADDING',    (0,0),(-1,-1), 0),
#                 ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ]))
#             elements.append(side_by_side)
#             elements.append(Spacer(1, 4))
#             elements.append(Paragraph(
#                 "Left: Vegetation health index map.  "
#                 "Right: Farm divided into 4 vegetation zones based on satellite data.",
#                 S['CAP']))
#             elements.append(Spacer(1, 6))

#         elif has_index and not has_kmeans:
#             idx_name  = next(iter(self.index_pngs))
#             png_bytes = self.index_pngs[idx_name]
#             caption   = INDEX_FARMER_CAPTION.get(idx_name, idx_name)
#             meta      = INDEX_META.get(idx_name, {"color": "#388E3C"})
#             hdr_color = colors.HexColor(meta["color"])
#             hdr_p = Paragraph(
#                 f"<b>{caption}</b>",
#                 ParagraphStyle('_fhdr', fontSize=10, fontName='Helvetica-Bold',
#                                textColor=C_WHITE, leading=13))
#             img  = self._png_to_rl(png_bytes, CW - 2, NDVI_MAX_H)
#             card = Table([[hdr_p], [img]], colWidths=[CW])
#             card.setStyle(TableStyle([
#                 ('BACKGROUND',    (0,0),(0,0), hdr_color),
#                 ('TOPPADDING',    (0,0),(0,0), 6),
#                 ('BOTTOMPADDING', (0,0),(0,0), 6),
#                 ('LEFTPADDING',   (0,0),(0,0), 10),
#                 ('TOPPADDING',    (0,1),(0,1), 2),
#                 ('BOTTOMPADDING', (0,1),(0,1), 2),
#                 ('LEFTPADDING',   (0,1),(0,1), 1),
#                 ('RIGHTPADDING',  (0,1),(0,1), 1),
#                 ('ALIGN',         (0,1),(0,1), 'CENTER'),
#                 ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
#             ]))
#             elements.append(card)
#             elements.append(Spacer(1, 8))

#         elif not has_index and has_kmeans:
#             elements.append(self._banner(
#                 "&#127919;  Vegetation Zone Map (K-Means Classification)", C_DARK_GREEN))
#             elements.append(Spacer(1, 4))
#             km_img = self._png_to_rl(self.kmeans_png, CW, NDVI_MAX_H)
#             elements.append(km_img)
#             elements.append(Spacer(1, 4))
#             elements.append(Paragraph(
#                 "Farm divided into 4 vegetation health zones based on satellite data.",
#                 S['CAP']))
#             elements.append(Spacer(1, 6))

#         else:
#             elements.append(Paragraph(
#                 "Satellite imagery not available for this stage.", S['B9']))

#         if has_index or has_kmeans:
#             elements.append(self._zone_legend_table())

#         return elements

#     def _section_satellite_agro(self):
#         S         = self.S
#         stage_lbl = self.stage_info.get("label", "Current Stage")
#         indices   = list(self.index_pngs.keys())
#         n         = len(indices)

#         elements = [
#             self._banner(
#                 f"&#127947;  Satellite Vegetation Analysis – {stage_lbl}",
#                 C_NAVY),
#             Spacer(1, 6),
#         ]

#         ndvi_mean = self.ndvi_stats.get("ndvi_mean") or self.ndvi_stats.get("mean")
#         if ndvi_mean is not None:
#             health = "High" if ndvi_mean >= 0.60 else "Moderate" if ndvi_mean >= 0.35 else "Low"
#             elements.append(Paragraph(
#                 f"<b>Mean NDVI: {ndvi_mean:.3f}</b> – {health} vegetation density", S['B9']))
#             elements.append(Spacer(1, 5))

#         if not self.index_pngs:
#             elements.append(Paragraph(
#                 "Satellite imagery not available for this stage.", S['B9']))
#         elif n == 1:
#             idx_name = indices[0]
#             elements.append(self._agro_index_card(idx_name, self.index_pngs[idx_name], CW))
#         else:
#             cell_w = (CW - 0.15*inch) / 2
#             pairs  = [indices[i:i+2] for i in range(0, n, 2)]
#             for pair in pairs:
#                 if len(pair) == 1:
#                     cells  = [self._agro_index_card(pair[0], self.index_pngs[pair[0]], CW)]
#                     widths = [CW]
#                 else:
#                     cells  = [self._agro_index_card(nm, self.index_pngs[nm], cell_w) for nm in pair]
#                     widths = [cell_w] * 2
#                 row = Table([cells], colWidths=widths)
#                 row.setStyle(TableStyle([
#                     ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#                     ('LEFTPADDING',   (0,0),(-1,-1), 0),
#                     ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#                     ('TOPPADDING',    (0,0),(-1,-1), 0),
#                     ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#                 ]))
#                 elements.append(row)
#                 elements.append(Spacer(1, 6))

#         if self.kmeans_png:
#             elements.append(self._banner(
#                 "&#127919;  K-Means Vegetation Zone Classification", C_MID_GREEN))
#             elements.append(Spacer(1, 4))
#             km_w   = CW * 0.62
#             leg_w  = CW * 0.38
#             km_img = self._png_to_rl(self.kmeans_png, km_w, NDVI_MAX_H)
#             km_row = Table([[km_img, self._zone_legend_table()]],
#                            colWidths=[km_w, leg_w])
#             km_row.setStyle(TableStyle([
#                 ('VALIGN',        (0,0),(-1,-1), 'TOP'),
#                 ('LEFTPADDING',   (0,0),(-1,-1), 0),
#                 ('RIGHTPADDING',  (0,0),(-1,-1), 0),
#                 ('TOPPADDING',    (0,0),(-1,-1), 0),
#                 ('BOTTOMPADDING', (0,0),(-1,-1), 0),
#             ]))
#             elements.append(km_row)

#         return elements

#     def _agro_index_card(self, idx_name: str, png_bytes: bytes, target_w: float) -> Table:
#         meta      = INDEX_META.get(idx_name, {"full": idx_name, "color": "#388E3C"})
#         hdr_color = colors.HexColor(meta["color"])
#         full_name = meta["full"]
#         hdr_p = Paragraph(
#             f"<b>{idx_name}</b>  <font size='7'>{full_name}</font>",
#             ParagraphStyle('_ahdr', fontSize=9, fontName='Helvetica-Bold',
#                            textColor=C_WHITE, leading=12))
#         img  = self._png_to_rl(png_bytes, target_w - 2, NDVI_MAX_H)
#         card = Table([[hdr_p], [img]], colWidths=[target_w])
#         card.setStyle(TableStyle([
#             ('BACKGROUND',    (0,0),(0,0), hdr_color),
#             ('TOPPADDING',    (0,0),(0,0), 5),
#             ('BOTTOMPADDING', (0,0),(0,0), 5),
#             ('LEFTPADDING',   (0,0),(0,0), 7),
#             ('RIGHTPADDING',  (0,0),(0,0), 7),
#             ('TOPPADDING',    (0,1),(0,1), 2),
#             ('BOTTOMPADDING', (0,1),(0,1), 2),
#             ('LEFTPADDING',   (0,1),(0,1), 1),
#             ('RIGHTPADDING',  (0,1),(0,1), 1),
#             ('ALIGN',         (0,1),(0,1), 'CENTER'),
#             ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
#         ]))
#         return card

#     # ── SECTION: Recommendations ────────────────────────────────────────────

#     def _section_recommendations(self):
#         S        = self.S
#         si       = self.stage_info
#         elements = [
#             self._banner("&#127807;  Crop Recommendations", C_DARK_GREEN),
#             Spacer(1, 5),
#         ]

#         if si.get("label"):
#             elements.append(Paragraph(
#                 f"<b>Stage:</b> {si['label']}  |  "
#                 f"<b>Day {si.get('days_since_sowing','?')}</b> since sowing  |  "
#                 f"<b>Window:</b> {si.get('day_range','')}",
#                 ParagraphStyle('_rc', fontSize=8, fontName='Helvetica-Oblique',
#                                textColor=colors.HexColor('#555555'), leading=11)))
#             elements.append(Spacer(1, 5))

#         if not self.recommendation_items:
#             elements.append(Paragraph(
#                 "No recommendations available for the current crop stage.", S['B9']))
#             return elements

#         # Group by index
#         grouped: dict = {}
#         for item in self.recommendation_items:
#             grouped.setdefault(item.indice, []).append(item)

#         for indice, items in grouped.items():
#             meta      = INDEX_META.get(indice, {"full": indice, "color": "#388E3C"})
#             idx_color = colors.HexColor(meta["color"])

#             if self.is_farmer:
#                 caption    = INDEX_FARMER_CAPTION.get(indice, indice)
#                 hdr_txt    = f"<b>{caption}</b>"
#                 hdr_bg     = colors.HexColor(meta["color"] + "22")
#                 hdr_border = idx_color
#             else:
#                 hdr_txt    = f"<b>{indice}</b> – {meta['full']}"
#                 hdr_bg     = idx_color
#                 hdr_border = idx_color

#             ht = Table([[Paragraph(
#                 hdr_txt,
#                 ParagraphStyle('_rh', fontSize=9, fontName='Helvetica-Bold',
#                                textColor=C_WHITE if not self.is_farmer else idx_color,
#                                leading=12))
#             ]], colWidths=[CW])
#             ht.setStyle(TableStyle([
#                 ('BACKGROUND',    (0,0),(-1,-1), hdr_bg),
#                 ('BOX',           (0,0),(-1,-1), 0.8, hdr_border),
#                 ('TOPPADDING',    (0,0),(-1,-1), 5),
#                 ('BOTTOMPADDING', (0,0),(-1,-1), 5),
#                 ('LEFTPADDING',   (0,0),(-1,-1), 10),
#                 ('RIGHTPADDING',  (0,0),(-1,-1), 8),
#             ]))

#             group = [ht, Spacer(1, 3)]

#             for item in items:
#                 stage_display = (item.get_crop_stage_display()
#                                  if hasattr(item, 'get_crop_stage_display')
#                                  else item.crop_stage)

#                 group.append(Paragraph(
#                     f"<b>{stage_display}</b>  "
#                     f"<font color='#777777'>({item.duration_in_days} days)</font>",
#                     S['B9B']))
#                 group.append(Spacer(1, 2))

#                 # ── FIX: clean rec_text before passing to _urdu_rl ──────
#                 raw_rec = str(item.recommendation_text) if item.recommendation_text else ""
#                 rec_text = _clean_urdu_text(
#                     raw_rec.replace('\r\n', '\n').replace('\r', '\n').strip()
#                 )

#                 if rec_text:
#                     urdu_img = _urdu_rl(
#                         rec_text,
#                         w_pt=CW - 0.4 * inch,
#                         h_pt=30,        # minimum height; auto-expands as needed
#                         font_size=12,
#                         bg=(250, 250, 250),
#                         fg=(40, 40, 40),
#                     )
#                     group.append(urdu_img)
#                 else:
#                     group.append(Paragraph("No recommendation text available.", S['B9']))

#                 group.append(Spacer(1, 8))

#             elements.append(KeepTogether(group))
#             elements.append(Spacer(1, 6))

#         return elements

#     # ── SECTION: Footer ─────────────────────────────────────────────────────

#     def _section_footer(self):
#         S        = self.S
#         logo     = self._logo_image(max_h=0.30*inch)
#         date_str = datetime.now().strftime('%B %d, %Y at %I:%M %p')
#         rtype    = "Farmer Advisory" if self.is_farmer else "Agronomist Report"
#         logo_cell = logo if logo else Paragraph("LIMS", S['B7'])
#         text_cell = Paragraph(
#             f"<i>Generated by LIMS ({rtype}) on {date_str}</i> &nbsp;|&nbsp; "
#             "<i>Land Information &amp; Management System</i>",
#             ParagraphStyle('_ft', fontSize=7, fontName='Helvetica-Oblique',
#                            textColor=C_DGRAY, alignment=TA_CENTER))
#         footer_row = Table([[logo_cell, text_cell]],
#                            colWidths=[0.7*inch, CW - 0.7*inch])
#         footer_row.setStyle(TableStyle([
#             ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
#             ('LEFTPADDING',  (0,0),(-1,-1), 0),
#             ('RIGHTPADDING', (0,0),(-1,-1), 0),
#         ]))
#         return [
#             Spacer(1, 8),
#             HRFlowable(width=CW, thickness=2, color=C_DARK_GREEN,
#                        spaceAfter=4, spaceBefore=0),
#             footer_row,
#         ]


"""
pdf_generator.py
----------------
Generates PDF reports.  Two report types:

FARMER  ("farmer")
──────────────────
• Stage badge  – shows the ONE active index + "Farmer Advisory" tag
• Farm/farmer cards, basemap, soil table, weather chart
• PAGE 2:
    - Banner: "Satellite Vegetation Analysis – <Stage>"
    - ONE index image full-width  (whichever index the stage requires)
    - K-Means zone map full-width below
    - Zone legend table
    - Crop Recommendations (grouped by that single index)

AGRO  ("agro")
──────────────
• Stage badge  – shows ALL active indices + "Agronomist Report" tag
• Same page-1 content
• PAGE 2:
    - Banner: "Satellite Vegetation Analysis – <Stage>"
    - ALL index images in a 2-up grid  (1 per cell, wrapping rows)
    - K-Means zone map side-by-side with zone legend
    - Crop Recommendations grouped by index with technical sub-headers

The correct indices per stage come from filters.py → STAGE_DEFINITIONS
and are already stored in stage_info["indices"] by the time PDFGenerator
is called. The PDF just honours whatever is in index_pngs.

FIXES APPLIED (Urdu rendering):
  1. _clean_urdu_text() now called at the top of _urdu_rl() — strips emojis,
     \r\n, zero-width chars BEFORE passing to arabic_reshaper.
  2. get_display() (BiDi) re-enabled at draw time and in get_pixel_width() —
     both reshape AND get_display are required for correct RTL visual order.
  3. x_pos clamped to max(H_PAD, ...) so short strings never draw at negative x.
  4. _section_recommendations() pre-cleans rec_text before calling _urdu_rl().
  5. Blank paragraph lines preserved as spacer lines in the wrapping loop.
"""

import io
import logging
import os as _os
from datetime import datetime
from typing import List, Optional, Dict
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from PIL import Image as PILImage, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, Image as RLImage, HRFlowable, PageBreak,
)

from User.models import CustomUser, Farms
from CropsRecomendations.models import RecommendationItem
from django.conf import settings
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# font_path = os.path.join(BASE_DIR, 'fonts', 'NotoNastaliqUrdu-VariableFont_wght.ttf')

# Around Line 519 - Update these lines
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)

# ── Page geometry ──────────────────────────────────────────────────────────
W, H = A4
LM = RM = 0.55 * inch
CW = W - LM - RM

# ── Font registration ──────────────────────────────────────────────────────
# Prefer NotoNastaliqUrdu for proper Urdu Nastaliq ligatures.
# Fall back to Amiri (Arabic) if Nastaliq is unavailable.
_FONTS_DIR = os.path.join(BASE_DIR, 'fonts')
_NASTALIQ  = os.path.join(_FONTS_DIR, 'NotoNastaliqUrdu-VariableFont_wght.ttf')
_AMIRI_R   = os.path.join(_FONTS_DIR, 'Amiri-Regular.ttf')
_AMIRI_B   = os.path.join(_FONTS_DIR, 'Amiri-Bold.ttf')

# Choose font path for ReportLab (used in UrduBody paragraph style)
FONT_PATH = _NASTALIQ if os.path.exists(_NASTALIQ) else _AMIRI_R

try:
    pdfmetrics.registerFont(TTFont('UrduFont', FONT_PATH))
    HAS_URDU_FONT = True
except Exception as e:
    logging.error(f"UrduFont registration failed: {e}")
    HAS_URDU_FONT = False

# ── Brand colours ──────────────────────────────────────────────────────────
C_DARK_GREEN  = colors.HexColor('#1B5E20')
C_MID_GREEN   = colors.HexColor('#388E3C')
C_LIGHT_GREEN = colors.HexColor('#E8F5E9')
C_ACCENT      = colors.HexColor('#F57F17')
C_NAVY        = colors.HexColor('#1A237E')
C_WHITE       = colors.white
C_LGRAY       = colors.HexColor('#F5F5F5')
C_GRAY        = colors.HexColor('#DDDDDD')
C_DGRAY       = colors.HexColor('#888888')
C_GREEN_RAW   = colors.HexColor('#00CC00')
C_YELLOW_RAW  = colors.HexColor('#FFFF00')
C_PURPLE_RAW  = colors.HexColor('#CC00FF')

# ── Index metadata ─────────────────────────────────────────────────────────
INDEX_META: Dict[str, dict] = {
    "NDVI":  {"full": "Normalised Difference Vegetation Index",  "color": "#388E3C"},
    "MSAVI": {"full": "Modified Soil-Adjusted Vegetation Index", "color": "#6A5ACD"},
    "NDRE":  {"full": "Red-Edge Normalised Difference",          "color": "#C0392B"},
    "ReCL":  {"full": "Red-Edge Chlorophyll Index",              "color": "#D4AC0D"},
    "NDMI":  {"full": "Normalised Difference Moisture Index",    "color": "#2980B9"},
}

# Plain-language captions for farmer report (no jargon)
INDEX_FARMER_CAPTION: Dict[str, str] = {
    "NDVI":  "Crop Health Map",
    "MSAVI": "Early Growth Vegetation Map",
    "NDRE":  "Crop Stress Map",
    "ReCL":  "Chlorophyll Content Map",
    "NDMI":  "Crop Water Stress Map",
}

# ── Zone legend ────────────────────────────────────────────────────────────
ZONE_COLORS = {
    4: colors.HexColor('#1E8449'),
    3: colors.HexColor('#A9DFBF'),
    2: colors.HexColor('#F4D03F'),
    1: colors.HexColor('#6C3483'),
}
ZONE_LABELS = {4: "Zone 4 – Good",    3: "Zone 3 – Moderate",
               2: "Zone 2 – Low",     1: "Zone 1 – Poor"}
ZONE_DESC   = {4: "High vegetation density – crop is thriving",
               3: "Moderate vegetation – healthy growth",
               2: "Sparse vegetation – monitor closely",
               1: "Very low / stressed vegetation or bare soil"}

# ── Stage colours ──────────────────────────────────────────────────────────
STAGE_COLORS: Dict[str, str] = {
    "pre_planting_early":     "#4A235A",
    "vegetative_growth":      "#1B5E20",
    "flowering_reproductive": "#B7950B",
    "maturity_pre_harvest":   "#784212",
}

# ── Image sizing ───────────────────────────────────────────────────────────
BASEMAP_TARGET_W = CW * 0.45
BASEMAP_MAX_H    = 2.2 * inch
NDVI_MAX_H       = 3.0 * inch

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE     = _os.path.dirname(_os.path.abspath(__file__))
LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "lims_logo.png")

# ── Soil rows ──────────────────────────────────────────────────────────────
SOIL_ROWS = [
    ("مٹی میں نمکیات کی مقدار", "ec",         "dS/m", "<4",      "4.1-8",    ">8",
     lambda v: v < 4,       lambda v: 4 <= v <= 8),
    ("نامیاتی مادہ (%)",         "om",         "%",    ">1.3",    "0.86-1.3", "<0.86",
     lambda v: v > 1.3,     lambda v: 0.86 <= v <= 1.3),
    ("زمین کی تیزابیت",          "ph",         "",     "6.5-7.5", "7.5-8.5",  ">8.5",
     lambda v: 6.5<=v<=7.5, lambda v: 7.5 < v <= 8.5),
    ("فاسفورس",                  "phosphorus", "ppm",  ">14",     "7-14",     "<7",
     lambda v: v > 14,      lambda v: 7 <= v <= 14),
    ("پوٹاش",                    "potassium",  "ppm",  ">180",    "80-180",   "<80",
     lambda v: v > 180,     lambda v: 80 <= v <= 180),
    ("زنک",                      "zinc",       "ppm",  ">1",      "0.5-1",    "<0.5",
     lambda v: v > 1,       lambda v: 0.5 <= v <= 1),
    ("کاپر",                     "copper",     "ppm",  ">0.2",    "0.1-0.2",  "<0.1",
     lambda v: v > 0.2,     lambda v: 0.1 <= v <= 0.2),
    ("آئرن",                     "iron",       "ppm",  ">4.5",    "2-4.5",    "<2",
     lambda v: v > 4.5,     lambda v: 2 <= v <= 4.5),
    ("میگانیز",                  "manganese",  "ppm",  ">1",      "0.5-1",    "<0.5",
     lambda v: v > 1,       lambda v: 0.5 <= v <= 1),
    ("بوران",                    "boron",      "ppm",  "0.5-1",   "0.2-0.5",  "<0.2",
     lambda v: v > 0.5,     lambda v: 0.2 <= v <= 0.5),
    ("مٹی کی سیرابی",            "saturation", "%",    "46-60%",  "30-45%",   "<20%",
     lambda v: v >= 46,     lambda v: 30 <= v < 46),
]

DUMMY_SOIL = {
    "ec": 2.51, "om": 0.42, "ph": 5.8, "nitrogen": None,
    "phosphorus": 5.8, "potassium": 100, "zinc": 0.53,
    "copper": 2.51, "iron": 4.5, "manganese": 0.6, "boron": 0.5, "saturation": 32,
}
DUMMY_WEATHER = {
    "city": "Farm Location", "country": "PK",
    "days": [
        {"date": "20 Apr", "temp_max": 39.5, "temp_min": 25.0, "humidity": 13, "wind_speed": 3.8, "wind_dir": "NW", "description": "Clear Sky"},
        {"date": "21 Apr", "temp_max": 41.2, "temp_min": 25.0, "humidity": 11, "wind_speed": 4.5, "wind_dir": "N",  "description": "Sunny"},
        {"date": "22 Apr", "temp_max": 43.5, "temp_min": 27.0, "humidity": 9,  "wind_speed": 3.9, "wind_dir": "NE", "description": "Clear Sky"},
        {"date": "23 Apr", "temp_max": 44.5, "temp_min": 27.9, "humidity": 9,  "wind_speed": 5.0, "wind_dir": "N",  "description": "Clear Sky"},
        {"date": "24 Apr", "temp_max": 44.8, "temp_min": 27.5, "humidity": 9,  "wind_speed": 4.8, "wind_dir": "NW", "description": "Sunny"},
        {"date": "25 Apr", "temp_max": 46.5, "temp_min": 30.1, "humidity": 9,  "wind_speed": 5.2, "wind_dir": "NE", "description": "Hot"},
        {"date": "26 Apr", "temp_max": 44.8, "temp_min": 31.2, "humidity": 9,  "wind_speed": 4.6, "wind_dir": "N",  "description": "Clear Sky"},
        {"date": "27 Apr", "temp_max": 44.5, "temp_min": 31.5, "humidity": 9,  "wind_speed": 4.3, "wind_dir": "NW", "description": "Sunny"},
        {"date": "28 Apr", "temp_max": 46.7, "temp_min": 31.5, "humidity": 11, "wind_speed": 5.5, "wind_dir": "NE", "description": "Rainy"},
        {"date": "29 Apr", "temp_max": 45.0, "temp_min": 29.8, "humidity": 11, "wind_speed": 4.8, "wind_dir": "N",  "description": "Rainy"},
        {"date": "30 Apr", "temp_max": 45.0, "temp_min": 29.5, "humidity": 9,  "wind_speed": 4.6, "wind_dir": "NW", "description": "Clear Sky"},
        {"date": "01 May", "temp_max": 41.5, "temp_min": 26.5, "humidity": 19, "wind_speed": 3.8, "wind_dir": "W",  "description": "Partly Cloudy"},
        {"date": "02 May", "temp_max": 41.8, "temp_min": 26.8, "humidity": 21, "wind_speed": 4.2, "wind_dir": "SW", "description": "Partly Cloudy"},
        {"date": "03 May", "temp_max": 42.5, "temp_min": 27.5, "humidity": 21, "wind_speed": 4.0, "wind_dir": "W",  "description": "Rainy"},
        {"date": "04 May", "temp_max": 42.0, "temp_min": 30.0, "humidity": 21, "wind_speed": 3.5, "wind_dir": "NW", "description": "Clear Sky"},
        {"date": "05 May", "temp_max": 44.0, "temp_min": 30.0, "humidity": 17, "wind_speed": 5.5, "wind_dir": "N",  "description": "Hot"},
    ],
}
RAIN_KEYWORDS = {"rain", "rainy", "drizzle", "showers", "thunderstorm",
                 "stormy", "precipitation", "heavy rain", "light rain"}


# ══════════════════════════════════════════════════════════════════════════════
#  Pure helpers
# ══════════════════════════════════════════════════════════════════════════════

def _soil_bg(val, exc_fn, avg_fn):
    if val is None:
        return colors.white
    try:
        v = float(val)
        if exc_fn and exc_fn(v): return C_GREEN_RAW
        if avg_fn and avg_fn(v): return C_YELLOW_RAW
        return C_PURPLE_RAW
    except Exception:
        return colors.white


def _rl2rgb(c):
    return (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def _get_urdu_font_path(bold=False):
    """
    Returns path to best available font for PIL Urdu rendering.

    Priority order:
      1. NotoNastaliqUrdu — Authentic Pakistani Nastaliq script.
         With PIL's Raqm support, this variable font renders perfectly.
      2. Amiri Bold / Regular — Arabic Naskh fallback.
    """
    fonts_dir = os.path.join(BASE_DIR, "fonts")

    # 1. NotoNastaliqUrdu (best for Urdu)
    nastaliq = os.path.join(fonts_dir, "NotoNastaliqUrdu-VariableFont_wght.ttf")
    if os.path.exists(nastaliq):
        logger.info(f"_get_urdu_font_path: using Nastaliq → {nastaliq}")
        return nastaliq

    # 2. Amiri fallback
    amiri = os.path.join(fonts_dir, "Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf")
    if os.path.exists(amiri):
        logger.info(f"_get_urdu_font_path: using Amiri → {amiri}")
        return amiri

    logger.error(f"_get_urdu_font_path: NO FONT FOUND in {fonts_dir}")
    return None

# ── Urdu-configured reshaper (reused across all calls) ────────────────────────
# Must be initialised AFTER _get_urdu_font_path is defined.
# arabic_reshaper >= 3.0 supports 'language': 'Urdu' which enables
# Urdu-specific ligature tables (ے, ں, ڈ, etc.).
try:
    _URDU_RESHAPER = arabic_reshaper.ArabicReshaper({
        'language':        'Urdu',
        'support_ligatures': True,
        'delete_tatweel':  False,
    })
except Exception:
    # Older arabic_reshaper versions may not accept 'language' key.
    _URDU_RESHAPER = arabic_reshaper.ArabicReshaper({'support_ligatures': True})


def _clean_urdu_text(text: str) -> str:
    """
    Strip emojis, smart punctuation, zero-width chars, and
    normalise whitespace.  Must be called BEFORE arabic_reshaper.
    """
    if not text:
        return ""
    # Remove emoji / pictographs
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F9FF"
        "\U00002600-\U000027BF"
        "\U0001FA00-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub('', text)
    # Smart dashes → plain dash
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    # Zero-width / BOM chars
    text = text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
    # Collapse multiple spaces/tabs on one line
    text = re.sub(r'[ \t]+', ' ', text)
    # Collapse 3+ newlines → 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── FIX: complete, corrected _urdu_rl ─────────────────────────────────────
# def _urdu_rl(text, w_pt, h_pt, font_size=10, bg=(245, 245, 245), fg=(0, 0, 0), bold=False):
#     """
#     Render Urdu/Arabic text as a PIL image and return an RLImage flowable.

#     Key invariants (all three must hold together):
#       1. _clean_urdu_text() runs first — removes emojis, \\r\\n, ZWJ etc.
#          that break arabic_reshaper.
#       2. Every string that is drawn goes through:
#              get_display(arabic_reshaper.reshape(s))
#          reshape  → connects letter forms (e.g. ک + ا → کا ligature)
#          get_display → reorders glyphs RTL so PIL's LTR renderer shows
#                        them in the correct reading order.
#       3. get_pixel_width() uses the same two-step transform so that the
#          measured width matches what is actually drawn, keeping line-wrap
#          breaks accurate.
#       4. x_pos is clamped to max(H_PAD, ...) so very short strings never
#          produce a negative coordinate (which PIL silently ignores → blank).
#     """
#     # ── Step 0: clean & normalise ────────────────────────────────────────
#     text = _clean_urdu_text(str(text).replace('\r\n', '\n').replace('\r', '\n'))
#     if not text.strip():
#         return Spacer(1, h_pt)

#     try:
#         fp = _get_urdu_font_path(bold=bold)
#         if not fp:
#             raise RuntimeError("Urdu font file not found.")

#         SCALE  = 3
#         pil_fs = max(10, font_size * SCALE)
#         font   = ImageFont.truetype(fp, pil_fs)

#         # Scratch canvas for measurements
#         _tmp = PILImage.new('RGB', (1, 1))
#         _d   = ImageDraw.Draw(_tmp)

#         def get_pixel_width(raw_text):
#             # FIX: must match what we actually draw — reshape THEN get_display
#             # s  = get_display(arabic_reshaper.reshape(raw_text))
#             reshaped = arabic_reshaper.reshape(raw_text)
#             display_text = get_display(reshaped)
#             bb = _d.textbbox((0, 0), display_text, font=font)
#             return bb[2] - bb[0]
#             # reshaped = arabic_reshaper.reshape(raw_text)
#             # display_text = get_display(reshaped)
#             # bb = _d.textbbox((0, 0), display_text, font=font)
#             # return bb[2] - bb[0]

#         canvas_px_w = int(w_pt * SCALE * 2)
#         H_PAD       = int(pil_fs * 0.5)
#         max_line_px = canvas_px_w - (H_PAD * 2)

#         # ── Step 1: wrap raw text into display lines ─────────────────────
#         raw_paras      = text.split('\n')
#         lines_to_render = []   # list of (shaped_str, pixel_width)

#         for para in raw_paras:
#             if not para.strip():
#                 # Preserve blank lines as empty spacer rows
#                 lines_to_render.append(('', 0))
#                 continue

#             words        = para.split()
#             current_line = []

#             for word in words:
#                 test_line = " ".join(current_line + [word])
#                 if get_pixel_width(test_line) <= max_line_px:
#                     current_line.append(word)
#                 else:
#                     if current_line:
#                         raw_str = " ".join(current_line)
#                         # FIX: reshape + get_display — BOTH required
#                         shaped  = get_display(arabic_reshaper.reshape(raw_str))
#                         lines_to_render.append((shaped, get_pixel_width(raw_str)))
#                     current_line = [word]

#             # Last (or only) line of paragraph
#             if current_line:
#                 raw_str = " ".join(current_line)
#                 # FIX: reshape + get_display — BOTH required
#                 shaped  = get_display(arabic_reshaper.reshape(raw_str))
#                 lines_to_render.append((shaped, get_pixel_width(raw_str)))

#         # ── Step 2: compute canvas height ───────────────────────────────
#         line_spacing = int(pil_fs * 1.6)
#         v_pad        = int(pil_fs * 0.5)
#         total_h_px   = (line_spacing * len(lines_to_render)) + (v_pad * 2)
#         final_h_pt   = max(float(h_pt), total_h_px / (SCALE * 2))

#         img  = PILImage.new('RGBA', (canvas_px_w, int(final_h_pt * SCALE * 2)), bg + (255,))
#         draw = ImageDraw.Draw(img)

#         # ── Step 3: draw right-aligned ───────────────────────────────────
#         y_cursor = v_pad
#         for shaped_text, line_w in lines_to_render:
#             if shaped_text:
#         # Instead of manual x_pos calculation, use a safer margin
#         # Ensure the canvas_px_w is wide enough to prevent clipping
#                 x_pos = canvas_px_w - line_w - (H_PAD * 2) 
#                 if x_pos < 0: x_pos = H_PAD
                
#                 draw.text((x_pos, y_cursor), shaped_text, fill=fg + (255,), font=font)
#             # if shaped_text:
#             #     # FIX: clamp so x never goes negative for short strings
#             #     x_pos = max(H_PAD, canvas_px_w - line_w - H_PAD)
#             #     draw.text((x_pos, y_cursor), shaped_text, fill=fg + (255,), font=font)
#             y_cursor += line_spacing

#         # ── Step 4: downscale & return ───────────────────────────────────
#         img = img.resize((int(w_pt * 2), int(final_h_pt * 2)), PILImage.LANCZOS)
#         buf = io.BytesIO()
#         img.save(buf, 'PNG')
#         buf.seek(0)
#         return RLImage(buf, width=w_pt, height=final_h_pt)

#     except Exception as e:
#         logger.error(f"_urdu_rl rendering failed: {e}")
#         return Paragraph(str(text), getSampleStyleSheet()['Normal'])

def _urdu_rl(text, w_pt, h_pt, font_size=10, bg=(245, 245, 245), fg=(0, 0, 0), bold=False):
    """
    Render Urdu text as a PIL image and return a ReportLab RLImage flowable.

    This version uses PIL's Raqm support (Complex Text Layout) for correct
    shaping (ligatures) and BiDi (RTL order).

    Requirements:
    1. libraqm must be installed (checked via PIL.features.check('raqm')).
    2. NotoNastaliqUrdu is preferred for authentic Urdu script.
    """
    # Step 0: clean & normalise
    text = _clean_urdu_text(str(text).replace("\r\n", "\n").replace("\r", "\n"))
    if not text.strip():
        return Spacer(1, h_pt)

    try:
        from PIL import features
        has_raqm = features.check('raqm')

        fp = _get_urdu_font_path(bold=bold)
        if not fp:
            raise RuntimeError("Urdu font file not found.")

        is_nastaliq = "NotoNastaliq" in fp or "nastaliq" in fp.lower()

        SCALE  = 4
        pil_fs = max(12, font_size * SCALE)
        font   = ImageFont.truetype(fp, pil_fs)

        _tmp = PILImage.new("RGB", (1, 1))
        _d   = ImageDraw.Draw(_tmp)

        # ── Pipeline Setup ────────────────────────────────────────────────
        if has_raqm:
            # BEST: Use Raqm for native shaping and bidi
            def _prepare(raw: str) -> str:
                return raw

            def get_pixel_width(s: str) -> int:
                if not s: return 0
                bb = _d.textbbox((0, 0), s, font=font, direction='rtl')
                return bb[2] - bb[0]
        else:
            # FALLBACK: Use reshaper + bidi (works for Naskh/Amiri, not Nastaliq)
            def _prepare(raw: str) -> str:
                return get_display(_URDU_RESHAPER.reshape(raw))

            def get_pixel_width(s: str) -> int:
                if not s: return 0
                bb = _d.textbbox((0, 0), _prepare(s), font=font)
                return bb[2] - bb[0]

        canvas_px_w = int(w_pt * SCALE * 2)
        H_PAD       = int(pil_fs * 0.6)
        max_line_px = canvas_px_w - (H_PAD * 2)

        # Step 1: word-wrap into lines
        raw_paras       = text.split("\n")
        lines_to_render = []

        for para in raw_paras:
            para = para.strip()
            if not para:
                lines_to_render.append(("", 0))
                continue

            words        = para.split()
            current_line = []

            for word in words:
                candidate = " ".join(current_line + [word])
                if get_pixel_width(candidate) <= max_line_px:
                    current_line.append(word)
                else:
                    if current_line:
                        raw_str = " ".join(current_line)
                        lines_to_render.append((_prepare(raw_str), get_pixel_width(raw_str)))
                    current_line = [word]

            if current_line:
                raw_str = " ".join(current_line)
                lines_to_render.append((_prepare(raw_str), get_pixel_width(raw_str)))

        # Step 2: canvas height
        line_spacing = int(pil_fs * (1.9 if is_nastaliq else 1.7))
        v_pad        = int(pil_fs * 0.6)
        total_h_px   = (line_spacing * len(lines_to_render)) + (v_pad * 2)
        final_h_pt   = max(float(h_pt), total_h_px / (SCALE * 2))

        img  = PILImage.new("RGBA", (canvas_px_w, int(final_h_pt * SCALE * 2)), bg + (255,))
        draw = ImageDraw.Draw(img)

        # Step 3: draw lines (right-aligned)
        y_cursor = v_pad
        for display_text, line_w in lines_to_render:
            if display_text:
                x_pos = max(H_PAD, canvas_px_w - line_w - H_PAD)
                if has_raqm:
                    draw.text((x_pos, y_cursor), display_text, fill=fg + (255,), font=font, direction='rtl')
                else:
                    draw.text((x_pos, y_cursor), display_text, fill=fg + (255,), font=font)
            y_cursor += line_spacing

        # Step 4: downscale & return
        img = img.resize((int(w_pt * 2), int(final_h_pt * 2)), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        return RLImage(buf, width=w_pt, height=final_h_pt)

    except Exception as e:
        logger.error(f"_urdu_rl rendering failed: {e}")
        return Paragraph(str(text), getSampleStyleSheet()["Normal"])

def _scale_image(png_bytes, target_w, max_h):
    buf = io.BytesIO(png_bytes)
    pil = PILImage.open(buf)
    ow, oh = pil.size
    w = target_w
    h = oh * (w / ow)
    if h > max_h:
        h = max_h
        w = ow * (h / oh)
    return w, h


def _make_weather_chart(days, width_pt, height_pt):
    dates    = [d["date"]       for d in days]
    t_max    = [d["temp_max"]   for d in days]
    t_min    = [d["temp_min"]   for d in days]
    humidity = [d["humidity"]   for d in days]
    wind     = [d["wind_speed"] for d in days]
    n, x, bw, dpi = len(dates), np.arange(len(dates)), 0.35, 150

    fig, ax1 = plt.subplots(figsize=(width_pt / 72, height_pt / 72), dpi=dpi)
    fig.patch.set_facecolor('#FAFFFE')
    ax1.set_facecolor('#F5FFFE')

    ax2 = ax1.twinx()
    ax2.bar(x - bw/2, wind,     width=bw, color='#7E57C2', alpha=0.75, zorder=2)
    ax2.bar(x + bw/2, humidity, width=bw, color='#4CAF50', alpha=0.75, zorder=2)
    ax2.set_ylim(0, max(max(wind), max(humidity)) * 5.5)
    ax2.set_ylabel('Wind Speed (m/s)', fontsize=7, color='#555555')
    ax2.tick_params(axis='y', labelsize=7)

    ax3 = ax1.twinx()
    ax3.spines['right'].set_position(('outward', 38))
    ax3.set_ylim(0, 100)
    ax3.set_yticks([0, 20, 40, 60, 80, 100])
    ax3.tick_params(axis='y', labelsize=6, colors='#555555')
    ax3.set_ylabel('Humidity (%)', fontsize=6, color='#555555')

    ax1.plot(x, t_max, color='#E65100', linewidth=2.0, marker='o', markersize=4.5, zorder=5)
    ax1.plot(x, t_min, color='#1565C0', linewidth=2.0, marker='o', markersize=4.5, zorder=5)
    ax1.set_ylabel('Temperature (°C)', fontsize=8)
    ax1.tick_params(axis='y', labelsize=7)
    ax1.set_ylim(0, 55)
    ax1.grid(axis='y', linestyle='--', alpha=0.35, zorder=1)
    ax1.set_xlim(-0.5, n - 0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(dates, rotation=45, ha='right', fontsize=7)
    ax1.set_xlabel('Date', fontsize=8)

    for i, d in enumerate(days):
        if any(kw in d.get("description", "").lower() for kw in RAIN_KEYWORDS):
            ax1.axvspan(i - 0.5, i + 0.5, alpha=0.18, color='#2196F3', zorder=0)

    axw = ax1.twinx()
    axw.plot(x, wind, color='#7B1FA2', linewidth=1.4, marker='o', markersize=3, alpha=0.85, zorder=4)
    axw.set_ylim(0, max(wind) * 5.5)
    axw.axis('off')

    legend_handles = [
        Line2D([0],[0], color='#E65100', marker='o', markersize=5, linewidth=2,   label='Max Temp (°C)'),
        Line2D([0],[0], color='#1565C0', marker='o', markersize=5, linewidth=2,   label='Min Temp (°C)'),
        Line2D([0],[0], color='#7B1FA2', marker='o', markersize=4, linewidth=1.4, label='Wind (m/s)'),
        plt.Rectangle((0,0),1,1, color='#4CAF50', alpha=0.75, label='Humidity (%)'),
        plt.Rectangle((0,0),1,1, color='#2196F3', alpha=0.30, label='Rain Day'),
    ]
    ax1.legend(handles=legend_handles, loc='upper center', bbox_to_anchor=(0.5, 1.16),
               ncol=5, fontsize=7, frameon=True, framealpha=0.9,
               edgecolor='#CCCCCC', handlelength=1.4)
    plt.tight_layout(pad=0.8)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='#FAFFFE', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _get_rainy_days(days):
    return [d["date"] for d in days
            if any(kw in d.get("description", "").lower() for kw in RAIN_KEYWORDS)]


# ══════════════════════════════════════════════════════════════════════════════
#  PDFGenerator
# ══════════════════════════════════════════════════════════════════════════════

class PDFGenerator:

    def __init__(
        self,
        farm,
        user,
        recommendation_items: List[RecommendationItem],
        index_pngs:   Optional[Dict[str, bytes]] = None,
        stage_info:   Optional[dict]             = None,
        report_type:  str                        = "farmer",   # "farmer" | "agro"
        zone_acres:   Optional[Dict[int, float]] = None,       # {1: 2.3, 2: 5.1, ...}
        # Legacy compat
        ndvi_png:     Optional[bytes] = None,
        kmeans_png:   Optional[bytes] = None,
        basemap_png:  Optional[bytes] = None,
        ndvi_stats:   Optional[dict]  = None,
        weather_data: Optional[dict]  = None,
        soil_data:    Optional[dict]  = None,
    ):
        self.farm                 = farm
        self.user                 = user
        self.recommendation_items = recommendation_items
        self.report_type          = report_type
        self.is_farmer            = (report_type == "farmer")
        self.stage_info           = stage_info or {}
        self.zone_acres: Dict[int, float] = zone_acres or {}

        # ── Build unified index_pngs ──────────────────────────────────────
        self.index_pngs: Dict[str, bytes] = dict(index_pngs or {})
        if ndvi_png and "NDVI" not in self.index_pngs:
            self.index_pngs["NDVI"] = ndvi_png

        # FARMER: enforce exactly ONE index (the first/primary).
        if self.is_farmer and len(self.index_pngs) > 1:
            active       = self.stage_info.get("indices", [])
            primary_name = (active[0] if active and active[0] in self.index_pngs
                            else ("NDVI" if "NDVI" in self.index_pngs
                                  else next(iter(self.index_pngs), None)))
            if primary_name:
                self.index_pngs = {primary_name: self.index_pngs[primary_name]}
            else:
                self.index_pngs = {}

        self.kmeans_png   = kmeans_png
        self.basemap_png  = basemap_png
        self.ndvi_stats   = ndvi_stats or {}
        self.weather_data = (
            weather_data if (weather_data or {}).get("days") else DUMMY_WEATHER
        )
        self.soil_data = (
            soil_data
            if soil_data and any(v is not None for v in soil_data.values())
            else DUMMY_SOIL
        )
        self._init_styles()

    # ── Styles ─────────────────────────────────────────────────────────────

    def _init_styles(self):
        self.S = getSampleStyleSheet()
        self.S.add(ParagraphStyle(
            name='UrduBody',
            fontName='UrduFont',
            fontSize=12,
            leading=22,
            alignment=TA_RIGHT,
            wordWrap='RTL',
        ))

        def a(name, **kw):
            if name not in self.S:
                self.S.add(ParagraphStyle(name=name, **kw))

        a('TITLE',        fontSize=18, fontName='Helvetica-Bold',
          alignment=TA_CENTER, textColor=C_NAVY, leading=22, spaceAfter=2)
        a('SUBTITLE',     fontSize=9,  fontName='Helvetica',
          alignment=TA_CENTER, textColor=C_DGRAY, leading=12)
        a('B9',           fontSize=9,  fontName='Helvetica',      leading=12)
        a('B9B',          fontSize=9,  fontName='Helvetica-Bold', leading=12)
        a('B9C',          fontSize=9,  fontName='Helvetica-Bold', leading=12, alignment=TA_CENTER)
        a('B8',           fontSize=8,  fontName='Helvetica',      leading=10)
        a('B8B',          fontSize=8,  fontName='Helvetica-Bold', leading=10)
        a('B7',           fontSize=7,  fontName='Helvetica',      leading=9)
        a('B7G',          fontSize=7,  fontName='Helvetica',      leading=9, textColor=C_DGRAY)
        a('CAP',          fontSize=8,  fontName='Helvetica-Oblique',
          alignment=TA_CENTER, textColor=colors.HexColor('#555555'))
        a('ADVISORY_EN',  fontSize=9,  fontName='Helvetica-Bold',
          textColor=colors.HexColor('#1565C0'), leading=13)
        a('ADVISORY_BODY',fontSize=8,  fontName='Helvetica',
          textColor=colors.HexColor('#333333'), leading=11)

    # ── Public API ──────────────────────────────────────────────────────────

    def generate(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
            leftMargin=LM, rightMargin=RM,
            topMargin=0.40*inch, bottomMargin=0.40*inch)
        story = []

        # PAGE 1
        story.extend(self._section_header())
        story.append(Spacer(1, 8))
        story.extend(self._section_stage_badge())
        story.append(Spacer(1, 6))
        story.extend(self._section_farmer_details())
        story.append(Spacer(1, 6))
        story.extend(self._section_map_and_soil())
        story.append(Spacer(1, 6))
        story.extend(self._section_weather())
        story.append(Spacer(1, 4))

        # PAGE 2
        story.append(PageBreak())
        if self.is_farmer:
            story.extend(self._section_satellite_farmer())
        else:
            story.extend(self._section_satellite_agro())
        story.append(Spacer(1, 7))
        story.extend(self._section_recommendations())
        story.extend(self._section_footer())

        doc.build(story)
        val = buf.getvalue()
        buf.close()
        return val

    def generate_fallback(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=RM,
            topMargin=0.40*inch, bottomMargin=0.40*inch)
        story = []
        story.extend(self._section_header())
        story.append(Spacer(1, 8))
        story.extend(self._section_stage_badge())
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "Report generated with default content due to a processing error.",
            self.S['B9']))
        story.extend(self._section_footer())
        doc.build(story)
        val = buf.getvalue()
        buf.close()
        return val

    # ── Shared helpers ──────────────────────────────────────────────────────

    def _banner(self, text, color=None):
        bg = color or C_MID_GREEN
        p  = Paragraph(text, ParagraphStyle(
            '_bn', fontSize=11, fontName='Helvetica-Bold',
            alignment=TA_CENTER, textColor=C_WHITE, leading=14))
        t = Table([[p]], colWidths=[CW])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), bg),
            ('TOPPADDING',    (0,0),(-1,-1), 6),
            ('BOTTOMPADDING', (0,0),(-1,-1), 6),
            ('LEFTPADDING',   (0,0),(-1,-1), 8),
            ('RIGHTPADDING',  (0,0),(-1,-1), 8),
        ]))
        return t

    def _urdu_banner(self, text):
        return _urdu_rl(text, w_pt=CW, h_pt=22,
                        font_size=14, bg=(56, 142, 60), fg=(255, 255, 255))

    def _logo_image(self, max_h=0.55*inch):
        if not _os.path.exists(LOGO_PATH):
            return None
        try:
            pil = PILImage.open(LOGO_PATH)
            ow, oh = pil.size
            h = max_h
            w = ow * (h / oh)
            return RLImage(LOGO_PATH, width=w, height=h)
        except Exception as e:
            logger.warning(f"Logo load failed: {e}")
            return None

    @staticmethod
    def _png_to_rl(png_bytes, target_w, max_h=None):
        buf = io.BytesIO(png_bytes)
        pil = PILImage.open(buf)
        ow, oh = pil.size
        buf.seek(0)
        w = target_w
        h = oh * (w / ow)
        if max_h and h > max_h:
            h = max_h
            w = ow * (h / oh)
        return RLImage(buf, width=w, height=h)

    def _info_card(self, label, value, label_color=None):
        bg  = label_color or C_MID_GREEN
        lbl = ParagraphStyle('_lc', fontSize=7, fontName='Helvetica-Bold',
                             textColor=C_WHITE, alignment=TA_CENTER)
        val = ParagraphStyle('_vc', fontSize=9, fontName='Helvetica-Bold',
                             textColor=C_NAVY,  alignment=TA_CENTER)
        t = Table([
            [Paragraph(label.upper(), lbl)],
            [Paragraph(str(value) if value else "N/A", val)],
        ], colWidths=[(CW/5) - 2])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,0), bg),
            ('BACKGROUND',    (0,1),(0,1), C_LGRAY),
            ('BOX',           (0,0),(-1,-1), 0.5, C_GRAY),
            ('TOPPADDING',    (0,0),(-1,-1), 3),
            ('BOTTOMPADDING', (0,0),(-1,-1), 3),
            ('LEFTPADDING',   (0,0),(-1,-1), 4),
            ('RIGHTPADDING',  (0,0),(-1,-1), 4),
        ]))
        return t

    def _zone_legend_table(self) -> Table:
        """
        ONE horizontal legend line:
        ■ Zone 1 – Poor  ■ Zone 2 – Low  ■ Zone 3 – Moderate  ■ Zone 4 – Good
        """
        cell_w = CW / 4
        cells  = []
        widths = []
        for zid in [1, 2, 3, 4]:
            zc     = ZONE_COLORS[zid]
            swatch = Table([[""]], colWidths=[0.18*inch], rowHeights=[0.18*inch])
            swatch.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(-1,-1), zc),
                ('TOPPADDING',    (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
                ('LEFTPADDING',   (0,0),(-1,-1), 0),
                ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ]))
            lbl = Paragraph(
                f"<b>{ZONE_LABELS[zid]}</b>",
                ParagraphStyle(f'_zl{zid}', fontSize=7, fontName='Helvetica-Bold',
                               textColor=colors.HexColor('#333333'), leading=9))
            inner = Table([[swatch, lbl]], colWidths=[0.22*inch, cell_w - 0.22*inch])
            inner.setStyle(TableStyle([
                ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
                ('LEFTPADDING',  (0,0),(-1,-1), 2),
                ('RIGHTPADDING', (0,0),(-1,-1), 2),
                ('TOPPADDING',   (0,0),(-1,-1), 0),
                ('BOTTOMPADDING',(0,0),(-1,-1), 0),
            ]))
            cells.append(inner)
            widths.append(cell_w)
        row = Table([cells], colWidths=widths)
        row.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), colors.HexColor('#F5F5F5')),
            ('BOX',           (0,0),(-1,-1), 0.5, C_GRAY),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0),(-1,-1), 4),
            ('BOTTOMPADDING', (0,0),(-1,-1), 4),
            ('LEFTPADDING',   (0,0),(-1,-1), 4),
            ('RIGHTPADDING',  (0,0),(-1,-1), 4),
        ]))
        return row

    def _zone_acres_row(self):
        """
        One-line coloured bar: zone colour + area in acres.
        Returns None if zone_acres not available.
        """
        if not self.zone_acres:
            return None
        cell_w = CW / 4
        cells  = []
        widths = []
        for zid in [1, 2, 3, 4]:
            ac  = self.zone_acres.get(zid, self.zone_acres.get(str(zid), 0.0))
            zc  = ZONE_COLORS[zid]
            lbl = Paragraph(
                f"<b>{ac:.1f} Acres</b>",
                ParagraphStyle(f'_za{zid}', fontSize=7, fontName='Helvetica-Bold',
                               textColor=C_WHITE, alignment=TA_CENTER, leading=10))
            cell = Table([[lbl]], colWidths=[cell_w - 4])
            cell.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(-1,-1), zc),
                ('TOPPADDING',    (0,0),(-1,-1), 3),
                ('BOTTOMPADDING', (0,0),(-1,-1), 3),
                ('LEFTPADDING',   (0,0),(-1,-1), 4),
                ('RIGHTPADDING',  (0,0),(-1,-1), 4),
            ]))
            cells.append(cell)
            widths.append(cell_w)
        row = Table([cells], colWidths=widths)
        row.setStyle(TableStyle([
            ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
            ('LEFTPADDING',  (0,0),(-1,-1), 2),
            ('RIGHTPADDING', (0,0),(-1,-1), 2),
            ('TOPPADDING',   (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1), 0),
        ]))
        return row

    # ── SECTION: Header ─────────────────────────────────────────────────────

    def _section_header(self):
        S    = self.S
        logo = self._logo_image(max_h=0.60*inch)
        report_label = ("Farmer Advisory Report"
                        if self.is_farmer else "Agronomist Detailed Report")
        title_cell = [
            Paragraph("LIMS KISSAN KI PEYCHAN", S['TITLE']),
            Paragraph(
                f"Land Information &amp; Management System – {report_label}",
                S['SUBTITLE']),
        ]
        date_str  = datetime.now().strftime('%d %B %Y')
        date_cell = Paragraph(
            f"<b>Report Date</b><br/>{date_str}",
            ParagraphStyle('_dt', fontSize=8, fontName='Helvetica',
                           alignment=TA_RIGHT, textColor=C_DGRAY, leading=11))
        logo_cell = logo if logo else Paragraph("LIMS", S['B9B'])
        col_w     = [1.2*inch, CW - 1.2*inch - 1.1*inch, 1.1*inch]
        header_row = Table([[logo_cell, title_cell, date_cell]], colWidths=col_w)
        header_row.setStyle(TableStyle([
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('LEFTPADDING',   (0,0),(-1,-1), 0),
            ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ]))
        top_line = HRFlowable(width=CW, thickness=3, color=C_DARK_GREEN,
                              spaceAfter=6, spaceBefore=0)
        bot_line = HRFlowable(width=CW, thickness=0.5, color=C_GRAY,
                              spaceAfter=0, spaceBefore=6)
        return [top_line, header_row, bot_line]

    # ── SECTION: Stage badge ────────────────────────────────────────────────

    def _section_stage_badge(self):
        S  = self.S
        si = self.stage_info
        if not si or not si.get("key"):
            return [self._banner("&#128200;  Crop stage could not be determined", C_DGRAY)]

        stage_key   = si["key"]
        stage_label = si.get("label", "Unknown Stage")
        days        = si.get("days_since_sowing", 0)
        day_range   = si.get("day_range", "")
        indices     = si.get("indices", [])
        display_indices = indices[:1] if self.is_farmer else indices

        hex_col     = STAGE_COLORS.get(stage_key, "#1B5E20")
        stage_color = colors.HexColor(hex_col)
        report_tag  = "Farmer Advisory" if self.is_farmer else "Agronomist Report"

        stage_para = Paragraph(
            f"&#127807; &nbsp;<b>{stage_label}</b>",
            ParagraphStyle('_sp', fontSize=12, fontName='Helvetica-Bold',
                           textColor=C_WHITE, leading=16))
        days_para = Paragraph(
            f"Day <b>{days}</b> since sowing &nbsp;|&nbsp; Stage window: {day_range}"
            f" &nbsp;|&nbsp; <i>{report_tag}</i>",
            ParagraphStyle('_dp', fontSize=8, fontName='Helvetica',
                           textColor=colors.HexColor('#EEEEEE'), leading=11))
        left_cell = [stage_para, Spacer(1, 3), days_para]

        idx_parts = []
        for idx in display_indices:
            meta = INDEX_META.get(idx, {"color": "#388E3C"})
            idx_parts.append(
                f'<font color="{meta["color"]}">&#9646;</font> <b>{idx}</b>'
            )
        idx_text   = "  |  ".join(idx_parts) if idx_parts else "N/A"
        label_text = "Index Analysed" if self.is_farmer else "Indices Analysed"
        right_para = Paragraph(
            f"<b>{label_text}:</b><br/>{idx_text}",
            ParagraphStyle('_rp', fontSize=9, fontName='Helvetica',
                           textColor=C_WHITE, alignment=TA_RIGHT, leading=13))

        left_w  = CW * 0.65
        right_w = CW * 0.35
        badge   = Table([[left_cell, right_para]], colWidths=[left_w, right_w])
        badge.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), stage_color),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0),(-1,-1), 8),
            ('BOTTOMPADDING', (0,0),(-1,-1), 8),
            ('LEFTPADDING',   (0,0),(0,-1),  10),
            ('RIGHTPADDING',  (1,0),(1,-1),  10),
            ('LEFTPADDING',   (1,0),(1,-1),  4),
        ]))
        return [badge]

    # ── SECTION: Farmer details ─────────────────────────────────────────────

    def _section_farmer_details(self):
        S = self.S
        f = self.farm
        u = self.user
        sow = f.sowing_date.strftime('%d %b %Y') if f.sowing_date else 'N/A'
        cards = [
            self._info_card("Farmer",       u.username or 'N/A',                    C_NAVY),
            self._info_card("Contact",      getattr(u, 'mobile_number', '') or 'N/A', C_MID_GREEN),
            self._info_card("Farm",         f.farm_name or 'N/A',                   C_MID_GREEN),
            self._info_card("Crop",         (f.crop.name if hasattr(f.crop, 'name') else str(f.crop)) if f.crop else 'N/A',        C_ACCENT),
            self._info_card("Area (Acres)", f.total_acres or 'N/A',                 C_DARK_GREEN),
        ]
        gap   = 3
        col_w = [(CW/5) - gap + gap/5] * 5

        def _row(cl):
            t = Table([cl], colWidths=col_w)
            t.setStyle(TableStyle([
                ('VALIGN',        (0,0),(-1,-1), 'TOP'),
                ('LEFTPADDING',   (0,0),(-1,-1), gap//2),
                ('RIGHTPADDING',  (0,0),(-1,-1), gap//2),
                ('TOPPADDING',    (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ]))
            return t

        banner = self._banner("&#127807;  Farm &amp; Farmer Details", C_DARK_GREEN)
        return [banner, Spacer(1, 4), _row(cards)]

    # ── SECTION: Map & Soil ─────────────────────────────────────────────────
    def _section_map_and_soil(self):
        S = self.S
        sd = self.soil_data
        
        # If no map, just render soil at full width
        if not self.basemap_png:
            ROW_H = 18
            CWS   = [CW * 0.40, CW * 0.60]
            banner = self._urdu_banner("زمین کی زرخیزی")
            
            def hdr_img(txt, w, bg_rgb, fg=(255, 255, 255), bold=True):
                return _urdu_rl(txt, w_pt=w, h_pt=ROW_H, font_size=10, bg=bg_rgb, fg=fg, bold=bold)

            sub = Table([[
                hdr_img("اصل حالت", CWS[0], (26, 35, 126)),
                hdr_img("مٹی کی صحت", CWS[1], (26, 35, 126)),
            ]], colWidths=CWS)
            sub.setStyle(TableStyle([
                ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
                ('LEFTPADDING', (0,0),(-1,-1), 0),
                ('RIGHTPADDING', (0,0),(-1,-1), 0),
            ]))

            rows = []
            for (ulbl, key, unit, exc, avg, poor, exc_fn, avg_fn) in SOIL_ROWS:
                val  = sd.get(key)
                disp = (f"{val} {unit}".strip() if unit else str(val)) if val is not None else "—"
                bg   = _soil_bg(val, exc_fn, avg_fn)
                rows.append([
                    _urdu_rl(disp, CWS[0], ROW_H, font_size=10, bg=_rl2rgb(bg)),
                    _urdu_rl(ulbl, CWS[1], ROW_H, font_size=10, bg=(245, 245, 245)),
                ])
                
            dt = Table(rows, colWidths=CWS)
            dt.setStyle(TableStyle([
                ('GRID', (0,0),(-1,-1), 0.4, C_GRAY),
                ('ALIGN', (0,0),(-1,-1), 'CENTER'),
                ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
                ('LEFTPADDING', (0,0),(-1,-1), 2),
                ('RIGHTPADDING', (0,0),(-1,-1), 2),
                ('FONT', (0,0),(-1,-1), 'Helvetica', 8),
            ]))
            return [banner, Spacer(1, 2), sub, dt]
            
        # We have both map and soil. Arrange them side by side.
        col_gap = 12
        cell_w = (CW - col_gap) / 2
        
        # --- MAP PART ---
        # Compute exact height of the soil part: banner(22) + spacer(2) + header(18) + len(SOIL_ROWS)*18
        soil_h = 22 + 2 + 18 + (len(SOIL_ROWS) * 18)
        # Banner table height roughly 19 points
        banner_h = 19
        target_img_h = soil_h - banner_h
        
        buf = io.BytesIO(self.basemap_png)
        map_img = RLImage(buf, width=cell_w, height=target_img_h)

        banner_style = ParagraphStyle('MapBnr', parent=S['B9'], alignment=TA_CENTER, textColor=C_WHITE)
        banner_p     = Paragraph("Farm satellite image", banner_style)
        banner_table = Table([[banner_p]], colWidths=[cell_w], rowHeights=[banner_h])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), C_DARK_GREEN),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ]))

        layout_map = Table([
            [map_img],
            [banner_table]
        ], colWidths=[cell_w])
        layout_map.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        
        # --- SOIL PART ---
        ROW_H = 18
        CWS = [cell_w * 0.40, cell_w * 0.60]
        soil_banner = _urdu_rl("زمین کی زرخیزی", w_pt=cell_w, h_pt=22, font_size=14, bg=(56, 142, 60), fg=(255, 255, 255))
        
        def hdr_img(txt, w, bg_rgb, fg=(255, 255, 255), bold=True):
            return _urdu_rl(txt, w_pt=w, h_pt=ROW_H, font_size=10, bg=bg_rgb, fg=fg, bold=bold)

        sub = Table([[
            hdr_img("اصل حالت", CWS[0], (26, 35, 126)),
            hdr_img("مٹی کی صحت", CWS[1], (26, 35, 126)),
        ]], colWidths=CWS)
        sub.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ('LEFTPADDING', (0,0),(-1,-1), 0),
            ('RIGHTPADDING', (0,0),(-1,-1), 0),
        ]))

        rows = []
        for (ulbl, key, unit, exc, avg, poor, exc_fn, avg_fn) in SOIL_ROWS:
            val  = sd.get(key)
            disp = (f"{val} {unit}".strip() if unit else str(val)) if val is not None else "—"
            bg   = _soil_bg(val, exc_fn, avg_fn)
            rows.append([
                _urdu_rl(disp, CWS[0], ROW_H, font_size=10, bg=_rl2rgb(bg)),
                _urdu_rl(ulbl, CWS[1], ROW_H, font_size=10, bg=(245, 245, 245)),
            ])
            
        dt = Table(rows, colWidths=CWS)
        dt.setStyle(TableStyle([
            ('GRID', (0,0),(-1,-1), 0.4, C_GRAY),
            ('ALIGN', (0,0),(-1,-1), 'CENTER'),
            ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ('LEFTPADDING', (0,0),(-1,-1), 2),
            ('RIGHTPADDING', (0,0),(-1,-1), 2),
            ('FONT', (0,0),(-1,-1), 'Helvetica', 8),
        ]))
        
        soil_cell = Table([[soil_banner], [Spacer(1, 2)], [sub], [dt]], colWidths=[cell_w])
        soil_cell.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        
        # --- COMBINE SIDE BY SIDE ---
        side_by_side = Table([
            [layout_map, soil_cell]
        ], colWidths=[cell_w, cell_w])
        side_by_side.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('LEFTPADDING', (0,0), (0,0), 0),
            ('RIGHTPADDING', (0,0), (0,0), col_gap),
            ('LEFTPADDING', (1,0), (1,0), 0),
            ('RIGHTPADDING', (1,0), (1,0), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        
        return [side_by_side]

    # ── SECTION: Weather ────────────────────────────────────────────────────

    def _section_weather(self):
        S    = self.S
        days = self.weather_data.get("days", [])
        city = self.weather_data.get("city", "")
        lbl  = (f"&#9925;  Weather Forecast – {city}"
                if city else "&#9925;  Weather Forecast (16-Day)")
        chart_png = _make_weather_chart(days, CW, 2.2*inch)
        elements  = [
            self._banner(lbl, C_NAVY), Spacer(1, 4),
            self._png_to_rl(chart_png, CW, max_h=2.2*inch), Spacer(1, 8),
        ]

        rainy = _get_rainy_days(days)
        if rainy:
            rl = ", ".join(rainy)
            en = (f"Rain is expected on <b>{rl}</b>. "
                  "Please avoid fertiliser or pesticide application on this day.")
            ut = "بارش کے دن: " + "  ،  ".join(rainy)
            un = "براہ کرم ان دنوں میں کھاد اور کیڑے مار ادویات کا استعمال نہ کریں۔"
        else:
            en = "No rainy days forecast in the next 16 days. Ensure adequate irrigation."
            ut = "اگلے 16 دنوں میں کوئی بارش متوقع نہیں ہے۔"
            un = "فصلوں کے لیے مناسب آبپاشی کو یقینی بنائیں۔"

        # English card (left)
        en_card = Table(
            [[Paragraph("&#9729; Weather Advisory", S['ADVISORY_EN'])],
             [Paragraph(en, S['ADVISORY_BODY'])]],
            colWidths=[CW * 0.50 - 6])
        en_card.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,0), colors.HexColor('#E3F2FD')),
            ('BACKGROUND',    (0,1),(0,1), colors.HexColor('#F8FBFF')),
            ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#1565C0')),
            ('TOPPADDING',    (0,0),(-1,-1), 5),
            ('BOTTOMPADDING', (0,0),(-1,-1), 5),
            ('LEFTPADDING',   (0,0),(-1,-1), 8),
            ('RIGHTPADDING',  (0,0),(-1,-1), 8),
            ('VALIGN',        (0,0),(-1,-1), 'TOP'),
        ]))

        # Urdu card (right) — dynamic height via _urdu_rl auto-expand
        ulb = _urdu_rl("موسم کی ہدایات", w_pt=CW*0.48, h_pt=20, font_size=11,
                       bg=(245, 127, 17), fg=(255, 255, 255), bold=True)
        ui1 = _urdu_rl(ut, w_pt=CW*0.48, h_pt=10, font_size=13, bg=(255, 248, 225), fg=(100, 60, 0))
        ui2 = _urdu_rl(un, w_pt=CW*0.48, h_pt=10, font_size=13, bg=(255, 253, 231), fg=(80,  40, 0))

        ur_card = Table([[ulb], [ui1], [ui2]], colWidths=[CW*0.50 - 6])
        ur_card.setStyle(TableStyle([
            ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#F57F17')),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ('LEFTPADDING',   (0,0),(-1,-1), 0),
            ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ('VALIGN',        (0,0),(-1,-1), 'TOP'),
        ]))

        adv = Table([[en_card, ur_card]], colWidths=[CW*0.50, CW*0.50])
        adv.setStyle(TableStyle([
            ('VALIGN',        (0,0),(-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0),(-1,-1), 0),
            ('RIGHTPADDING',  (0,0),(-1,-1), 4),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ]))
        elements.append(adv)
        return elements

    # ══════════════════════════════════════════════════════════════════════
    #  SATELLITE SECTION
    # ══════════════════════════════════════════════════════════════════════

    def _section_satellite_farmer(self):
        S         = self.S
        stage_lbl = self.stage_info.get("label", "Current Stage")
        elements  = [
            self._banner(
                f"&#127947;  Satellite Vegetation Analysis – {stage_lbl}",
                C_NAVY),
            Spacer(1, 6),
        ]

        ndvi_mean = self.ndvi_stats.get("ndvi_mean") or self.ndvi_stats.get("mean")
        if ndvi_mean is not None:
            health = "High" if ndvi_mean >= 0.60 else "Moderate" if ndvi_mean >= 0.35 else "Low"
            elements.append(Paragraph(
                f"<b>Mean NDVI: {ndvi_mean:.3f}</b> – {health} vegetation density", S['B9']))
            elements.append(Spacer(1, 5))

        has_index  = bool(self.index_pngs)
        has_kmeans = bool(self.kmeans_png)

        # ── Horizontal legend ABOVE the images ──────────────────────────
        if has_index or has_kmeans:
            elements.append(self._zone_legend_table())
            elements.append(Spacer(1, 5))

        if has_index and has_kmeans:
            GUTTER    = 0.12 * inch
            cell_w    = (CW - GUTTER) / 2
            img_max_h = 3.2 * inch

            idx_name  = next(iter(self.index_pngs))
            png_bytes = self.index_pngs[idx_name]
            caption   = INDEX_FARMER_CAPTION.get(idx_name, idx_name)
            meta      = INDEX_META.get(idx_name, {"color": "#388E3C"})
            hdr_color = colors.HexColor(meta["color"])

            hdr_p_left = Paragraph(
                f"<b>{caption}</b>",
                ParagraphStyle('_fhdr_l', fontSize=9, fontName='Helvetica-Bold',
                               textColor=C_WHITE, leading=12))
            img_left  = self._png_to_rl(png_bytes, cell_w - 2, img_max_h)
            card_left = Table([[hdr_p_left], [img_left]], colWidths=[cell_w])
            card_left.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(0,0), hdr_color),
                ('TOPPADDING',    (0,0),(0,0), 5),
                ('BOTTOMPADDING', (0,0),(0,0), 5),
                ('LEFTPADDING',   (0,0),(0,0), 8),
                ('RIGHTPADDING',  (0,0),(0,0), 8),
                ('TOPPADDING',    (0,1),(0,1), 2),
                ('BOTTOMPADDING', (0,1),(0,1), 2),
                ('LEFTPADDING',   (0,1),(0,1), 1),
                ('RIGHTPADDING',  (0,1),(0,1), 1),
                ('ALIGN',         (0,1),(0,1), 'CENTER'),
                ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
            ]))

            hdr_p_right = Paragraph(
                "<b>Vegetation Zone Map</b>",
                ParagraphStyle('_fhdr_r', fontSize=9, fontName='Helvetica-Bold',
                               textColor=C_WHITE, leading=12))
            img_right  = self._png_to_rl(self.kmeans_png, cell_w - 2, img_max_h)
            card_right = Table([[hdr_p_right], [img_right]], colWidths=[cell_w])
            card_right.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(0,0), C_DARK_GREEN),
                ('TOPPADDING',    (0,0),(0,0), 5),
                ('BOTTOMPADDING', (0,0),(0,0), 5),
                ('LEFTPADDING',   (0,0),(0,0), 8),
                ('RIGHTPADDING',  (0,0),(0,0), 8),
                ('TOPPADDING',    (0,1),(0,1), 2),
                ('BOTTOMPADDING', (0,1),(0,1), 2),
                ('LEFTPADDING',   (0,1),(0,1), 1),
                ('RIGHTPADDING',  (0,1),(0,1), 1),
                ('ALIGN',         (0,1),(0,1), 'CENTER'),
                ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
            ]))

            side_by_side = Table(
                [[card_left, card_right]],
                colWidths=[cell_w, cell_w],
            )
            side_by_side.setStyle(TableStyle([
                ('VALIGN',        (0,0),(-1,-1), 'TOP'),
                ('LEFTPADDING',   (0,0),(-1,-1), 0),
                ('RIGHTPADDING',  (0,0),(0,-1),  GUTTER),
                ('RIGHTPADDING',  (1,0),(1,-1),  0),
                ('TOPPADDING',    (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 0),
            ]))
            elements.append(side_by_side)
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                "Left: Vegetation health index map.  "
                "Right: Farm divided into 4 vegetation zones based on satellite data.",
                S['CAP']))
            elements.append(Spacer(1, 6))

        elif has_index and not has_kmeans:
            idx_name  = next(iter(self.index_pngs))
            png_bytes = self.index_pngs[idx_name]
            caption   = INDEX_FARMER_CAPTION.get(idx_name, idx_name)
            meta      = INDEX_META.get(idx_name, {"color": "#388E3C"})
            hdr_color = colors.HexColor(meta["color"])
            hdr_p = Paragraph(
                f"<b>{caption}</b>",
                ParagraphStyle('_fhdr', fontSize=10, fontName='Helvetica-Bold',
                               textColor=C_WHITE, leading=13))
            img  = self._png_to_rl(png_bytes, CW - 2, NDVI_MAX_H)
            card = Table([[hdr_p], [img]], colWidths=[CW])
            card.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(0,0), hdr_color),
                ('TOPPADDING',    (0,0),(0,0), 6),
                ('BOTTOMPADDING', (0,0),(0,0), 6),
                ('LEFTPADDING',   (0,0),(0,0), 10),
                ('TOPPADDING',    (0,1),(0,1), 2),
                ('BOTTOMPADDING', (0,1),(0,1), 2),
                ('LEFTPADDING',   (0,1),(0,1), 1),
                ('RIGHTPADDING',  (0,1),(0,1), 1),
                ('ALIGN',         (0,1),(0,1), 'CENTER'),
                ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
            ]))
            elements.append(card)
            elements.append(Spacer(1, 8))

        elif not has_index and has_kmeans:
            elements.append(self._banner(
                "&#127919;  Vegetation Zone Map (K-Means Classification)", C_DARK_GREEN))
            elements.append(Spacer(1, 4))
            km_img = self._png_to_rl(self.kmeans_png, CW, NDVI_MAX_H)
            elements.append(km_img)
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                "Farm divided into 4 vegetation health zones based on satellite data.",
                S['CAP']))
            elements.append(Spacer(1, 6))

        else:
            elements.append(Paragraph(
                "Satellite imagery not available for this stage.", S['B9']))

        # ── Zone area in acres row (below images) ────────────────────
        acres_row = self._zone_acres_row()
        if acres_row and (has_index or has_kmeans):
            elements.append(Spacer(1, 3))
            elements.append(acres_row)
            elements.append(Spacer(1, 2))

        return elements

    def _section_satellite_agro(self):
        """
        AGRO PAGE 2 satellite block.

        For each index:
          ┌─────────────────────────────────────────────────┐
          │  Legend (1 horizontal line, zone colours)        │
          │  [Index image]  |  [K-Means for that index]     │
          │  Zone areas in acres (1 coloured bar row)        │
          └─────────────────────────────────────────────────┘
        Then at the end: overall NDVI-based K-Means (full width) if available.
        """
        S         = self.S
        stage_lbl = self.stage_info.get("label", "Current Stage")
        indices   = list(self.index_pngs.keys())
        n         = len(indices)

        elements = [
            self._banner(
                f"&#127947;  Satellite Vegetation Analysis – {stage_lbl}",
                C_NAVY),
            Spacer(1, 6),
        ]

        ndvi_mean = self.ndvi_stats.get("ndvi_mean") or self.ndvi_stats.get("mean")
        if ndvi_mean is not None:
            health = "High" if ndvi_mean >= 0.60 else "Moderate" if ndvi_mean >= 0.35 else "Low"
            elements.append(Paragraph(
                f"<b>Mean NDVI: {ndvi_mean:.3f}</b> – {health} vegetation density", S['B9']))
            elements.append(Spacer(1, 5))

        if not self.index_pngs:
            elements.append(Paragraph(
                "Satellite imagery not available for this stage.", S['B9']))
        else:
            GUTTER  = 0.10 * inch
            cell_w  = (CW - GUTTER) / 2
            img_h   = 2.8 * inch

            for idx_name in indices:
                png_bytes = self.index_pngs[idx_name]
                meta      = INDEX_META.get(idx_name, {"full": idx_name, "color": "#388E3C"})
                hdr_color = colors.HexColor(meta["color"])
                full_name = meta["full"]

                # ── Legend row above this index pair ────────────────
                elements.append(self._zone_legend_table())
                elements.append(Spacer(1, 3))

                # ── Index image (left) + K-Means for this index (right) ──
                # Left card: real index image
                hdr_index_p = Paragraph(
                    f"<b>{idx_name}</b>  <font size='7'>{full_name}</font>",
                    ParagraphStyle(f'_ahi_{idx_name}', fontSize=9,
                                   fontName='Helvetica-Bold',
                                   textColor=C_WHITE, leading=12))
                img_index  = self._png_to_rl(png_bytes, cell_w - 2, img_h)
                card_index = Table([[hdr_index_p], [img_index]], colWidths=[cell_w])
                card_index.setStyle(TableStyle([
                    ('BACKGROUND',    (0,0),(0,0), hdr_color),
                    ('TOPPADDING',    (0,0),(0,0), 5),
                    ('BOTTOMPADDING', (0,0),(0,0), 5),
                    ('LEFTPADDING',   (0,0),(0,0), 7),
                    ('RIGHTPADDING',  (0,0),(0,0), 7),
                    ('TOPPADDING',    (0,1),(0,1), 2),
                    ('BOTTOMPADDING', (0,1),(0,1), 2),
                    ('LEFTPADDING',   (0,1),(0,1), 1),
                    ('RIGHTPADDING',  (0,1),(0,1), 1),
                    ('ALIGN',         (0,1),(0,1), 'CENTER'),
                    ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
                ]))

                # Right card: K-Means zone map (shared, NDVI-based)
                if self.kmeans_png:
                    hdr_km_p = Paragraph(
                        f"<b>Vegetation Zones</b>  "
                        f"<font size='7'>(K-Means, NDVI-based)</font>",
                        ParagraphStyle(f'_ahk_{idx_name}', fontSize=9,
                                       fontName='Helvetica-Bold',
                                       textColor=C_WHITE, leading=12))
                    img_km    = self._png_to_rl(self.kmeans_png, cell_w - 2, img_h)
                    card_km   = Table([[hdr_km_p], [img_km]], colWidths=[cell_w])
                    card_km.setStyle(TableStyle([
                        ('BACKGROUND',    (0,0),(0,0), C_DARK_GREEN),
                        ('TOPPADDING',    (0,0),(0,0), 5),
                        ('BOTTOMPADDING', (0,0),(0,0), 5),
                        ('LEFTPADDING',   (0,0),(0,0), 7),
                        ('RIGHTPADDING',  (0,0),(0,0), 7),
                        ('TOPPADDING',    (0,1),(0,1), 2),
                        ('BOTTOMPADDING', (0,1),(0,1), 2),
                        ('LEFTPADDING',   (0,1),(0,1), 1),
                        ('RIGHTPADDING',  (0,1),(0,1), 1),
                        ('ALIGN',         (0,1),(0,1), 'CENTER'),
                        ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
                    ]))
                    pair_row = Table(
                        [[card_index, card_km]],
                        colWidths=[cell_w, cell_w],
                    )
                else:
                    # No K-Means available → index image full width
                    img_index_fw = self._png_to_rl(png_bytes, CW - 2, img_h)
                    hdr_fw = Paragraph(
                        f"<b>{idx_name}</b>  <font size='7'>{full_name}</font>",
                        ParagraphStyle(f'_ahifw_{idx_name}', fontSize=9,
                                       fontName='Helvetica-Bold',
                                       textColor=C_WHITE, leading=12))
                    card_fw = Table([[hdr_fw], [img_index_fw]], colWidths=[CW])
                    card_fw.setStyle(TableStyle([
                        ('BACKGROUND',    (0,0),(0,0), hdr_color),
                        ('TOPPADDING',    (0,0),(0,0), 5),
                        ('BOTTOMPADDING', (0,0),(0,0), 5),
                        ('LEFTPADDING',   (0,0),(0,0), 7),
                        ('RIGHTPADDING',  (0,0),(0,0), 7),
                        ('TOPPADDING',    (0,1),(0,1), 2),
                        ('BOTTOMPADDING', (0,1),(0,1), 2),
                        ('LEFTPADDING',   (0,1),(0,1), 1),
                        ('RIGHTPADDING',  (0,1),(0,1), 1),
                        ('ALIGN',         (0,1),(0,1), 'CENTER'),
                        ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
                    ]))
                    pair_row = Table([[card_fw]], colWidths=[CW])

                pair_row.setStyle(TableStyle([
                    ('VALIGN',        (0,0),(-1,-1), 'TOP'),
                    ('LEFTPADDING',   (0,0),(-1,-1), 0),
                    ('RIGHTPADDING',  (0,0),(-1,-1), 0),
                    ('TOPPADDING',    (0,0),(-1,-1), 0),
                    ('BOTTOMPADDING', (0,0),(-1,-1), 0),
                ]))
                elements.append(pair_row)

                # ── Zone acres row below ─────────────────────────────
                acres_row = self._zone_acres_row()
                if acres_row:
                    elements.append(Spacer(1, 2))
                    elements.append(acres_row)

                elements.append(Spacer(1, 10))

        return elements

    def _agro_index_card(self, idx_name: str, png_bytes: bytes, target_w: float) -> Table:
        meta      = INDEX_META.get(idx_name, {"full": idx_name, "color": "#388E3C"})
        hdr_color = colors.HexColor(meta["color"])
        full_name = meta["full"]
        hdr_p = Paragraph(
            f"<b>{idx_name}</b>  <font size='7'>{full_name}</font>",
            ParagraphStyle('_ahdr', fontSize=9, fontName='Helvetica-Bold',
                           textColor=C_WHITE, leading=12))
        img  = self._png_to_rl(png_bytes, target_w - 2, NDVI_MAX_H)
        card = Table([[hdr_p], [img]], colWidths=[target_w])
        card.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,0), hdr_color),
            ('TOPPADDING',    (0,0),(0,0), 5),
            ('BOTTOMPADDING', (0,0),(0,0), 5),
            ('LEFTPADDING',   (0,0),(0,0), 7),
            ('RIGHTPADDING',  (0,0),(0,0), 7),
            ('TOPPADDING',    (0,1),(0,1), 2),
            ('BOTTOMPADDING', (0,1),(0,1), 2),
            ('LEFTPADDING',   (0,1),(0,1), 1),
            ('RIGHTPADDING',  (0,1),(0,1), 1),
            ('ALIGN',         (0,1),(0,1), 'CENTER'),
            ('BOX',           (0,0),(-1,-1), 0.6, colors.HexColor('#AAAAAA')),
        ]))
        return card

    # ── SECTION: Recommendations ────────────────────────────────────────────

    def _section_recommendations(self):
        S        = self.S
        si       = self.stage_info
        elements = [
            self._banner("&#127807;  Crop Recommendations", C_DARK_GREEN),
            Spacer(1, 5),
        ]

        if si.get("label"):
            elements.append(Paragraph(
                f"<b>Stage:</b> {si['label']}  |  "
                f"<b>Day {si.get('days_since_sowing','?')}</b> since sowing  |  "
                f"<b>Window:</b> {si.get('day_range','')}",
                ParagraphStyle('_rc', fontSize=8, fontName='Helvetica-Oblique',
                               textColor=colors.HexColor('#555555'), leading=11)))
            elements.append(Spacer(1, 5))

        if not self.recommendation_items:
            elements.append(Paragraph(
                "No recommendations available for the current crop stage.", S['B9']))
            return elements

        # Group by index
        grouped: dict = {}
        for item in self.recommendation_items:
            grouped.setdefault(item.indice, []).append(item)

        for indice, items in grouped.items():
            meta      = INDEX_META.get(indice, {"full": indice, "color": "#388E3C"})
            idx_color = colors.HexColor(meta["color"])

            if self.is_farmer:
                caption    = INDEX_FARMER_CAPTION.get(indice, indice)
                hdr_txt    = f"<b>{caption}</b>"
                hdr_bg     = colors.HexColor(meta["color"] + "22")
                hdr_border = idx_color
            else:
                hdr_txt    = f"<b>{indice}</b> – {meta['full']}"
                hdr_bg     = idx_color
                hdr_border = idx_color

            ht = Table([[Paragraph(
                hdr_txt,
                ParagraphStyle('_rh', fontSize=9, fontName='Helvetica-Bold',
                               textColor=C_WHITE if not self.is_farmer else idx_color,
                               leading=12))
            ]], colWidths=[CW])
            ht.setStyle(TableStyle([
                ('BACKGROUND',    (0,0),(-1,-1), hdr_bg),
                ('BOX',           (0,0),(-1,-1), 0.8, hdr_border),
                ('TOPPADDING',    (0,0),(-1,-1), 5),
                ('BOTTOMPADDING', (0,0),(-1,-1), 5),
                ('LEFTPADDING',   (0,0),(-1,-1), 10),
                ('RIGHTPADDING',  (0,0),(-1,-1), 8),
            ]))

            group = [ht, Spacer(1, 3)]

            for item in items:
                stage_display = (item.get_crop_stage_display()
                                 if hasattr(item, 'get_crop_stage_display')
                                 else item.crop_stage)

                group.append(Paragraph(
                    f"<b>{stage_display}</b>  "
                    f"<font color='#777777'>({item.duration_in_days} days)</font>",
                    S['B9B']))
                group.append(Spacer(1, 2))

                # ── FIX: clean rec_text before passing to _urdu_rl ──────
                raw_rec = str(item.recommendation_text) if item.recommendation_text else ""
                rec_text = _clean_urdu_text(
                    raw_rec.replace('\r\n', '\n').replace('\r', '\n').strip()
                )

                if rec_text:
                    urdu_img = _urdu_rl(
                        rec_text,
                        w_pt=CW - 0.4 * inch,
                        h_pt=30,        # minimum height; auto-expands as needed
                        font_size=12,
                        bg=(250, 250, 250),
                        fg=(40, 40, 40),
                    )
                    group.append(urdu_img)
                else:
                    group.append(Paragraph("No recommendation text available.", S['B9']))

                group.append(Spacer(1, 8))

            elements.append(KeepTogether(group))
            elements.append(Spacer(1, 6))

        return elements

    # ── SECTION: Footer ─────────────────────────────────────────────────────

    def _section_footer(self):
        S        = self.S
        logo     = self._logo_image(max_h=0.30*inch)
        date_str = datetime.now().strftime('%B %d, %Y at %I:%M %p')
        rtype    = "Farmer Advisory" if self.is_farmer else "Agronomist Report"
        logo_cell = logo if logo else Paragraph("LIMS", S['B7'])
        text_cell = Paragraph(
            f"<i>Generated by LIMS ({rtype}) on {date_str}</i> &nbsp;|&nbsp; "
            "<i>Land Information &amp; Management System</i>",
            ParagraphStyle('_ft', fontSize=7, fontName='Helvetica-Oblique',
                           textColor=C_DGRAY, alignment=TA_CENTER))
        footer_row = Table([[logo_cell, text_cell]],
                           colWidths=[0.7*inch, CW - 0.7*inch])
        footer_row.setStyle(TableStyle([
            ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
            ('LEFTPADDING',  (0,0),(-1,-1), 0),
            ('RIGHTPADDING', (0,0),(-1,-1), 0),
        ]))
        return [
            Spacer(1, 8),
            HRFlowable(width=CW, thickness=2, color=C_DARK_GREEN,
                       spaceAfter=4, spaceBefore=0),
            footer_row,
        ]