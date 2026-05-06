import requests
from datetime import date
from .models import MandiDailyData


def fetch_and_save_mandi(for_date=None):
    if for_date is None:
        for_date = date.today()

    url = f"http://amis.pk/Androidforpitb/Prices.ashx?date={for_date}&Depart=LIMS"

    r = requests.get(url, timeout=60)
    r.raise_for_status()

    api_data = r.json()  # full list

    obj, created = MandiDailyData.objects.update_or_create(
        date=for_date,
        defaults={"data": api_data}
    )

    return {
        "date": str(for_date),
        "total_records": len(api_data),
        "created": created
    }
