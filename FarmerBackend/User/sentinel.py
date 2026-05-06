import numpy as np
import os
from PIL import Image, ImageFilter, ImageEnhance
from sentinelhub import (
    SHConfig,
    SentinelHubRequest,
    DataCollection,
    MimeType,
    CRS,
    BBox,
    SentinelHubCatalog
)
from datetime import datetime, timedelta

import cv2

def get_config(client_id, client_secret):
    config = SHConfig()
    config.sh_client_id = client_id
    config.sh_client_secret = client_secret
    return config


def get_latest_date(bbox, config):
    catalog = SentinelHubCatalog(config=config)
    end = datetime.utcnow()
    start = end - timedelta(days=60)

    search = catalog.search(
        DataCollection.SENTINEL2_L2A,
        bbox=bbox,
        time=(start.isoformat(), end.isoformat()),
        filter="eo:cloud_cover < 50",
        fields={"include": ["properties.datetime", "properties.eo:cloud_cover"], "exclude": []}
    )

    results = list(search)

    if not results:
        return None

    results.sort(key=lambda x: x["properties"]["datetime"], reverse=True)
    return results[0]["properties"]["datetime"]

def enhance_satellite_image(image: np.ndarray) -> np.ndarray:
    # Convert to OpenCV BGR
    img_cv = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # Step 1: Upscale 4x using EDSR super resolution style with INTER_CUBIC
    img_cv = cv2.resize(img_cv, (2048, 2048), interpolation=cv2.INTER_CUBIC)

    # Step 2: Bilateral filter - smooths flat regions, preserves edges (key for vector-like look)
    img_cv = cv2.bilateralFilter(img_cv, d=9, sigmaColor=75, sigmaSpace=75)

    # Step 3: Second bilateral pass for stronger smoothing
    img_cv = cv2.bilateralFilter(img_cv, d=7, sigmaColor=60, sigmaSpace=60)

    # Step 4: Convert to LAB color space for better color processing
    lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # Step 5: CLAHE on L channel - adaptive contrast without blowing out colors
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # Step 6: Merge and convert back
    lab = cv2.merge([l, a, b])
    img_cv = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Step 7: Unsharp mask for edge crispness
    gaussian = cv2.GaussianBlur(img_cv, (0, 0), sigmaX=2.0)
    img_cv = cv2.addWeighted(img_cv, 1.6, gaussian, -0.6, 0)

    # Step 8: Morphological closing to fill tiny pixel gaps (vector-like regions)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    img_cv = cv2.morphologyEx(img_cv, cv2.MORPH_CLOSE, kernel)

    # Step 9: Edge detection and enhancement
    edges = cv2.Canny(img_cv, threshold1=30, threshold2=80)
    edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    img_cv = cv2.addWeighted(img_cv, 1.0, edges_colored, 0.08, 0)

    # Step 10: Final bilateral to re-smooth any edge artifacts
    img_cv = cv2.bilateralFilter(img_cv, d=5, sigmaColor=40, sigmaSpace=40)

    # Convert back to RGB PIL
    img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img_rgb)

    # Step 11: PIL color and saturation boost
    img = ImageEnhance.Color(img).enhance(1.5)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Sharpness(img).enhance(1.8)

    # Step 12: Downscale back with LANCZOS
    img = img.resize((512, 512), Image.LANCZOS)

    return np.array(img)

def get_sentinel_image(bbox_coords, client_id, client_secret):
    config = get_config(client_id, client_secret)

    min_lon, min_lat, max_lon, max_lat = bbox_coords

    if abs(min_lat) > 90 or abs(max_lat) > 90:
        min_lon, min_lat, max_lon, max_lat = min_lat, min_lon, max_lat, max_lon

    bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)

    end = datetime.utcnow()
    start = end - timedelta(days=60)

    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input: [{ bands: ["B04", "B03", "B02", "CLM"], units: "DN" }],
            output: { bands: 3, sampleType: "FLOAT32" }
        };
    }
    function evaluatePixel(sample) {
        var r = sample.B04 / 10000.0;
        var g = sample.B03 / 10000.0;
        var b = sample.B02 / 10000.0;

        if (sample.CLM == 1) {
            return [0.8, 0.8, 0.85];
        }
        return [r, g, b];
    }
    """

    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(start.isoformat(), end.isoformat()),
                mosaicking_order="mostRecent",
                maxcc=0.5
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=(512, 512),
        config=config,
    )

    image = request.get_data()[0]

    image_clipped = np.clip(image, 0, 0.3)
    image_gamma = np.power(image_clipped / 0.3, 0.7)
    image_uint8 = (image_gamma * 255).astype(np.uint8)

    image_uint8 = enhance_satellite_image(image_uint8)

    latest_date = get_latest_date(bbox, config)

    return image_uint8, latest_date