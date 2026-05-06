# """
# ndvi_service.py
# ---------------
# Fetches satellite indices from Sentinel-Hub for a farm polygon.

# The index (or set of indices) fetched is determined dynamically by the
# caller based on the current crop stage.

# Supported indices: NDVI, MSAVI, NDRE, ReCL, NDMI
# """

# import io
# import os
# import uuid
# import traceback
# import numpy as np

# import requests as http_requests
# from datetime import datetime, timedelta
# from PIL import Image as PILImage, ImageDraw, ImageFilter, ImageFont
# from shapely.geometry import shape, Polygon, MultiPolygon

# from sentinelhub import (
#     SHConfig, SentinelHubRequest, DataCollection,
#     MimeType, BBox, bbox_to_dimensions, CRS, Geometry,
# )

# from django.conf import settings

# import logging
# logger = logging.getLogger(__name__)

# # ── Sentinel-Hub credentials ──────────────────────────────────────────────
# SH_CLIENT_ID     = 'b7ad13c9-8aeb-46a1-a752-404f7c854ac7'
# SH_CLIENT_SECRET = 'xJgiBaLovfijWueXRKXrOcjQhwk0Bmlz'
# SH_TOKEN_URL     = (
#     'https://services.sentinel-hub.com/auth/realms/main/'
#     'protocol/openid-connect/token'
# )

# MIN_OUTPUT_PX = 800

# # ── Colour evalscripts ────────────────────────────────────────────────────

# EVALSCRIPTS: dict[str, str] = {

#     "NDVI": """//VERSION=3
# function setup(){return{input:[{bands:["B04","B08"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function cb(v){
#   if(v>=0.95)return[0,127,71];if(v>=0.90)return[6,150,84];if(v>=0.85)return[21,169,97];
#   if(v>=0.80)return[85,190,107];if(v>=0.75)return[119,202,112];if(v>=0.70)return[155,215,116];
#   if(v>=0.65)return[186,225,130];if(v>=0.60)return[212,239,150];if(v>=0.55)return[235,247,173];
#   if(v>=0.50)return[254,254,195];if(v>=0.45)return[255,237,171];if(v>=0.40)return[253,199,127];
#   if(v>=0.35)return[255,172,103];if(v>=0.30)return[255,139,87];if(v>=0.25)return[255,107,74];
#   if(v>=0.20)return[237,78,60];if(v>=0.15)return[226,43,45];if(v>=0.10)return[197,18,39];
#   return[171,0,41];}
# function evaluatePixel(s){return cb((s.B08-s.B04)/(s.B08+s.B04+1e-9));}""",

#     # MSAVI – Modified Soil-Adjusted Vegetation Index
#     # Useful in early growth when soil is still exposed
#     "MSAVI": """//VERSION=3
# function setup(){return{input:[{bands:["B04","B08"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function cb(v){
#   // Same green-red ramp as NDVI for consistency
#   if(v>=0.80)return[0,127,71];if(v>=0.70)return[21,169,97];
#   if(v>=0.60)return[85,190,107];if(v>=0.50)return[155,215,116];
#   if(v>=0.40)return[212,239,150];if(v>=0.30)return[254,254,195];
#   if(v>=0.20)return[255,172,103];if(v>=0.10)return[255,107,74];
#   return[171,0,41];}
# function evaluatePixel(s){
#   let nir=s.B08, red=s.B04;
#   let msavi=(2*nir+1-Math.sqrt(Math.pow(2*nir+1,2)-8*(nir-red)))/2;
#   return cb(msavi);}""",

#     # NDRE – Red Edge NDVI (requires B05 + B08A — Sentinel-2 specific)
#     "NDRE": """//VERSION=3
# function setup(){return{input:[{bands:["B05","B08A"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function cb(v){
#   if(v>=0.60)return[0,127,71];if(v>=0.50)return[21,169,97];
#   if(v>=0.40)return[85,190,107];if(v>=0.30)return[155,215,116];
#   if(v>=0.20)return[212,239,150];if(v>=0.10)return[254,254,195];
#   return[171,0,41];}
# function evaluatePixel(s){return cb((s.B08A-s.B05)/(s.B08A+s.B05+1e-9));}""",

#     # ReCL – Red-Edge Chlorophyll Index
#     "ReCL": """//VERSION=3
# function setup(){return{input:[{bands:["B05","B07"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function cb(v){
#   if(v>=6.0)return[0,127,71];if(v>=5.0)return[21,169,97];
#   if(v>=4.0)return[85,190,107];if(v>=3.0)return[155,215,116];
#   if(v>=2.0)return[212,239,150];if(v>=1.0)return[254,254,195];
#   return[171,0,41];}
# function evaluatePixel(s){return cb((s.B07/s.B05)-1);}""",

#     # NDMI – Normalised Difference Moisture Index
#     "NDMI": """//VERSION=3
# function setup(){return{input:[{bands:["B08","B11"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function cb(v){
#   // Blue-brown ramp: high moisture = blue, low = brown
#   if(v>=0.60)return[5,113,176];if(v>=0.40)return[74,166,218];
#   if(v>=0.20)return[166,217,240];if(v>=0.00)return[224,243,248];
#   if(v>=-0.20)return[253,219,199];if(v>=-0.40)return[244,165,130];
#   return[214,96,77];}
# function evaluatePixel(s){return cb((s.B08-s.B11)/(s.B08+s.B11+1e-9));}""",
# }

# # Float evalscripts for stats computation (always NDVI-based for K-Means)
# NDVI_FLOAT_EVALSCRIPT = (
#     "//VERSION=3\n"
#     "function setup(){return{input:[{bands:['B04','B08']}],"
#     "output:{bands:1,sampleType:SampleType.FLOAT32}};}\n"
#     "function evaluatePixel(s){return[(s.B08-s.B04)/(s.B08+s.B04+1e-9)];}"
# )

