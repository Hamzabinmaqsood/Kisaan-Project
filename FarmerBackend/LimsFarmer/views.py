from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from User.models import CustomUser
from rest_framework import serializers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Count, Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from User.models import *
from querry.models import  *
from faq.models import *
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from django.shortcuts import render


def show_kml_page(request):
    return render(request, './admin/mark_kml.html')


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # Additional check to ensure user exists
        if not CustomUser.objects.filter(id=user.id).exists():
            raise serializers.ValidationError("User does not exist.")

        data['user_id'] = user.id
        data['user_role'] = user.role.name if user.role else None

        data['user_name'] = user.username
        return data


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        return data
    
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    

class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer

class TokenVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(True)
   
class DashboardAPIView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request):

        # -----------------------------
        # USER COUNTS BY ROLE
        # -----------------------------
        role_counts = (
            CustomUser.objects
            .values("role__name")
            .annotate(count=Count("id"))
        )
        role_summary = {
            item["role__name"]: item["count"]
            for item in role_counts
        }

        # -----------------------------
        # FARM COUNT
        # -----------------------------
        total_farms = Farms.objects.count()

        # -----------------------------
        # TOTAL ACRES
        # -----------------------------
        total_acres = (
            Farms.objects.aggregate(
                total_acres=Sum("total_acres")
            )["total_acres"] or 0
        )

        # -----------------------------
        # QUERY COUNTS
        # -----------------------------
        total_queries = MediaMessage.objects.count()
        pending_queries = MediaMessage.objects.filter(is_done=False).count()
        responded_queries = MediaMessage.objects.filter(is_done=True).count()

        # -----------------------------
        # ?? ASSIGNED QUERY BREAKDOWN
        # -----------------------------

        # Pending assigned queries (is_done=False)
        pending_assigned_users = (
            AssignedQuery.objects
            .filter(query__is_done=False)
            .values("user__id", "user__username")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Responded assigned queries (is_done=True)
        responded_assigned_users = (
            AssignedQuery.objects
            .filter(query__is_done=True)
            .values("user__id", "user__username")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Optional: Unassigned Queries Count
        unassigned_queries = MediaMessage.objects.filter(
            assignment__isnull=True
        ).count()

        # -----------------------------
        # FAQ COUNTS PER CROP
        # -----------------------------
        crops_with_faq_count = (
            CropType.objects
            .annotate(
                total_faqs=Count("faqs__items", distinct=True),

                active_faqs=Count(
                    "faqs__items",
                    filter=Q(faqs__items__is_active=True),
                    distinct=True
                ),

                inactive_faqs=Count(
                    "faqs__items",
                    filter=Q(faqs__items__is_active=False),
                    distinct=True
                ),
            )
            .values(
                "id",
                "name",
                "total_faqs",
                "active_faqs",
                "inactive_faqs"
            )
        )

        total_crops = crops_with_faq_count.count()

        # -----------------------------
        # OVERALL FAQ TOTALS
        # -----------------------------
        faq_totals = FAQItem.objects.aggregate(
            total_faqs=Count("id"),
            active_faqs=Count("id", filter=Q(is_active=True)),
            inactive_faqs=Count("id", filter=Q(is_active=False)),
        )

        # -----------------------------
        # FINAL RESPONSE
        # -----------------------------
        return Response({

            "users": {
                "total_by_role": role_summary,
            },

            "farms": {
                "total_farms": total_farms,
                "total_acres": float(total_acres),
            },

            "queries": {
                "total_queries": total_queries,
                "pending_queries": pending_queries,
                "responded_queries": responded_queries,
                "unassigned_queries": unassigned_queries,

                # ?? Assigned breakdown
                "pending_assigned_users": list(pending_assigned_users),
                "responded_assigned_users": list(responded_assigned_users),
            },

            "faqs": {
                "total_crops": total_crops,
                "total_faqs": faq_totals["total_faqs"] or 0,
                "active_faqs": faq_totals["active_faqs"] or 0,
                "inactive_faqs": faq_totals["inactive_faqs"] or 0,
                "crop_wise_faq_count": list(crops_with_faq_count),
            }

        })
    

#********************************************************************************************  API FOR REPORT GENERATION *********************************************************************************************************
SH_CLIENT_ID     = '1d22c17c-da52-4417-aaeb-095ffb675bfa'
SH_CLIENT_SECRET = 'vN3Hr02dcndT9bofC7ai86jGKPmiJJs1'

import os
import io
import time
import uuid
import json
import hashlib
import numpy as np
import folium
import base64
import shutil
import requests as http_requests
from datetime import datetime, timedelta
from PIL import Image as PILImage, ImageDraw, ImageFilter
from shapely.geometry import shape, Polygon, MultiPolygon
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from sentinelhub import (
    SHConfig, SentinelHubRequest, DataCollection,
    MimeType, BBox, bbox_to_dimensions, CRS, Geometry
)
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status


SH_TOKEN_URL = 'https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token'

MIN_OUTPUT_PX  = 600
UPSAMPLE_BLUR  = 0.6
CACHE_DAYS     = 7          # images older than this are refreshed

# Root folder where weekly cache is stored
# Structure: CACHE_ROOT / <bbox_hash> / <index_name>.png
#                                     / metadata.json
CACHE_ROOT = os.path.join(settings.MEDIA_ROOT, "indices_cache")


# ---------------------------------------------------------------------------
# Weekly cache helpers
# ---------------------------------------------------------------------------

def _bbox_hash(polygon_coords):
    """
    Stable key derived from the polygon's bounding box, rounded to 6 dp.
    Two polygons with the same bbox share a cache entry.
    """
    lons = [c[0] for c in polygon_coords]
    lats = [c[1] for c in polygon_coords]
    bbox_str = f"{min(lons):.6f},{min(lats):.6f},{max(lons):.6f},{max(lats):.6f}"
    return hashlib.md5(bbox_str.encode()).hexdigest()


def _cache_dir(bbox_key):
    return os.path.join(CACHE_ROOT, bbox_key)


def _metadata_path(bbox_key):
    return os.path.join(_cache_dir(bbox_key), "metadata.json")


def _load_metadata(bbox_key):
    path = _metadata_path(bbox_key)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_metadata(bbox_key, metadata):
    os.makedirs(_cache_dir(bbox_key), exist_ok=True)
    with open(_metadata_path(bbox_key), "w") as f:
        json.dump(metadata, f, indent=2)


def _cached_image_b64(bbox_key, index_name):
    """Return base64 string if a valid (non-expired) cached image exists, else None."""
    metadata = _load_metadata(bbox_key)
    entry = metadata.get(index_name)
    if not entry:
        return None

    fetched_at = datetime.fromisoformat(entry["fetched_at"])
    if datetime.utcnow() - fetched_at > timedelta(days=CACHE_DAYS):
        return None   # expired — caller must re-fetch

    img_path = os.path.join(_cache_dir(bbox_key), f"{index_name}.png")
    if not os.path.exists(img_path):
        return None

    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _write_cache(bbox_key, index_name, png_bytes):
    """Save PNG bytes to cache and update metadata timestamp."""
    cache_dir = _cache_dir(bbox_key)
    os.makedirs(cache_dir, exist_ok=True)

    img_path = os.path.join(cache_dir, f"{index_name}.png")
    with open(img_path, "wb") as f:
        f.write(png_bytes)

    metadata = _load_metadata(bbox_key)
    metadata[index_name] = {"fetched_at": datetime.utcnow().isoformat()}
    _save_metadata(bbox_key, metadata)


def _all_indices_cached(bbox_key):
    """True only when ALL four indices have a valid, non-expired cache entry."""
    for name in EVALSCRIPTS:
        if _cached_image_b64(bbox_key, name) is None:
            return False
    return True


# ---------------------------------------------------------------------------
# Sentinel Hub helpers (unchanged)
# ---------------------------------------------------------------------------

def _get_sentinel_token():
    response = http_requests.post(
        SH_TOKEN_URL,
        data={
            'grant_type':    'client_credentials',
            'client_id':     SH_CLIENT_ID,
            'client_secret': SH_CLIENT_SECRET,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=30,
    )
    print(response.status_code, response.text)
    if response.status_code != 200:
        raise Exception(f"Token fetch failed: {response.status_code} {response.text}")
    return response.json()['access_token']


EVALSCRIPTS = {
    "ndvi": """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B04", "B08"] }],
        output: { bands: 3, sampleType: SampleType.UINT8 }
    };
}
function colorBlend(val) {
    if (val >= 0.95) return [0, 127, 71];
    else if (val >= 0.90) return [6, 150, 84];
    else if (val >= 0.85) return [21, 169, 97];
    else if (val >= 0.80) return [85, 190, 107];
    else if (val >= 0.75) return [119, 202, 112];
    else if (val >= 0.70) return [155, 215, 116];
    else if (val >= 0.65) return [186, 225, 130];
    else if (val >= 0.60) return [212, 239, 150];
    else if (val >= 0.55) return [235, 247, 173];
    else if (val >= 0.50) return [254, 254, 195];
    else if (val >= 0.45) return [255, 237, 171];
    else if (val >= 0.40) return [253, 199, 127];
    else if (val >= 0.35) return [255, 172, 103];
    else if (val >= 0.30) return [255, 139, 87];
    else if (val >= 0.25) return [255, 107, 74];
    else if (val >= 0.20) return [237, 78, 60];
    else if (val >= 0.15) return [226, 43, 45];
    else if (val >= 0.10) return [197, 18, 39];
    else return [171, 0, 41];
}
function evaluatePixel(sample) {
    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
    return colorBlend(ndvi);
}
""",

    "savi": """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B04", "B08"] }],
        output: { bands: 3, sampleType: SampleType.UINT8 }
    };
}
function colorBlendsavi(val) {
    if (val >= 0.70) return [0, 127, 71];
    else if (val >= 0.60) return [6, 150, 84];
    else if (val >= 0.50) return [21, 169, 97];
    else if (val >= 0.40) return [85, 190, 107];
    else if (val >= 0.35) return [119, 202, 112];
    else if (val >= 0.30) return [155, 215, 116];
    else if (val >= 0.27) return [186, 225, 130];
    else if (val >= 0.25) return [212, 239, 150];
    else if (val >= 0.22) return [235, 247, 173];
    else if (val >= 0.20) return [254, 254, 195];
    else if (val >= 0.17) return [255, 237, 171];
    else if (val >= 0.15) return [253, 199, 127];
    else if (val >= 0.12) return [255, 172, 103];
    else if (val >= 0.10) return [255, 139, 87];
    else if (val >= 0.08) return [255, 107, 74];
    else if (val >= 0.06) return [237, 78, 60];
    else if (val >= 0.04) return [226, 43, 45];
    else if (val >= 0.02) return [197, 18, 39];
    else return [171, 0, 41];
}
function evaluatePixel(sample) {
    let L = 0.428;
    let savi = ((sample.B08 - sample.B04) / (sample.B08 + sample.B04 + L)) * (1.0 + L);
    return colorBlendsavi(savi);
}
""",

    "ndmi": """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B08", "B11"] }],
        output: { bands: 3, sampleType: SampleType.UINT8 }
    };
}
function colorBlendndmi(val) {
    if (val >= 0.8)  return [85, 102, 215];
    else if (val >= 0.6)  return [136, 137, 221];
    else if (val >= 0.4)  return [137, 136, 219];
    else if (val >= 0.2)  return [166, 158, 210];
    else if (val >= 0.0)  return [186, 171, 209];
    else if (val >= -0.2) return [211, 186, 194];
    else if (val >= -0.4) return [194, 182, 180];
    else if (val >= -0.6) return [183, 166, 159];
    else if (val >= -0.8) return [182, 156, 149];
    else return [181, 156, 144];
}
function evaluatePixel(sample) {
    let ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
    return colorBlendndmi(ndmi);
}
""",

    "recl": """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B04", "B05"] }],
        output: { bands: 3, sampleType: SampleType.UINT8 }
    };
}
function colorBlendreci(val) {
    if (val >= 9.50) return [0, 127, 71];
    else if (val >= 9.00) return [6, 150, 84];
    else if (val >= 8.50) return [21, 169, 97];
    else if (val >= 8.00) return [85, 190, 107];
    else if (val >= 7.50) return [119, 202, 112];
    else if (val >= 7.00) return [155, 215, 116];
    else if (val >= 6.50) return [186, 225, 130];
    else if (val >= 6.00) return [212, 239, 150];
    else if (val >= 5.50) return [235, 247, 173];
    else if (val >= 5.00) return [254, 254, 195];
    else if (val >= 4.50) return [255, 237, 171];
    else if (val >= 4.00) return [253, 199, 127];
    else if (val >= 3.50) return [255, 172, 103];
    else if (val >= 3.00) return [255, 139, 87];
    else if (val >= 2.50) return [255, 107, 74];
    else if (val >= 2.00) return [237, 78, 60];
    else if (val >= 1.50) return [226, 43, 45];
    else if (val >= 1.00) return [197, 18, 39];
    else return [171, 0, 41];
}
function evaluatePixel(sample) {
    let reci = (sample.B05 / sample.B04) - 1;
    return colorBlendreci(reci);
}
""",
}


def _fetch_index(polygon_coords, evalscript, tmp_folder, access_token):
    config = SHConfig()
    config.sh_client_id     = SH_CLIENT_ID
    config.sh_client_secret = SH_CLIENT_SECRET
    config.sh_token         = access_token

    geometry = Geometry(
        geometry={"type": "Polygon", "coordinates": [polygon_coords]},
        crs=CRS.WGS84
    )

    geom_shape = shape(geometry.geometry)
    bounds     = geom_shape.bounds
    bbox_obj   = BBox(bbox=bounds, crs=CRS.WGS84)
    size       = bbox_to_dimensions(bbox_obj, resolution=10)

    req = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=("2024-03-01", "2024-05-30"),
                mosaicking_order='leastCC'
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.PNG)],
        geometry=geometry,
        size=size,
        config=config,
        data_folder=tmp_folder,
    )

    data = req.get_data()
    arr  = data[0]
    return arr, bounds, size


