import os
import asyncio
import base64
import logging
import requests
import numpy as np
import hashlib
import json
import random

from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import JSONParser

from django.conf import settings

from deep_translator import GoogleTranslator
import edge_tts
from rest_framework.permissions import IsAuthenticated
from .models import SentinelIndexCache
from User.models import *
logger = logging.getLogger(__name__)

SENTINEL_CLIENT_ID = "854f6aa8-67cc-4e2d-b438-680aa3d04c17"
SENTINEL_CLIENT_SECRET = "tFIvAxQlDgF8WQoaMuhWhAGxm4V7d9Ye"


# ---------------------------------------------------
# EDGE TTS
# ---------------------------------------------------
async def generate_urdu_tts_async(text, output_path):
    communicate = edge_tts.Communicate(
        text=text,
        voice="ur-PK-AsadNeural",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz"
    )
    await communicate.save(output_path)
    await asyncio.sleep(random.uniform(0.3, 0.6))


def generate_urdu_tts(text, output_path):
    """
    Safe wrapper for Django (handles running event loop)
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        asyncio.create_task(generate_urdu_tts_async(text, output_path))
    else:
        asyncio.run(generate_urdu_tts_async(text, output_path))


# ---------------------------------------------------
# MAIN API
# ---------------------------------------------------
class GenerateWithNDVIView(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]  
    def post(self, request):
        try:
            bbox = request.data.get("bbox", [])
            index_type = request.data.get("index", "ndvi").lower()
            farm_id = request.data.get("farm_id", None)
            farm = Farms.objects.get(id=farm_id)

            if not bbox or len(bbox) != 4:
                return Response({"success": False, "error": "Invalid bbox"}, status=400)

            if index_type not in ["ndvi", "savi", "ndmi", "ndre", "reci"]:
                return Response({"success": False, "error": "Invalid index"}, status=400)

            # Normalize bbox to avoid micro-float differences breaking cache
            bbox = [round(float(x), 6) for x in bbox]

            bbox_hash = self._bbox_hash(bbox)
            today = datetime.utcnow().date()
            area_acres = self._calculate_area(bbox)

            # ---------------------------------------------------
            # 🔍 CHECK DATABASE CACHE
            # ---------------------------------------------------
            cached = SentinelIndexCache.objects.filter(
                farm_id = farm.id,
                index_type=index_type,
                bbox_hash=bbox_hash,
                date=today
            ).first()

            if cached:
                logger.info("✅ DATA SERVED FROM DATABASE CACHE")
                return self._build_response(
                    image_base64=cached.image_base64,
                    stats=cached.statistics,
                    bbox=bbox,
                    area_acres=area_acres,
                    index_type=index_type,
                    cached=True,
                    audio_file=cached.audio_file
                )

            # ---------------------------------------------------
            # 🌍 FETCH FROM SENTINEL
            # ---------------------------------------------------
            token = self._get_sentinel_token()
            if not token:
                return Response({"success": False, "error": "Auth failed"}, status=500)

            image_base64 = self._fetch_index_data(token, bbox, index_type)
            if not image_base64:
                return Response({"success": False, "error": "Sentinel fetch failed"}, status=500)

            stats = self._analyze_index_colors(image_base64, index_type)

            # ---------------------------------------------------
            # 📝 Build response ONCE (this will create audio file too)
            # ---------------------------------------------------
            response_data, audio_filename = self._build_response_data(
                image_base64=image_base64,
                stats=stats,
                bbox=bbox,
                area_acres=area_acres,
                index_type=index_type,
                cached=False,
                audio_file=None
            )

            # ---------------------------------------------------
            # 💾 SAVE TO DATABASE (INCLUDING AUDIO FILE NAME)
            # ---------------------------------------------------
            SentinelIndexCache.objects.create(
                farm_id = farm,
                index_type=index_type,
                bbox_hash=bbox_hash,
                bbox=bbox,
                date=today,
                image_base64=image_base64,
                statistics=stats,
                audio_file=audio_filename
            )

            return Response(response_data, status=200)

        except Exception as e:
            logger.error(str(e), exc_info=True)
            return Response({"success": False, "error": str(e)}, status=500)

    # ---------------------------------------------------
    # ✅ RESPONSE BUILDER (CACHED PATH USES THIS)
    # ---------------------------------------------------
    def _build_response(self, image_base64, stats, bbox, area_acres, index_type, cached, audio_file=None):
        response_data, _ = self._build_response_data(
            image_base64=image_base64,
            stats=stats,
            bbox=bbox,
            area_acres=area_acres,
            index_type=index_type,
            cached=cached,
            audio_file=audio_file
        )
        return Response(response_data, status=200)

    # ---------------------------------------------------
    # ✅ REAL RESPONSE DATA GENERATOR (USED BY BOTH PATHS)
    # Returns: (dict, audio_filename_or_none)
    # ---------------------------------------------------
    def _build_response_data(self, image_base64, stats, bbox, area_acres, index_type, cached, audio_file=None):
        dominant_category = stats["dominant_category"]
        dominant_percentage = stats[dominant_category]

        english_text = self._generate_index_report(
            area_acres, stats, dominant_category, dominant_percentage, index_type
        )

        urdu_text = GoogleTranslator(source="en", target="ur").translate(english_text)

        # ---------------------------------------------------
        # 🔊 VOICE LOGIC (DON'T RE-GENERATE IF CACHED)
        # ---------------------------------------------------
        audio_filename = None
        if cached and audio_file:
            audio_filename = audio_file
        else:
            audio_filename = f"urdu_{int(datetime.now().timestamp())}.mp3"
            audio_dir = os.path.join(settings.MEDIA_ROOT, "audio")
            os.makedirs(audio_dir, exist_ok=True)
            audio_path = os.path.join(audio_dir, audio_filename)
            generate_urdu_tts(urdu_text, audio_path)

        audio_url = f"/media/audio/{audio_filename}" if audio_filename else None

        sync_data = self._generate_sync_data_single_color(urdu_text, dominant_category)

        payload = {
            "success": True,
            "cached": cached,
            "index_type": index_type.upper(),
            "english_text": english_text,
            "urdu_text": urdu_text,
            "audio_url": audio_url,
            "sync_data": sync_data,
            "index_data": {
                "image_base64": image_base64,
                "statistics": stats,
                "bbox": bbox,
                "area_acres": round(area_acres, 2),
                "dominant_category": dominant_category,
                "dominant_percentage": round(dominant_percentage, 1)
            },
            "timestamp": datetime.now().isoformat()
        }

        return payload, audio_filename

    # ---------------------------------------------------
    # HELPERS
    # ---------------------------------------------------
    def _bbox_hash(self, bbox):
        bbox_str = json.dumps(bbox, sort_keys=True)
        return hashlib.sha256(bbox_str.encode()).hexdigest()

    def _calculate_area(self, bbox):
        lat_diff = abs(bbox[3] - bbox[1])
        lon_diff = abs(bbox[2] - bbox[0])
        avg_lat = (bbox[1] + bbox[3]) / 2
        area_km2 = (lat_diff * 111) * (lon_diff * 111 * np.cos(np.radians(avg_lat)))
        return area_km2 * 247.105  # acres

    def _get_sentinel_token(self):
        r = requests.post(
            "https://services.sentinel-hub.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": SENTINEL_CLIENT_ID,
                "client_secret": SENTINEL_CLIENT_SECRET
            }
        )
        return r.json().get("access_token") if r.status_code == 200 else None

    def _get_sentinel_token(self):
        r = requests.post(
            "https://services.sentinel-hub.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": SENTINEL_CLIENT_ID,
                "client_secret": SENTINEL_CLIENT_SECRET
            }
        )
        return r.json().get("access_token") if r.status_code == 200 else None

    # 👉 ALL YOUR evalscript, fetch, analyze, report & sync
    # 👉 METHODS REMAIN EXACTLY THE SAME AS YOU POSTED
    # 👉 (No logic changes needed for TTS)


    
    def _get_evalscript(self, index_type):
        """Get evalscript with EXACT color schemes"""
        
        if index_type == 'ndvi':
            return """
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
"""
        
        elif index_type == 'savi':
            return """
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
"""
        
        elif index_type == 'ndmi':
            return """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B08", "B11"] }],
        output: { bands: 3, sampleType: SampleType.UINT8 }
    };
}