# TRUE_COLOR_EVALSCRIPT = """//VERSION=3
# function setup(){return{input:[{bands:["B04","B03","B02"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
# function evaluatePixel(s){
#   return[Math.min(255,Math.round(3.5*s.B04*255)),
#          Math.min(255,Math.round(3.5*s.B03*255)),
#          Math.min(255,Math.round(3.5*s.B02*255))];}"""

# ZONE_COLORS = {
#     1: (108,  52, 131),
#     2: (244, 208,  63),
#     3: (169, 223, 191),
#     4: ( 30, 132,  73),
# }
# ZONE_LABELS = {
#     1: "Zone 1 – Poor",
#     2: "Zone 2 – Low",
#     3: "Zone 3 – Moderate",
#     4: "Zone 4 – Good",
# }


# # ── Internal helpers ──────────────────────────────────────────────────────

# def _get_token() -> str:
#     r = http_requests.post(
#         SH_TOKEN_URL,
#         data={
#             "grant_type":    "client_credentials",
#             "client_id":     SH_CLIENT_ID,
#             "client_secret": SH_CLIENT_SECRET,
#         },
#         headers={"Content-Type": "application/x-www-form-urlencoded"},
#         timeout=30,
#     )
#     if r.status_code != 200:
#         raise RuntimeError(f"SH token error {r.status_code}: {r.text[:200]}")
#     tok = r.json().get("access_token")
#     if not tok:
#         raise RuntimeError("No access_token in response")
#     return tok


# def _sh_request(polygon_coords, evalscript, mime, tmp_dir, tok, d_from, d_to):
#     cfg = SHConfig()
#     cfg.sh_client_id     = SH_CLIENT_ID
#     cfg.sh_client_secret = SH_CLIENT_SECRET
#     cfg.sh_token         = tok

#     geo    = Geometry(
#         geometry={"type": "Polygon", "coordinates": [polygon_coords]},
#         crs=CRS.WGS84,
#     )
#     bounds = shape(geo.geometry).bounds
#     size   = bbox_to_dimensions(BBox(bbox=bounds, crs=CRS.WGS84), resolution=10)

#     req = SentinelHubRequest(
#         evalscript=evalscript,
#         input_data=[SentinelHubRequest.input_data(
#             data_collection=DataCollection.SENTINEL2_L2A,
#             time_interval=(d_from, d_to),
#             mosaicking_order='leastCC',
#         )],
#         responses=[SentinelHubRequest.output_response("default", mime)],
#         geometry=geo,
#         size=size,
#         config=cfg,
#         data_folder=tmp_dir,
#     )
#     return req.get_data()[0], bounds, size


# def _polygon_mask(polygon_coords, bounds, w, h) -> PILImage.Image:
#     minx, miny, maxx, maxy = bounds
#     mask = PILImage.new("L", (w, h), 0)
#     draw = ImageDraw.Draw(mask)
#     geom = shape({"type": "Polygon", "coordinates": [polygon_coords]})

#     def _fill(poly: Polygon):
#         pts = [
#             ((lon - minx) / (maxx - minx) * w,
#              (maxy - lat) / (maxy - miny) * h)
#             for lon, lat in poly.exterior.coords
#         ]
#         draw.polygon(pts, fill=255)
#         for interior in poly.interiors:
#             draw.polygon(
#                 [((lon - minx) / (maxx - minx) * w,
#                   (maxy - lat) / (maxy - miny) * h)
#                  for lon, lat in interior.coords],
#                 fill=0,
#             )

#     if isinstance(geom, Polygon):
#         _fill(geom)
#     elif isinstance(geom, MultiPolygon):
#         for p in geom.geoms:
#             _fill(p)

#     return mask.filter(ImageFilter.GaussianBlur(radius=1))


# def _upsample(img: PILImage.Image) -> PILImage.Image:
#     w, h = img.size
#     if min(w, h) >= MIN_OUTPUT_PX:
#         return img
#     scale = MIN_OUTPUT_PX / min(w, h)
#     return img.resize(
#         (max(int(w * scale), MIN_OUTPUT_PX),
#          max(int(h * scale), MIN_OUTPUT_PX)),
#         PILImage.Resampling.NEAREST,
#     )


# def _clip_to_polygon(img_rgba: PILImage.Image, mask: PILImage.Image) -> PILImage.Image:
#     w, h = img_rgba.size
#     if mask.size != (w, h):
#         mask = mask.resize((w, h), PILImage.Resampling.NEAREST)
#     r, g, b, a = img_rgba.split()
#     combined_alpha = PILImage.fromarray(
#         np.minimum(np.array(a), np.array(mask)).astype(np.uint8)
#     )
#     img_rgba.putalpha(combined_alpha)
#     return img_rgba


# def _to_png_bytes(img: PILImage.Image) -> bytes:
#     buf = io.BytesIO()
#     img.save(buf, "PNG")
#     buf.seek(0)
#     return buf.getvalue()


# def _fetch_true_color(polygon_coords, bounds, tmp_dir, tok, d_from, d_to):
#     arr, _, (nw, nh) = _sh_request(
#         polygon_coords, TRUE_COLOR_EVALSCRIPT, MimeType.PNG, tmp_dir, tok, d_from, d_to
#     )
#     if arr.ndim == 2:
#         arr = np.stack([arr, arr, arr], axis=-1)
#     return PILImage.fromarray(arr.astype(np.uint8), "RGB"), nw, nh