def _rgb_array_to_rgba_png(arr):
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.shape[2] == 3:
        alpha = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=np.uint8)
        arr   = np.concatenate([arr, alpha], axis=2)
    img = PILImage.fromarray(arr.astype(np.uint8), "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def _upsample_to_min_size(image_bytes, native_w, native_h):
    if min(native_w, native_h) >= MIN_OUTPUT_PX:
        return image_bytes, native_w, native_h
    scale  = MIN_OUTPUT_PX / min(native_w, native_h)
    new_w  = max(int(native_w * scale), MIN_OUTPUT_PX)
    new_h  = max(int(native_h * scale), MIN_OUTPUT_PX)
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = img.resize((new_w, new_h), PILImage.Resampling.BICUBIC)
    if UPSAMPLE_BLUR > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=UPSAMPLE_BLUR))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue(), new_w, new_h


def _clip_to_polygon(image_bytes, polygon_coords, image_bounds, width, height):
    SUPERSAMPLE = 4
    BLUR_RADIUS = 2.0
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), PILImage.Resampling.LANCZOS)
    minx, miny, maxx, maxy = image_bounds
    hi_w = width  * SUPERSAMPLE
    hi_h = height * SUPERSAMPLE

    def geo_to_hires(lon, lat):
        px = (lon - minx) / (maxx - minx) * hi_w
        py = (maxy - lat) / (maxy - miny) * hi_h
        return (px, py)

    geom    = shape({"type": "Polygon", "coordinates": [polygon_coords]})
    hi_mask = PILImage.new("L", (hi_w, hi_h), 0)
    draw    = ImageDraw.Draw(hi_mask)

    def _fill_poly(polygon):
        exterior_pts = [geo_to_hires(lon, lat) for lon, lat in polygon.exterior.coords]
        draw.polygon(exterior_pts, fill=255)
        for interior in polygon.interiors:
            draw.polygon([geo_to_hires(lon, lat) for lon, lat in interior.coords], fill=0)

    if isinstance(geom, Polygon):
        _fill_poly(geom)
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            _fill_poly(poly)

    hi_mask     = hi_mask.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
    smooth_mask = hi_mask.resize((width, height), PILImage.Resampling.LANCZOS)
    r, g, b, a  = img.split()
    combined_alpha = PILImage.fromarray(
        np.minimum(np.array(a), np.array(smooth_mask)).astype(np.uint8)
    )
    img.putalpha(combined_alpha)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _overlay_on_google_map(png_bytes, polygon_coords, image_bounds, output_path):
    minx, miny, maxx, maxy = image_bounds
    tmp_png = output_path.replace(".png", "_tmp.png")
    with open(tmp_png, "wb") as f:
        f.write(png_bytes)

    m = folium.Map(
        location=[(miny + maxy) / 2, (minx + maxx) / 2],
        zoom_start=17,
        control_scale=True,
    )
    folium.raster_layers.TileLayer(
        tiles='https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        subdomains=['mt0', 'mt1', 'mt2', 'mt3'],
        overlay=False,
        control=True,
    ).add_to(m)

    folium_bounds = [[miny, minx], [maxy, maxx]]
    folium.raster_layers.ImageOverlay(
        name='Index Overlay',
        image=tmp_png,
        bounds=folium_bounds,
        opacity=0.9,
        interactive=True,
        cross_origin=False,
    ).add_to(m)
    folium.Polygon(
        locations=[[lat, lon] for lon, lat in polygon_coords],
        color='#ff2222',
        weight=2,
        fill=False,
        opacity=0.9,
    ).add_to(m)
    m.fit_bounds(folium_bounds)

    html_path = output_path.replace(".png", "_map.html")
    m.save(html_path)
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1100,900')

    # options = Options()
    # options.add_argument('--headless')
    # options.add_argument('--no-sandbox')
    # options.add_argument('--disable-dev-shm-usage')
    # options.add_argument('--window-size=1100,900')
    driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)
    # driver = webdriver.Chrome(options=options)
    try:
        driver.get("file://" + os.path.abspath(html_path))
        time.sleep(4)
        driver.save_screenshot(output_path)
    finally:
        driver.quit()
        for f in [tmp_png, html_path]:
            try:
                os.remove(f)
            except Exception:
                pass