function colorBlendndmi(val) {
    if (val >= 0.8) return [85, 102, 215];
    else if (val >= 0.6) return [136, 137, 221];
    else if (val >= 0.4) return [137, 136, 219];
    else if (val >= 0.2) return [166, 158, 210];
    else if (val >= 0.0) return [186, 171, 209];
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
"""
        
        elif index_type == 'ndre':
            return """
//VERSION=3
function setup() {
    return {
        input: [{ bands: ["B05", "B08"] }],
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
    let ndre = (sample.B08 - sample.B05) / (sample.B08 + sample.B05);
    return colorBlend(ndre);
}
"""
        
        elif index_type == 'reci':
            return """
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
"""
        
        return None
    
    def _fetch_index_data(self, token, bbox, index_type):
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            evalscript = self._get_evalscript(index_type)
            if not evalscript:
                return None
            
            response = requests.post(
                "https://services.sentinel-hub.com/api/v1/process",
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    "input": {
                        "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
                        "data": [{
                            "type": "sentinel-2-l2a",
                            "dataFilter": {
                                "timeRange": {
                                    "from": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                                    "to": end_date.strftime("%Y-%m-%dT23:59:59Z")
                                },
                                "maxCloudCoverage": 30
                            }
                        }]
                    },
                    "output": {
                        "width": 512,
                        "height": 512,
                        "responses": [{"identifier": "default", "format": {"type": "image/png"}}]
                    },
                    "evalscript": evalscript
                }
            )
            return base64.b64encode(response.content).decode('utf-8') if response.status_code == 200 else None
        except:
            return None
    
    def _analyze_index_colors(self, image_base64, index_type):
        """Analyze colors based on index type"""
        try:
            image_data = base64.b64decode(image_base64)
            img = Image.open(BytesIO(image_data)).convert('RGB')
            img_array = np.array(img)
            
            total_pixels = img_array.shape[0] * img_array.shape[1]
            
            if index_type == 'ndmi':
                # NDMI uses blue/purple colors (moisture)
                return self._analyze_ndmi_colors(img_array, total_pixels)
            else:
                # NDVI, SAVI, NDRE, RECI use green/yellow/red
                return self._analyze_vegetation_colors(img_array, total_pixels)
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            return {
                'dense_vegetation': 5.0,
                'moderate_vegetation': 15.0,
                'sparse_vegetation': 70.0,
                'open_soil': 10.0,
                'avg_value': 0.25,
                'dominant_category': 'sparse_vegetation'
            }
    
    def _analyze_ndmi_colors(self, img_array, total_pixels):
        """NDMI: Blue/purple = high moisture, Brown = low moisture"""
        high_moisture = 0
        moderate_moisture = 0
        low_moisture = 0
        very_low_moisture = 0
        
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                r, g, b = img_array[i, j]
                
                # High moisture (blue/purple shades)
                if b > 180 and b > r and b > g:
                    high_moisture += 1
                # Moderate moisture (purple/pink)
                elif (r > 150 and b > 150) or (r > 130 and g > 130 and b > 130):
                    moderate_moisture += 1
                # Low moisture (brown/tan)
                elif r > 160 and g > 140 and b < 160:
                    low_moisture += 1
                else:
                    very_low_moisture += 1
        
        return {
            'dense_vegetation': (high_moisture / total_pixels) * 100,
            'moderate_vegetation': (moderate_moisture / total_pixels) * 100,
            'sparse_vegetation': (low_moisture / total_pixels) * 100,
            'open_soil': (very_low_moisture / total_pixels) * 100,
            'avg_value': (high_moisture * 0.8 + moderate_moisture * 0.5 + low_moisture * 0.2) / total_pixels,
            'dominant_category': max([
                ('dense_vegetation', (high_moisture / total_pixels) * 100),
                ('moderate_vegetation', (moderate_moisture / total_pixels) * 100),
                ('sparse_vegetation', (low_moisture / total_pixels) * 100),
                ('open_soil', (very_low_moisture / total_pixels) * 100)
            ], key=lambda x: x[1])[0]
        }
    
    def _analyze_vegetation_colors(self, img_array, total_pixels):
        """NDVI/SAVI/NDRE/RECI: Green = dense, Yellow = moderate, Red = sparse"""
        dense_count = 0
        moderate_count = 0
        sparse_count = 0
        soil_count = 0
        
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                r, g, b = img_array[i, j]
                
                # Dense (Green)
                if (g >= 100 and g > r * 1.2 and g > b):
                    dense_count += 1
                # Moderate (Yellow)
                elif (r >= 200 and g >= 180) or (r >= 180 and g >= 170 and abs(r-g) < 80):
                    moderate_count += 1
                # Sparse (Red/Orange)
                elif (r >= 170 and r > g * 1.3):
                    sparse_count += 1
                else:
                    soil_count += 1
        
        stats = {
            'dense_vegetation': (dense_count / total_pixels) * 100,
            'moderate_vegetation': (moderate_count / total_pixels) * 100,
            'sparse_vegetation': (sparse_count / total_pixels) * 100,
            'open_soil': (soil_count / total_pixels) * 100,
        }
        
        stats['avg_value'] = (
            (stats['dense_vegetation'] * 0.80) +
            (stats['moderate_vegetation'] * 0.52) +
            (stats['sparse_vegetation'] * 0.28) +
            (stats['open_soil'] * 0.10)
        ) / 100
        
        stats['dominant_category'] = max(stats, key=lambda k: stats[k] if k != 'avg_value' else 0)
        
        return stats
    
    def _generate_index_report(self, area_acres, stats, dominant_category, dominant_percentage, index_type):
        """Generate report based on index type"""
        script_parts = [f"Your total field area is {area_acres:.1f} acres."]
        
        # Index-specific messages
        index_messages = {
            'ndvi': {
                'dense_vegetation': f"NDVI shows {dominant_percentage:.1f} percent dense green vegetation with excellent crop health.",
                'moderate_vegetation': f"NDVI shows {dominant_percentage:.1f} percent moderate yellow vegetation needing attention.",
                'sparse_vegetation': f"NDVI shows {dominant_percentage:.1f} percent sparse red vegetation under stress.",
                'open_soil': f"NDVI shows {dominant_percentage:.1f} percent open soil."
            },
            'savi': {
                'dense_vegetation': f"SAVI index shows {dominant_percentage:.1f} percent dense vegetation.",
                'moderate_vegetation': f"SAVI index shows {dominant_percentage:.1f} percent moderate vegetation.",
                'sparse_vegetation': f"SAVI index shows {dominant_percentage:.1f} percent sparse vegetation.",
                'open_soil': f"SAVI index shows {dominant_percentage:.1f} percent bare soil."
            },
            'ndmi': {
                'dense_vegetation': f"Moisture index shows {dominant_percentage:.1f} percent high water content. Well-irrigated.",
                'moderate_vegetation': f"Moisture index shows {dominant_percentage:.1f} percent moderate water content.",
                'sparse_vegetation': f"Moisture index shows {dominant_percentage:.1f} percent low water content. Water stress detected.",
                'open_soil': f"Moisture index shows {dominant_percentage:.1f} percent very low moisture."
            },
            'ndre': {
                'dense_vegetation': f"Red Edge NDVI shows {dominant_percentage:.1f} percent high chlorophyll content.",
                'moderate_vegetation': f"Red Edge NDVI shows {dominant_percentage:.1f} percent moderate chlorophyll.",
                'sparse_vegetation': f"Red Edge NDVI shows {dominant_percentage:.1f} percent low chlorophyll.",
                'open_soil': f"Red Edge NDVI shows {dominant_percentage:.1f} percent minimal vegetation."
            },
            'reci': {
                'dense_vegetation': f"Chlorophyll index shows {dominant_percentage:.1f} percent healthy vegetation.",
                'moderate_vegetation': f"Chlorophyll index shows {dominant_percentage:.1f} percent moderate chlorophyll levels.",
                'sparse_vegetation': f"Chlorophyll index shows {dominant_percentage:.1f} percent low chlorophyll. Fertilizer needed.",
                'open_soil': f"Chlorophyll index shows {dominant_percentage:.1f} percent bare soil."
            }
        }
        
        script_parts.append(index_messages[index_type][dominant_category])
        
        # Critical issues
        critical = []
        if stats['dense_vegetation'] < 5 and dominant_category != 'dense_vegetation':
            critical.append("almost no dense vegetation")
        if stats['sparse_vegetation'] > 30 and dominant_category != 'sparse_vegetation':
            critical.append(f"{stats['sparse_vegetation']:.1f} percent shows stress")
        if stats['open_soil'] > 15 and dominant_category != 'open_soil':
            critical.append(f"{stats['open_soil']:.1f} percent is bare soil")
        
        if critical:
            script_parts.append("However, " + " and ".join(critical) + ".")
        
        # Recommendation
        avg_val = stats['avg_value']
        if avg_val > 0.65:
            script_parts.append("Continue current management practices.")
        elif avg_val > 0.45:
            script_parts.append("Consider irrigation and fertilization.")
        elif avg_val > 0.25:
            script_parts.append("Immediate intervention required.")
        else:
            script_parts.append("Critical condition requiring urgent action.")
        
        return " ".join(script_parts)
    
    def _generate_sync_data_single_color(self, urdu_text, dominant_category):
        words = urdu_text.split()
        time_per_word = 12 / len(words) if words else 0.5
        
        color_map = {
            'dense_vegetation': 'dense_green',
            'moderate_vegetation': 'moderate_yellow',
            'sparse_vegetation': 'sparse_red',
            'open_soil': 'sparse_red'
        }
        
        dominant_color = color_map.get(dominant_category, 'sparse_red')
        
        sync_data = []
        current_time = 0.0
        
        for word in words:
            sync_data.append({
                'word': word,
                'color': dominant_color,
                'category': dominant_category,
                'start_time': round(current_time, 2),
                'duration': round(time_per_word, 2)
            })
            current_time += time_per_word
        
        return sync_data