# def _draw_polygon_border(img, polygon_coords, bounds, color=(255, 50, 50), width=3):
#     minx, miny, maxx, maxy = bounds
#     w, h = img.size
#     draw = ImageDraw.Draw(img)
#     pts = [
#         ((lon - minx) / (maxx - minx) * w,
#          (maxy - lat) / (maxy - miny) * h)
#         for lon, lat in polygon_coords
#     ]
#     draw.line(pts + [pts[0]], fill=color, width=width)
#     return img


# def _composite_overlay_on_basemap(basemap_rgb, overlay_rgba, opacity=0.80):
#     bm = basemap_rgb.convert("RGBA")
#     ov = overlay_rgba.convert("RGBA")
#     if bm.size != ov.size:
#         ov = ov.resize(bm.size, PILImage.LANCZOS)
#     r, g, b, a = ov.split()
#     a = a.point(lambda v: int(v * opacity))
#     ov = PILImage.merge("RGBA", (r, g, b, a))
#     result = bm.copy()
#     result.paste(ov, mask=ov.split()[3])
#     return result.convert("RGB")


# def _kmeans_zone_image(float_arr, polygon_coords, bounds, n_zones=4):
#     from sklearn.cluster import KMeans

#     h, w = float_arr.shape[:2]
#     fa   = float_arr if float_arr.ndim == 2 else float_arr[:, :, 0]

#     mask_img = _polygon_mask(polygon_coords, bounds, w, h)
#     mask     = np.array(mask_img) > 128

#     valid_vals  = fa[mask]
#     finite_mask = np.isfinite(valid_vals)
#     valid_vals  = valid_vals[finite_mask]

#     zone_arr = np.zeros((h, w), dtype=np.uint8)

#     if len(valid_vals) >= n_zones:
#         km = KMeans(n_clusters=n_zones, random_state=42, n_init=10)
#         km.fit(valid_vals.reshape(-1, 1))

#         centroids       = km.cluster_centers_.flatten()
#         sorted_centroids = np.sort(centroids)
#         rank_map = {
#             old: new + 1
#             for new, old in enumerate(np.argsort(centroids))
#         }

#         valid_yx = np.argwhere(mask)
#         finite_yx = valid_yx[finite_mask]
#         for idx, (y, x) in enumerate(finite_yx):
#             zone_arr[y, x] = rank_map[km.labels_[idx]]

#     zone_rgba = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
#     pix = zone_rgba.load()
#     for y in range(h):
#         for x in range(w):
#             z = zone_arr[y, x]
#             if z > 0:
#                 pix[x, y] = ZONE_COLORS[z] + (255,)

#     zone_rgba = _upsample(zone_rgba)
#     return zone_rgba


# # ── Single-index fetch ────────────────────────────────────────────────────

# def _fetch_single_index(index_name: str, pc, bounds, tmp_dir, tok, d_from, d_to, mask_native, nw, nh, tc_up):
#     """Fetch one index and return (png_bytes, mean_stat)."""
#     evalscript = EVALSCRIPTS.get(index_name)
#     if not evalscript:
#         logger.warning(f"No evalscript for index '{index_name}', skipping.")
#         return None, None

#     rgb_arr, _, _ = _sh_request(pc, evalscript, MimeType.PNG, tmp_dir, tok, d_from, d_to)

#     if rgb_arr.ndim == 2:
#         rgb_arr = np.stack([rgb_arr, rgb_arr, rgb_arr], axis=-1)

#     rgb_img = PILImage.fromarray(rgb_arr.astype(np.uint8), "RGB").convert("RGBA")
#     rgb_up  = _upsample(rgb_img)
#     mask_up = _upsample(mask_native)
#     clipped = _clip_to_polygon(rgb_up, mask_up)

#     if tc_up is not None:
#         overlay = _composite_overlay_on_basemap(tc_up.copy(), clipped, opacity=0.85)
#         overlay = _draw_polygon_border(overlay, pc, bounds)
#         png = _to_png_bytes(overlay)
#     else:
#         bg = PILImage.new("RGBA", clipped.size, (255, 255, 255, 255))
#         bg.paste(clipped, mask=clipped.split()[3])
#         png = _to_png_bytes(bg.convert("RGB"))

#     return png, None   # mean_stat computed separately from float array for NDVI only


# # ── Public entry-point ────────────────────────────────────────────────────

# def fetch_ndvi_images(
#     polygon_coords: list,
#     date_str: str,           # "YYYY-MM-DD"  (use today's date, not sowing_date)
#     date_range_days: int = 15,
#     indices: list[str] | None = None,   # e.g. ["NDVI"], ["MSAVI","NDVI"], etc.
# ) -> dict:
#     """
#     Fetch the requested satellite indices for the given polygon.

#     Parameters
#     ----------
#     polygon_coords  : list of [lon, lat] pairs
#     date_str        : centre of the date window (YYYY-MM-DD) — use today's date
#     date_range_days : window half-width in days
#     indices         : list of index names to fetch (from EVALSCRIPTS keys).
#                       Defaults to ["NDVI"] if not provided.

#     Returns
#     -------
#     {
#       "index_pngs":  { "NDVI": bytes, "MSAVI": bytes, ... },   # one PNG per index
#       "kmeans_png":  bytes,    # K-Means zone map (always NDVI-based)
#       "basemap_png": bytes,    # True-colour satellite basemap
#       "stats": {
#           "ndvi_mean": float,
#           "zone_pct":  {1: float, 2: float, 3: float, 4: float},
#       },
#       "error": str | None,
#     }
#     """
#     if not indices:
#         indices = ["NDVI"]

#     result = {
#         "index_pngs":  {},
#         "kmeans_png":  None,
#         "basemap_png": None,
#         "stats":       {},
#         "error":       None,
#     }