def _fetch_and_cache_index(index_name, evalscript, polygon_coords, bbox_key, access_token, tmp_dir):
    """
    Full pipeline for one index: fetch → process → write to persistent cache.
    Returns base64 string of the final overlay PNG.
    """
    arr, bounds, size = _fetch_index(polygon_coords, evalscript, tmp_dir, access_token)
    native_w, native_h = size

    png_bytes = _rgb_array_to_rgba_png(arr)
    png_bytes, out_w, out_h = _upsample_to_min_size(png_bytes, native_w, native_h)
    clipped = _clip_to_polygon(png_bytes, polygon_coords, bounds, out_w, out_h)

    tmp_out = os.path.join(tmp_dir, f"{index_name}_overlay.png")
    _overlay_on_google_map(clipped, polygon_coords, bounds, tmp_out)

    with open(tmp_out, "rb") as f:
        overlay_bytes = f.read()

    # Overwrite any stale cache entry
    _write_cache(bbox_key, index_name, overlay_bytes)

    return base64.b64encode(overlay_bytes).decode("utf-8")


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

@api_view(['POST'])
def generate_indices_report(request):
    """
    POST body:  { "polygon": [[lon, lat], ...] }

    Cache behaviour:
      • Cache key = MD5 of the polygon's bounding box (rounded to 6 dp).
      • If ALL four index PNGs exist and are < 7 days old → return from cache.
      • Otherwise fetch only the missing/expired indices from Sentinel Hub,
        save them, and return all four.
      • After 7 days the next request silently replaces the stale images.

    Response fields:
      ndvi, savi, ndmi, recl  – base64 PNG strings
      source                  – "cache" or "sentinel_hub"
      cached_at               – ISO UTC datetime when the images were stored
    """

    # --- validate polygon ---------------------------------------------------
    polygon_coords = request.data.get("polygon")
    if not polygon_coords or not isinstance(polygon_coords, list) or len(polygon_coords) < 3:
        return Response(
            {"error": "Provide 'polygon' as a list of at least 3 [lon, lat] pairs."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        polygon_coords = [[float(c[0]), float(c[1])] for c in polygon_coords]
    except (TypeError, ValueError, IndexError):
        return Response(
            {"error": "Each coordinate must be a [lon, lat] numeric pair."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if polygon_coords[0] != polygon_coords[-1]:
        polygon_coords.append(polygon_coords[0])

    try:
        geom_check = shape({"type": "Polygon", "coordinates": [polygon_coords]})
        if not geom_check.is_valid:
            return Response(
                {"error": "Polygon is invalid (self-intersecting?)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Exception as e:
        return Response({"error": f"Polygon parse error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    # --- check weekly cache -------------------------------------------------
    bbox_key = _bbox_hash(polygon_coords)

    if _all_indices_cached(bbox_key):
        result    = {name: _cached_image_b64(bbox_key, name) for name in EVALSCRIPTS}
        metadata  = _load_metadata(bbox_key)
        oldest    = min(metadata[n]["fetched_at"] for n in EVALSCRIPTS if n in metadata)
        result["source"]    = "cache"
        result["cached_at"] = oldest
        return Response(result, status=status.HTTP_200_OK)

    # --- fetch missing / expired indices ------------------------------------
    try:
        access_token = _get_sentinel_token()
    except Exception as e:
        return Response(
            {"error": f"Sentinel Hub authentication failed: {str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    session_id = uuid.uuid4().hex
    tmp_dir    = os.path.join(settings.MEDIA_ROOT, "indices_tmp", session_id)
    os.makedirs(tmp_dir, exist_ok=True)

    result_images = {}

    try:
        for index_name, evalscript in EVALSCRIPTS.items():

            # Reuse any index that is still fresh
            cached_b64 = _cached_image_b64(bbox_key, index_name)
            if cached_b64 is not None:
                result_images[index_name] = cached_b64
                continue

            try:
                result_images[index_name] = _fetch_and_cache_index(
                    index_name, evalscript, polygon_coords, bbox_key, access_token, tmp_dir
                )
            except Exception as e:
                return Response(
                    {"error": f"Failed for {index_name}: {str(e)}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    metadata  = _load_metadata(bbox_key)
    newest    = max(metadata[n]["fetched_at"] for n in EVALSCRIPTS if n in metadata)
    result_images["source"]    = "sentinel_hub"
    result_images["cached_at"] = newest
    return Response(result_images, status=status.HTTP_200_OK)
