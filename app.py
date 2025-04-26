from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, CarouselTemplate, CarouselColumn, MessageAction
import requests
import json
import re
from tinydb import TinyDB, Query
from datetime import datetime

# 初始化
app = Flask(__name__)
line_bot_api = LineBotApi('aGpYRbppqiGEdWyqMRXLjl0bAoh1TH0v23yQ9AZ6r6SkIukuuvyNTiqWpdG+tCZPoeUoLJnAfR0TgJJP/q1RBqMKE2a8Dv6fBz7YbFhAODYbyOh6vnc8s+fZpf31S9C2SaLdzVWyWv3+49so/JZf8QdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('71b996979ccdcb40878628b4acc4caf0')
GEMINI_API_KEY = "AIzaSyCLZ6saVa2GASawITSp36d98BSH5ov8Yuo"
db = TinyDB('nutrition_db.json')

# --- 功能區 ---

# 呼叫Gemini取得營養資料（強制JSON格式）
def query_nutrition(food_input):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}

    prompt = f"""
你現在是營養成分資料專家。針對「{food_input}」，請遵守以下規則產生JSON：

1. 如果名稱中有數字與g（例如「香蕉 50g」），則quantity填寫使用者給的份量（50g）。
2. 如果名稱中沒有數字份量，則quantity設定為「100g」。
3. food_name請寫乾淨的食物名稱（不包含數字份量），例如「香蕉」。
4. nutrition欄位內容必須包含（單位：克），格式如下：
    - 碳水化合物
    - 蛋白質
    - 脂肪
    - 維生素
    - 礦物質
    - 膳食纖維
    - 水分
5. 所有數字保留一位小數（例如：23.0）。

回傳格式範例：

{{
  "food_name": "香蕉",
  "quantity": "50g",
  "nutrition": {{
    "碳水化合物": 23.0,
    "蛋白質": 1.1,
    "脂肪": 0.3,
    "維生素": 0.1,
    "礦物質": 0.2,
    "膳食纖維": 2.6,
    "水分": 74.0
  }}
}}

**只回傳JSON，不要有其他文字！**
"""

    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    res = response.json()

    try:
        raw_text = res['candidates'][0]['content']['parts'][0]['text']
        json_start = raw_text.find('{')
        json_obj = raw_text[json_start:]
        nutrition_data = json.loads(json_obj)
        return nutrition_data
    except Exception as e:
        print("解析錯誤：", e)
        return None

# 分析特殊指令
def handle_special_command(user_id, text):
    User = Query()
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    if text == "/本月健康":
        records = db.search((User.user_id == user_id) & (User.date.startswith(current_month)))
        total = {"碳水化合物": 0, "蛋白質": 0, "脂肪": 0, "維生素": 0, "礦物質": 0, "膳食纖維": 0, "水分": 0}
        for record in records:
            for key in total.keys():
                total[key] += record["nutrition"][key]

        days = len(set([r['date'] for r in records])) or 1
        avg = {k: round(v/days, 1) for k, v in total.items()}

        text = "【本月累計攝取量】\n" + "\n".join([f"{k}: {v:.1f} 克" for k, v in total.items()]) + "\n\n"
        text += "【平均每日攝取量】\n" + "\n".join([f"{k}: {v:.1f} 克" for k, v in avg.items()])
        return text

    elif text == "/本月食物":
        records = db.search((User.user_id == user_id) & (User.date.startswith(current_month)))
        foods = [f"{r['food_name']}（{r['quantity']}）" for r in records]
        if not foods:
            return "本月尚無食物紀錄。"
        return "【本月食物紀錄】\n" + "\n".join(foods)

    elif text == "/今天食物":
        today = now.strftime("%Y-%m-%d")
        records = db.search((User.user_id == user_id) & (User.date == today))
        foods = [f"{r['food_name']}（{r['quantity']}）" for r in records]
        if not foods:
            return "今天尚無食物紀錄。"
        return "【今日食物紀錄】\n" + "\n".join(foods)

    elif text == "/今天健康":
        today = now.strftime("%Y-%m-%d")
        records = db.search((User.user_id == user_id) & (User.date == today))
        total = {"碳水化合物": 0, "蛋白質": 0, "脂肪": 0, "維生素": 0, "礦物質": 0, "膳食纖維": 0, "水分": 0}
        for record in records:
            for key in total.keys():
                total[key] += record["nutrition"][key]
        if not records:
            return "今天尚無營養紀錄。"
        return "【今日營養攝取】\n" + "\n".join([f"{k}: {v:.1f} 克" for k, v in total.items()])

    else:
        return "未知指令"

# --- 路由設定 ---

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except:
        abort(400)
    return 'OK'

# --- 主要邏輯 ---

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if text.startswith("/"):
        reply = handle_special_command(user_id, text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    nutrition_data = query_nutrition(text)
    if not nutrition_data:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢失敗，請稍後再試"))
        return

    # 整理顯示
    display_text = "\n".join([
        f"碳水化合物：{nutrition_data['nutrition']['碳水化合物']} 克",
        f"蛋白質：{nutrition_data['nutrition']['蛋白質']} 克",
        f"脂肪：{nutrition_data['nutrition']['脂肪']} 克",
        f"維生素：{nutrition_data['nutrition']['維生素']} 克",
        f"礦物質：{nutrition_data['nutrition']['礦物質']} 克",
        f"膳食纖維：{nutrition_data['nutrition']['膳食纖維']} 克",
        f"水分：{nutrition_data['nutrition']['水分']} 克"
    ])

    carousel = TemplateSendMessage(
        alt_text='食物營養資訊',
        template=CarouselTemplate(
            columns=[
                CarouselColumn(
                    title=f"{nutrition_data['food_name']}（{nutrition_data['quantity']}）",
                    text=display_text[:60],
                    actions=[
                        MessageAction(label='加入', text=f"/加入 {nutrition_data['food_name']} {nutrition_data['quantity']}")
                    ]
                )
            ]
        )
    )
    line_bot_api.reply_message(event.reply_token, carousel)

@handler.add(MessageEvent, message=TextMessage)
def handle_join(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if text.startswith("/加入"):
        parts = text.split()
        if len(parts) >= 3:
            food_name = parts[1]
            quantity = parts[2]
            nutrition_data = query_nutrition(f"{food_name} {quantity}")
            if not nutrition_data:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="加入失敗，請重新查詢"))
                return
            db.insert({
                "user_id": user_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "food_name": nutrition_data['food_name'],
                "quantity": nutrition_data['quantity'],
                "nutrition": nutrition_data['nutrition']
            })
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{nutrition_data['food_name']}（{nutrition_data['quantity']}）已加入記錄"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="格式錯誤，請使用：/加入 食物名稱 份量"))