#     # ── Normalise polygon ────────────────────────────────────────────────
#     try:
#         pc = [[float(c[0]), float(c[1])] for c in polygon_coords]
#     except Exception as e:
#         result["error"] = f"Bad polygon coords: {e}"
#         return result

#     if pc[0] != pc[-1]:
#         pc.append(pc[0])

#     try:
#         geom = shape({"type": "Polygon", "coordinates": [pc]})
#         if not geom.is_valid:
#             result["error"] = "Invalid polygon geometry"
#             return result
#     except Exception as e:
#         result["error"] = str(e)
#         return result

#     # ── Date window ──────────────────────────────────────────────────────
#     try:
#         dt     = datetime.strptime(date_str, "%Y-%m-%d")
#         d_from = (dt - timedelta(days=date_range_days)).strftime("%Y-%m-%d")
#         d_to   = (dt + timedelta(days=date_range_days)).strftime("%Y-%m-%d")
#     except Exception:
#         d_from = "2024-03-01"
#         d_to   = "2024-05-30"

#     # ── SH token ─────────────────────────────────────────────────────────
#     try:
#         tok = _get_token()
#     except Exception as e:
#         result["error"] = f"SH auth failed: {e}"
#         return result

#     tmp_dir = os.path.join(settings.MEDIA_ROOT, "ndvi_tmp", uuid.uuid4().hex)
#     os.makedirs(tmp_dir, exist_ok=True)

#     try:
#         # ── True-colour basemap ──────────────────────────────────────────
#         tc_up = None
#         try:
#             tc_img, tc_w, tc_h = _fetch_true_color(pc, shape({"type":"Polygon","coordinates":[pc]}).bounds, tmp_dir, tok, d_from, d_to)
#             tc_up = _upsample(tc_img)
#             result["basemap_png"] = _to_png_bytes(tc_up)
#         except Exception as e:
#             logger.warning(f"True color fetch failed: {e}")

#         # ── Determine bounds & native mask from first index ───────────────
#         first_evalscript = EVALSCRIPTS.get(indices[0], EVALSCRIPTS["NDVI"])
#         first_arr, bounds, (nw, nh) = _sh_request(
#             pc, first_evalscript, MimeType.PNG, tmp_dir, tok, d_from, d_to
#         )
#         mask_native = _polygon_mask(pc, bounds, nw, nh)

#         # ── Fetch each requested index ────────────────────────────────────
#         for idx_name in indices:
#             try:
#                 if idx_name == indices[0]:
#                     # Re-use already-fetched first_arr
#                     arr = first_arr
#                 else:
#                     arr, _, _ = _sh_request(
#                         pc, EVALSCRIPTS[idx_name], MimeType.PNG, tmp_dir, tok, d_from, d_to
#                     )

#                 if arr.ndim == 2:
#                     arr = np.stack([arr, arr, arr], axis=-1)

#                 rgb_img = PILImage.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
#                 rgb_up  = _upsample(rgb_img)
#                 mask_up = _upsample(mask_native)
#                 clipped = _clip_to_polygon(rgb_up, mask_up)

#                 if tc_up is not None:
#                     overlay = _composite_overlay_on_basemap(tc_up.copy(), clipped, opacity=0.85)
#                     overlay = _draw_polygon_border(overlay, pc, bounds)
#                     png = _to_png_bytes(overlay)
#                 else:
#                     bg = PILImage.new("RGBA", clipped.size, (255, 255, 255, 255))
#                     bg.paste(clipped, mask=clipped.split()[3])
#                     png = _to_png_bytes(bg.convert("RGB"))

#                 result["index_pngs"][idx_name] = png
#                 logger.info(f"Fetched index {idx_name} OK")

#             except Exception as e:
#                 logger.error(f"Failed to fetch {idx_name}: {e}")

#         # ── NDVI float array for stats + K-Means (always) ───────────────
#         try:
#             float_arr, _, _ = _sh_request(
#                 pc, NDVI_FLOAT_EVALSCRIPT, MimeType.TIFF, tmp_dir, tok, d_from, d_to
#             )
#             fa      = float_arr if float_arr.ndim == 2 else float_arr[:, :, 0]
#             mask_np = np.array(mask_native) > 128
#             valid   = fa[mask_np]
#             valid   = valid[np.isfinite(valid)]
#             result["stats"]["ndvi_mean"] = round(float(np.mean(valid)), 3) if len(valid) else 0.0

#             # K-Means
#             zone_img  = _kmeans_zone_image(float_arr, pc, bounds, n_zones=4)
#             zone_mask = _upsample(mask_native)
#             zone_img  = _clip_to_polygon(zone_img, zone_mask)

#             if tc_up is not None:
#                 zones_on_map = _composite_overlay_on_basemap(tc_up.copy(), zone_img, opacity=0.75)
#                 zones_on_map = _draw_polygon_border(zones_on_map, pc, bounds)
#                 result["kmeans_png"] = _to_png_bytes(zones_on_map)
#             else:
#                 bg2 = PILImage.new("RGBA", zone_img.size, (255, 255, 255, 255))
#                 bg2.paste(zone_img, mask=zone_img.split()[3])
#                 result["kmeans_png"] = _to_png_bytes(bg2.convert("RGB"))

#         except Exception as e:
#             logger.error(f"NDVI float/kmeans fetch failed: {e}")

#         logger.info(
#             f"fetch_ndvi_images: indices={indices}, "
#             f"ndvi_mean={result['stats'].get('ndvi_mean', 'N/A')}"
#         )

