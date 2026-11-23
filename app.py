from datetime import date, datetime, timedelta
import math
from flask import Flask, jsonify, render_template, request
import requests
from fruits_data import CITIES, ENVIRONMENT_FACTORS, FRUITS_DB

app = Flask(__name__)

WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def fetch_weather_advice(city_key: str = "miaoli") -> dict:
    """呼叫免金鑰公開 API Open-Meteo 取得當地今日氣候與播種建議"""
    city = CITIES.get(city_key, CITIES["miaoli"])
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": "temperature_2m,relative_humidity_2m",
        "daily": "precipitation_probability_max",
        "timezone": "Asia/Taipei",
        "forecast_days": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        temp = data.get("current", {}).get("temperature_2m")
        humidity = data.get("current", {}).get("relative_humidity_2m")
        rain_probs = data.get("daily", {}).get("precipitation_probability_max", [])
        rain_prob = rain_probs[0] if rain_probs else None

        if temp is not None and temp < 15:
            advice = "今日氣溫偏低，播種後建議覆蓋保鮮膜或移至室內窗邊保溫催芽。"
        elif rain_prob is not None and rain_prob >= 60:
            advice = "今日降雨機率較高，露天盆栽請注意盆底排水，避免種子泡水腐爛。"
        elif temp is not None and temp > 32:
            advice = "今日氣溫較高，播種後請放置半陰通風處並早晚噴霧保濕。"
        else:
            advice = "今日溫濕度適中，非常適合進行播種、浸種催芽與幼苗換盆！"

        return {
            "ok": True,
            "city": city["name"],
            "temp": temp,
            "humidity": humidity,
            "rain_prob": rain_prob,
            "advice": advice,
        }
    except (requests.RequestException, ValueError, KeyError):
        return {
            "ok": False,
            "city": city["name"],
            "advice": "目前無法取得即時氣象資料（外部 API 連線逾時），不影響成熟日期計算。",
        }


def calculate_harvest(
    fruit_key: str,
    plant_date_str: str,
    env_key: str = "outdoor",
    custom_name: str = "",
    custom_days: int | None = None,
) -> tuple[dict | None, str | None]:
    """核心日期計算與生長階段拆解"""
    try:
        plant_date = datetime.strptime(plant_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None, "請輸入有效的播種日期（格式：YYYY-MM-DD）。"

    env = ENVIRONMENT_FACTORS.get(env_key, ENVIRONMENT_FACTORS["outdoor"])

    if fruit_key == "custom":
        if not custom_days or custom_days <= 0 or custom_days > 5000:
            return None, "自訂成熟天數請輸入 1 到 5000 之間的整數。"
        fruit_info = {
            "name": custom_name.strip() or "自訂水果",
            "category": "自訂作物",
            "days": custom_days,
            "sunlight": "請依該品種特性提供充足日照",
            "watering": "保持土壤微濕、排水良好",
            "tip": "建議記錄實際發芽與開花日期，逐步微調專屬種植筆記。",
        }
    else:
        fruit_info = FRUITS_DB.get(fruit_key)
        if not fruit_info:
            return None, "找不到選擇的水果項目，請重新選擇。"

    adjusted_days = max(1, math.ceil(fruit_info["days"] * env["multiplier"]))
    harvest_date = plant_date + timedelta(days=adjusted_days)
    today = date.today()
    days_remaining = (harvest_date - today).days
    days_elapsed = (today - plant_date).days

    stage_specs = [
        ("1. 播種發芽期", 0.0, 0.15, "種子吸水膨脹、破殼長出子葉"),
        ("2. 幼苗生長期", 0.15, 0.50, "根系擴展、本葉快速增多與枝葉抽長"),
        ("3. 開花授粉期", 0.50, 0.75, "花芽分化、開花並完成授粉著果"),
        ("4. 結果成熟期", 0.75, 1.00, "果實膨大、轉色累積糖分至可採收"),
    ]
    stages = []
    for title, start_ratio, end_ratio, desc in stage_specs:
        s_date = plant_date + timedelta(days=round(adjusted_days * start_ratio))
        e_date = plant_date + timedelta(days=round(adjusted_days * end_ratio))
        stages.append({
            "title": title,
            "start": s_date.strftime("%Y-%m-%d"),
            "end": e_date.strftime("%Y-%m-%d"),
            "desc": desc,
        })

    if days_elapsed <= 0:
        progress = 0
    elif days_elapsed >= adjusted_days:
        progress = 100
    else:
        progress = round((days_elapsed / adjusted_days) * 100)

    return {
        "fruit_name": fruit_info["name"],
        "category": fruit_info["category"],
        "base_days": fruit_info["days"],
        "adjusted_days": adjusted_days,
        "env_label": env["label"],
        "plant_date": plant_date.strftime("%Y-%m-%d"),
        "plant_weekday": WEEKDAYS_ZH[plant_date.weekday()],
        "harvest_date": harvest_date.strftime("%Y-%m-%d"),
        "harvest_weekday": WEEKDAYS_ZH[harvest_date.weekday()],
        "days_remaining": days_remaining,
        "progress": progress,
        "sunlight": fruit_info["sunlight"],
        "watering": fruit_info["watering"],
        "tip": fruit_info["tip"],
        "stages": stages,
    }, None


@app.route("/", methods=["GET", "POST"])
def index():
    today_str = date.today().strftime("%Y-%m-%d")
    selected_fruit = "cherry_tomato"
    selected_env = "outdoor"
    selected_city = "miaoli"
    plant_date_str = today_str
    custom_name = ""
    custom_days = ""
    result = None
    error = None

    if request.method == "POST":
        selected_fruit = request.form.get("fruit", "cherry_tomato")
        selected_env = request.form.get("env", "outdoor")
        selected_city = request.form.get("city", "miaoli")
        plant_date_str = request.form.get("plant_date", today_str)
        custom_name = request.form.get("custom_name", "")
        custom_days_raw = request.form.get("custom_days", "").strip()
        custom_days = custom_days_raw

        parsed_custom_days = None
        if selected_fruit == "custom":
            try:
                parsed_custom_days = int(custom_days_raw)
            except ValueError:
                parsed_custom_days = None

        result, error = calculate_harvest(
            fruit_key=selected_fruit,
            plant_date_str=plant_date_str,
            env_key=selected_env,
            custom_name=custom_name,
            custom_days=parsed_custom_days,
        )

    weather = fetch_weather_advice(selected_city)

    return render_template(
        "index.html",
        fruits=FRUITS_DB,
        environments=ENVIRONMENT_FACTORS,
        cities=CITIES,
        selected_fruit=selected_fruit,
        selected_env=selected_env,
        selected_city=selected_city,
        plant_date=plant_date_str,
        custom_name=custom_name,
        custom_days=custom_days,
        result=result,
        error=error,
        weather=weather,
    )


@app.get("/api/fruits")
def api_fruits():
    return jsonify({"fruits": FRUITS_DB, "environments": ENVIRONMENT_FACTORS})


@app.post("/api/calculate")
def api_calculate():
    payload = request.get_json(silent=True) or {}
    result, error = calculate_harvest(
        fruit_key=payload.get("fruit", ""),
        plant_date_str=payload.get("plant_date", ""),
        env_key=payload.get("env", "outdoor"),
        custom_name=payload.get("custom_name", ""),
        custom_days=payload.get("custom_days"),
    )
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "result": result})


if __name__ == "__main__":
    app.run(debug=True)