#     except Exception as e:
#         logger.error(f"fetch_ndvi_images error: {e}\n{traceback.format_exc()}")
#         result["error"] = str(e)
#     finally:
#         import shutil
#         shutil.rmtree(tmp_dir, ignore_errors=True)

#     return result


# # ── Backwards-compat alias ────────────────────────────────────────────────
# # Old callers that only needed NDVI still work unchanged.
# def fetch_ndvi_images_legacy(polygon_coords, date_str, date_range_days=15):
#     res = fetch_ndvi_images(polygon_coords, date_str, date_range_days, indices=["NDVI"])
#     return {
#         "ndvi_png":   res["index_pngs"].get("NDVI"),
#         "kmeans_png": res["kmeans_png"],
#         "basemap_png": res["basemap_png"],
#         "stats":      res["stats"],
#         "error":      res["error"],
#     }

"""
ndvi_service.py
---------------
Fetches satellite indices from Sentinel-Hub for a farm polygon.

The index (or set of indices) fetched is determined dynamically by the
caller based on the current crop stage.

Supported indices: NDVI, MSAVI, NDRE, ReCL, NDMI
"""

import io
import os
import uuid
import traceback
import numpy as np

import requests as http_requests
from datetime import datetime, timedelta
from PIL import Image as PILImage, ImageDraw, ImageFilter, ImageFont
from shapely.geometry import shape, Polygon, MultiPolygon

from sentinelhub import (
    SHConfig, SentinelHubRequest, DataCollection,
    MimeType, BBox, bbox_to_dimensions, CRS, Geometry,
)

from django.conf import settings

import logging
logger = logging.getLogger(__name__)

# ── Sentinel-Hub credentials ──────────────────────────────────────────────
SH_CLIENT_ID     = 'b7ad13c9-8aeb-46a1-a752-404f7c854ac7'
SH_CLIENT_SECRET = 'xJgiBaLovfijWueXRKXrOcjQhwk0Bmlz'
SH_TOKEN_URL     = (
    'https://services.sentinel-hub.com/auth/realms/main/'
    'protocol/openid-connect/token'
)

MIN_OUTPUT_PX = 800

# ── Colour evalscripts ────────────────────────────────────────────────────

EVALSCRIPTS: dict[str, str] = {

    "NDVI": """//VERSION=3
function setup(){return{input:[{bands:["B04","B08"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function cb(v){
  if(v>=0.95)return[0,127,71];if(v>=0.90)return[6,150,84];if(v>=0.85)return[21,169,97];
  if(v>=0.80)return[85,190,107];if(v>=0.75)return[119,202,112];if(v>=0.70)return[155,215,116];
  if(v>=0.65)return[186,225,130];if(v>=0.60)return[212,239,150];if(v>=0.55)return[235,247,173];
  if(v>=0.50)return[254,254,195];if(v>=0.45)return[255,237,171];if(v>=0.40)return[253,199,127];
  if(v>=0.35)return[255,172,103];if(v>=0.30)return[255,139,87];if(v>=0.25)return[255,107,74];
  if(v>=0.20)return[237,78,60];if(v>=0.15)return[226,43,45];if(v>=0.10)return[197,18,39];
  return[171,0,41];}
function evaluatePixel(s){return cb((s.B08-s.B04)/(s.B08+s.B04+1e-9));}""",

    # MSAVI – Modified Soil-Adjusted Vegetation Index
    # Useful in early growth when soil is still exposed
    "MSAVI": """//VERSION=3
function setup(){return{input:[{bands:["B04","B08"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function cb(v){
  // Same green-red ramp as NDVI for consistency
  if(v>=0.80)return[0,127,71];if(v>=0.70)return[21,169,97];
  if(v>=0.60)return[85,190,107];if(v>=0.50)return[155,215,116];
  if(v>=0.40)return[212,239,150];if(v>=0.30)return[254,254,195];
  if(v>=0.20)return[255,172,103];if(v>=0.10)return[255,107,74];
  return[171,0,41];}
function evaluatePixel(s){
  let nir=s.B08, red=s.B04;
  let msavi=(2*nir+1-Math.sqrt(Math.pow(2*nir+1,2)-8*(nir-red)))/2;
  return cb(msavi);}""",

    # NDRE – Red Edge NDVI (requires B05 + B08A — Sentinel-2 specific)
    "NDRE": """//VERSION=3
function setup(){return{input:[{bands:["B05","B08A"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function cb(v){
  if(v>=0.60)return[0,127,71];if(v>=0.50)return[21,169,97];
  if(v>=0.40)return[85,190,107];if(v>=0.30)return[155,215,116];
  if(v>=0.20)return[212,239,150];if(v>=0.10)return[254,254,195];
  return[171,0,41];}
function evaluatePixel(s){return cb((s.B08A-s.B05)/(s.B08A+s.B05+1e-9));}""",

    # ReCL – Red-Edge Chlorophyll Index
    "ReCL": """//VERSION=3
function setup(){return{input:[{bands:["B05","B07"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function cb(v){
  if(v>=6.0)return[0,127,71];if(v>=5.0)return[21,169,97];
  if(v>=4.0)return[85,190,107];if(v>=3.0)return[155,215,116];
  if(v>=2.0)return[212,239,150];if(v>=1.0)return[254,254,195];
  return[171,0,41];}
function evaluatePixel(s){return cb((s.B07/s.B05)-1);}""",

    # NDMI – Normalised Difference Moisture Index
    "NDMI": """//VERSION=3
function setup(){return{input:[{bands:["B08","B11"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function cb(v){
  // Blue-brown ramp: high moisture = blue, low = brown
  if(v>=0.60)return[5,113,176];if(v>=0.40)return[74,166,218];
  if(v>=0.20)return[166,217,240];if(v>=0.00)return[224,243,248];
  if(v>=-0.20)return[253,219,199];if(v>=-0.40)return[244,165,130];
  return[214,96,77];}
function evaluatePixel(s){return cb((s.B08-s.B11)/(s.B08+s.B11+1e-9));}""",
}

# Float evalscripts for stats computation (always NDVI-based for K-Means)
NDVI_FLOAT_EVALSCRIPT = (
    "//VERSION=3\n"
    "function setup(){return{input:[{bands:['B04','B08']}],"
    "output:{bands:1,sampleType:SampleType.FLOAT32}};}\n"
    "function evaluatePixel(s){return[(s.B08-s.B04)/(s.B08+s.B04+1e-9)];}"
)

TRUE_COLOR_EVALSCRIPT = """//VERSION=3
function setup(){return{input:[{bands:["B04","B03","B02"]}],output:{bands:3,sampleType:SampleType.UINT8}};}
function evaluatePixel(s){
  return[Math.min(255,Math.round(3.5*s.B04*255)),
         Math.min(255,Math.round(3.5*s.B03*255)),
         Math.min(255,Math.round(3.5*s.B02*255))];}"""

ZONE_COLORS = {
    1: (108,  52, 131),
    2: (244, 208,  63),
    3: (169, 223, 191),
    4: ( 30, 132,  73),
}
ZONE_LABELS = {
    1: "Zone 1 – Poor",
    2: "Zone 2 – Low",
    3: "Zone 3 – Moderate",
    4: "Zone 4 – Good",
}


# ── Internal helpers ──────────────────────────────────────────────────────

def _get_token() -> str:
    r = http_requests.post(
        SH_TOKEN_URL,
        data={
            "grant_type":    "client_credentials",
            "client_id":     SH_CLIENT_ID,
            "client_secret": SH_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"SH token error {r.status_code}: {r.text[:200]}")
    tok = r.json().get("access_token")
    if not tok:
        raise RuntimeError("No access_token in response")
    return tok


def _sh_request(polygon_coords, evalscript, mime, tmp_dir, tok, d_from, d_to):
    cfg = SHConfig()
    cfg.sh_client_id     = SH_CLIENT_ID
    cfg.sh_client_secret = SH_CLIENT_SECRET
    cfg.sh_token         = tok

    geo    = Geometry(
        geometry={"type": "Polygon", "coordinates": [polygon_coords]},
        crs=CRS.WGS84,
    )
    bounds = shape(geo.geometry).bounds
    size   = bbox_to_dimensions(BBox(bbox=bounds, crs=CRS.WGS84), resolution=10)

    req = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L2A,
            time_interval=(d_from, d_to),
            mosaicking_order='leastCC',
        )],
        responses=[SentinelHubRequest.output_response("default", mime)],
        geometry=geo,
        size=size,
        config=cfg,
        data_folder=tmp_dir,
    )
    return req.get_data()[0], bounds, size


def _polygon_mask(polygon_coords, bounds, w, h) -> PILImage.Image:
    minx, miny, maxx, maxy = bounds
    mask = PILImage.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    geom = shape({"type": "Polygon", "coordinates": [polygon_coords]})

    def _fill(poly: Polygon):
        pts = [
            ((lon - minx) / (maxx - minx) * w,
             (maxy - lat) / (maxy - miny) * h)
            for lon, lat in poly.exterior.coords
        ]
        draw.polygon(pts, fill=255)
        for interior in poly.interiors:
            draw.polygon(
                [((lon - minx) / (maxx - minx) * w,
                  (maxy - lat) / (maxy - miny) * h)
                 for lon, lat in interior.coords],
                fill=0,
            )

    if isinstance(geom, Polygon):
        _fill(geom)
    elif isinstance(geom, MultiPolygon):
        for p in geom.geoms:
            _fill(p)

    return mask.filter(ImageFilter.GaussianBlur(radius=1))


def _upsample(img: PILImage.Image) -> PILImage.Image:
    w, h = img.size
    if min(w, h) >= MIN_OUTPUT_PX:
        return img
    scale = MIN_OUTPUT_PX / min(w, h)
    return img.resize(
        (max(int(w * scale), MIN_OUTPUT_PX),
         max(int(h * scale), MIN_OUTPUT_PX)),
        PILImage.Resampling.NEAREST,
    )


def _clip_to_polygon(img_rgba: PILImage.Image, mask: PILImage.Image) -> PILImage.Image:
    w, h = img_rgba.size
    if mask.size != (w, h):
        mask = mask.resize((w, h), PILImage.Resampling.NEAREST)
    r, g, b, a = img_rgba.split()
    combined_alpha = PILImage.fromarray(
        np.minimum(np.array(a), np.array(mask)).astype(np.uint8)
    )
    img_rgba.putalpha(combined_alpha)
    return img_rgba


def _to_png_bytes(img: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf.getvalue()


def _fetch_true_color(polygon_coords, bounds, tmp_dir, tok, d_from, d_to):
    arr, _, (nw, nh) = _sh_request(
        polygon_coords, TRUE_COLOR_EVALSCRIPT, MimeType.PNG, tmp_dir, tok, d_from, d_to
    )
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    return PILImage.fromarray(arr.astype(np.uint8), "RGB"), nw, nh


def _draw_polygon_border(img, polygon_coords, bounds, color=(255, 50, 50), width=3):
    minx, miny, maxx, maxy = bounds
    w, h = img.size
    draw = ImageDraw.Draw(img)
    pts = [
        ((lon - minx) / (maxx - minx) * w,
         (maxy - lat) / (maxy - miny) * h)
        for lon, lat in polygon_coords
    ]
    draw.line(pts + [pts[0]], fill=color, width=width)
    return img


def _composite_overlay_on_basemap(basemap_rgb, overlay_rgba, opacity=0.80):
    bm = basemap_rgb.convert("RGBA")
    ov = overlay_rgba.convert("RGBA")
    if bm.size != ov.size:
        ov = ov.resize(bm.size, PILImage.LANCZOS)
    r, g, b, a = ov.split()
    a = a.point(lambda v: int(v * opacity))
    ov = PILImage.merge("RGBA", (r, g, b, a))
    result = bm.copy()
    result.paste(ov, mask=ov.split()[3])
    return result.convert("RGB")


def _kmeans_zone_image(float_arr, polygon_coords, bounds, n_zones=4):
    """
    Returns (zone_rgba_image, zone_pixel_counts).
    zone_pixel_counts: dict {1: int, 2: int, 3: int, 4: int}
    """
    from sklearn.cluster import KMeans

    h, w = float_arr.shape[:2]
    fa   = float_arr if float_arr.ndim == 2 else float_arr[:, :, 0]

    mask_img = _polygon_mask(polygon_coords, bounds, w, h)
    mask     = np.array(mask_img) > 128

    valid_vals  = fa[mask]
    finite_mask = np.isfinite(valid_vals)
    valid_vals  = valid_vals[finite_mask]

    zone_arr    = np.zeros((h, w), dtype=np.uint8)
    zone_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    if len(valid_vals) >= n_zones:
        km = KMeans(n_clusters=n_zones, random_state=42, n_init=10)
        km.fit(valid_vals.reshape(-1, 1))

        centroids = km.cluster_centers_.flatten()
        rank_map  = {
            old: new + 1
            for new, old in enumerate(np.argsort(centroids))
        }

        valid_yx  = np.argwhere(mask)
        finite_yx = valid_yx[finite_mask]
        for idx, (y, x) in enumerate(finite_yx):
            z = rank_map[km.labels_[idx]]
            zone_arr[y, x] = z
            zone_counts[z] = zone_counts.get(z, 0) + 1

    zone_rgba = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    pix = zone_rgba.load()
    for y in range(h):
        for x in range(w):
            z = zone_arr[y, x]
            if z > 0:
                pix[x, y] = ZONE_COLORS[z] + (255,)

    zone_rgba = _upsample(zone_rgba)
    return zone_rgba, zone_counts


# ── Single-index fetch ────────────────────────────────────────────────────

def _fetch_single_index(index_name: str, pc, bounds, tmp_dir, tok, d_from, d_to, mask_native, nw, nh, tc_up):
    """Fetch one index and return (png_bytes, mean_stat)."""
    evalscript = EVALSCRIPTS.get(index_name)
    if not evalscript:
        logger.warning(f"No evalscript for index '{index_name}', skipping.")
        return None, None

    rgb_arr, _, _ = _sh_request(pc, evalscript, MimeType.PNG, tmp_dir, tok, d_from, d_to)

    if rgb_arr.ndim == 2:
        rgb_arr = np.stack([rgb_arr, rgb_arr, rgb_arr], axis=-1)

    rgb_img = PILImage.fromarray(rgb_arr.astype(np.uint8), "RGB").convert("RGBA")
    rgb_up  = _upsample(rgb_img)
    mask_up = _upsample(mask_native)
    clipped = _clip_to_polygon(rgb_up, mask_up)

    if tc_up is not None:
        overlay = _composite_overlay_on_basemap(tc_up.copy(), clipped, opacity=0.85)
        overlay = _draw_polygon_border(overlay, pc, bounds)
        png = _to_png_bytes(overlay)
    else:
        bg = PILImage.new("RGBA", clipped.size, (255, 255, 255, 255))
        bg.paste(clipped, mask=clipped.split()[3])
        png = _to_png_bytes(bg.convert("RGB"))

    return png, None   # mean_stat computed separately from float array for NDVI only


# ── Public entry-point ────────────────────────────────────────────────────

def fetch_ndvi_images(
    polygon_coords: list,
    date_str: str,           # "YYYY-MM-DD"  (use today's date, not sowing_date)
    date_range_days: int = 15,
    indices: list[str] | None = None,   # e.g. ["NDVI"], ["MSAVI","NDVI"], etc.
) -> dict:
    """
    Fetch the requested satellite indices for the given polygon.

    Parameters
    ----------
    polygon_coords  : list of [lon, lat] pairs
    date_str        : centre of the date window (YYYY-MM-DD) — use today's date
    date_range_days : window half-width in days
    indices         : list of index names to fetch (from EVALSCRIPTS keys).
                      Defaults to ["NDVI"] if not provided.

    Returns
    -------
    {
      "index_pngs":  { "NDVI": bytes, "MSAVI": bytes, ... },   # one PNG per index
      "kmeans_png":  bytes,    # K-Means zone map (always NDVI-based)
      "basemap_png": bytes,    # True-colour satellite basemap
      "stats": {
          "ndvi_mean": float,
          "zone_pct":  {1: float, 2: float, 3: float, 4: float},
      },
      "error": str | None,
    }
    """
    if not indices:
        indices = ["NDVI"]

    result = {
        "index_pngs":  {},
        "kmeans_png":  None,
        "basemap_png": None,
        "stats":       {},
        "error":       None,
    }

    # ── Normalise polygon ────────────────────────────────────────────────
    try:
        pc = [[float(c[0]), float(c[1])] for c in polygon_coords]
    except Exception as e:
        result["error"] = f"Bad polygon coords: {e}"
        return result

    if pc[0] != pc[-1]:
        pc.append(pc[0])

    try:
        geom = shape({"type": "Polygon", "coordinates": [pc]})
        if not geom.is_valid:
            result["error"] = "Invalid polygon geometry"
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    # ── Date window ──────────────────────────────────────────────────────
    try:
        dt     = datetime.strptime(date_str, "%Y-%m-%d")
        d_from = (dt - timedelta(days=date_range_days)).strftime("%Y-%m-%d")
        d_to   = (dt + timedelta(days=date_range_days)).strftime("%Y-%m-%d")
    except Exception:
        d_from = "2024-03-01"
        d_to   = "2024-05-30"

    # ── SH token ─────────────────────────────────────────────────────────
    try:
        tok = _get_token()
    except Exception as e:
        result["error"] = f"SH auth failed: {e}"
        return result

    tmp_dir = os.path.join(settings.MEDIA_ROOT, "ndvi_tmp", uuid.uuid4().hex)
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        # ── True-colour basemap ──────────────────────────────────────────
        tc_up = None
        try:
            tc_img, tc_w, tc_h = _fetch_true_color(pc, shape({"type":"Polygon","coordinates":[pc]}).bounds, tmp_dir, tok, d_from, d_to)
            tc_up = _upsample(tc_img)
            result["basemap_png"] = _to_png_bytes(tc_up)
        except Exception as e:
            logger.warning(f"True color fetch failed: {e}")

        # ── Determine bounds & native mask from first index ───────────────
        first_evalscript = EVALSCRIPTS.get(indices[0], EVALSCRIPTS["NDVI"])
        first_arr, bounds, (nw, nh) = _sh_request(
            pc, first_evalscript, MimeType.PNG, tmp_dir, tok, d_from, d_to
        )
        mask_native = _polygon_mask(pc, bounds, nw, nh)

        # ── Fetch each requested index ────────────────────────────────────
        for idx_name in indices:
            try:
                if idx_name == indices[0]:
                    # Re-use already-fetched first_arr
                    arr = first_arr
                else:
                    arr, _, _ = _sh_request(
                        pc, EVALSCRIPTS[idx_name], MimeType.PNG, tmp_dir, tok, d_from, d_to
                    )

                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)

                rgb_img = PILImage.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
                rgb_up  = _upsample(rgb_img)
                mask_up = _upsample(mask_native)
                clipped = _clip_to_polygon(rgb_up, mask_up)

                if tc_up is not None:
                    overlay = _composite_overlay_on_basemap(tc_up.copy(), clipped, opacity=0.85)
                    overlay = _draw_polygon_border(overlay, pc, bounds)
                    png = _to_png_bytes(overlay)
                else:
                    bg = PILImage.new("RGBA", clipped.size, (255, 255, 255, 255))
                    bg.paste(clipped, mask=clipped.split()[3])
                    png = _to_png_bytes(bg.convert("RGB"))

                result["index_pngs"][idx_name] = png
                logger.info(f"Fetched index {idx_name} OK")

            except Exception as e:
                logger.error(f"Failed to fetch {idx_name}: {e}")

        # ── NDVI float array for stats + K-Means (always) ───────────────
        try:
            float_arr, _, _ = _sh_request(
                pc, NDVI_FLOAT_EVALSCRIPT, MimeType.TIFF, tmp_dir, tok, d_from, d_to
            )
            fa      = float_arr if float_arr.ndim == 2 else float_arr[:, :, 0]
            mask_np = np.array(mask_native) > 128
            valid   = fa[mask_np]
            valid   = valid[np.isfinite(valid)]
            result["stats"]["ndvi_mean"] = round(float(np.mean(valid)), 3) if len(valid) else 0.0

            # K-Means — also returns zone pixel counts
            zone_img, zone_pixel_counts = _kmeans_zone_image(float_arr, pc, bounds, n_zones=4)

            # Store raw pixel counts (caller converts to acres using farm.total_acres)
            total_pixels = sum(zone_pixel_counts.values())
            result["stats"]["zone_pixel_counts"] = zone_pixel_counts
            result["stats"]["total_pixels"]      = total_pixels

            zone_mask = _upsample(mask_native)
            zone_img  = _clip_to_polygon(zone_img, zone_mask)

            if tc_up is not None:
                zones_on_map = _composite_overlay_on_basemap(tc_up.copy(), zone_img, opacity=0.75)
                zones_on_map = _draw_polygon_border(zones_on_map, pc, bounds)
                result["kmeans_png"] = _to_png_bytes(zones_on_map)
            else:
                bg2 = PILImage.new("RGBA", zone_img.size, (255, 255, 255, 255))
                bg2.paste(zone_img, mask=zone_img.split()[3])
                result["kmeans_png"] = _to_png_bytes(bg2.convert("RGB"))

        except Exception as e:
            logger.error(f"NDVI float/kmeans fetch failed: {e}")

        logger.info(
            f"fetch_ndvi_images: indices={indices}, "
            f"ndvi_mean={result['stats'].get('ndvi_mean', 'N/A')}"
        )

    except Exception as e:
        logger.error(f"fetch_ndvi_images error: {e}\n{traceback.format_exc()}")
        result["error"] = str(e)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


# ── Backwards-compat alias ────────────────────────────────────────────────
# Old callers that only needed NDVI still work unchanged.
def fetch_ndvi_images_legacy(polygon_coords, date_str, date_range_days=15):
    res = fetch_ndvi_images(polygon_coords, date_str, date_range_days, indices=["NDVI"])
    return {
        "ndvi_png":   res["index_pngs"].get("NDVI"),
        "kmeans_png": res["kmeans_png"],
        "basemap_png": res["basemap_png"],
        "stats":      res["stats"],
        "error":      res["error"],
    }