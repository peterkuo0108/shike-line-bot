from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, CarouselTemplate, CarouselColumn, MessageAction
from tinydb import TinyDB
from datetime import datetime
import requests
import os

# === 設定 ===
LINE_CHANNEL_ACCESS_TOKEN = 'aGpYRbppqiGEdWyqMRXLjl0bAoh1TH0v23yQ9AZ6r6SkIukuuvyNTiqWpdG+tCZPoeUoLJnAfR0TgJJP/q1RBqMKE2a8Dv6fBz7YbFhAODYbyOh6vnc8s+fZpf31S9C2SaLdzVWyWv3+49so/JZf8QdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '71b996979ccdcb40878628b4acc4caf0'
GEMINI_API_KEY = 'AIzaSyCLZ6saVa2GASawITSp36d98BSH5ov8Yuo'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
db = TinyDB('data.json')

app = Flask(__name__)

# === Gemini 查詢營養資訊 ===
def query_nutrition(food_name):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    prompt = f"""
請用表格列出每100克「{food_name}」的以下營養素數值（單位請統一為克或毫克）：

- 碳水化合物
- 蛋白質
- 脂肪
- 維生素
- 礦物質
- 膳食纖維
- 水分

請用以下格式：

碳水化合物：X 克  
蛋白質：X 克  
脂肪：X 克  
維生素：X 毫克  
礦物質：X 毫克  
膳食纖維：X 克  
水分：X 克
"""
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=data)
    res = response.json()
    try:
        raw_text = res['candidates'][0]['content']['parts'][0]['text']
        nutrition = {}
        for line in raw_text.split('\n'):
            if "：" in line:
                key, val = line.strip().split("：")
                num = ''.join(c for c in val if c.isdigit() or c == '.')
                if "毫克" in val:
                    num = round(float(num) / 1000, 2)
                else:
                    num = float(num)
                nutrition[key] = num
        return nutrition, raw_text
    except:
        return {}, "查詢失敗"

# === 指令處理 ===
def handle_special_command(user_id, text):
    if text == "/本月健康":
        today = datetime.now()
        month = today.strftime("%Y-%m")
        entries = db.search((lambda x: x['user_id'] == user_id and x['date'].startswith(month)))
        total = {}
        count = 0
        for entry in entries:
            for k, v in entry['nutrition'].items():
                total[k] = total.get(k, 0) + v
            count += 1
        if count == 0:
            return "本月沒有紀錄"
        avg = {k: round(v/count, 2) for k, v in total.items()}
        lines = [f"{k}：總共 {round(v,2)} 克，每日平均 {avg[k]} 克" for k, v in total.items()]
        return "\n".join(lines)

    elif text == "/本月食物":
        month = datetime.now().strftime("%Y-%m")
        entries = db.search((lambda x: x['user_id'] == user_id and x['date'].startswith(month)))
        if not entries:
            return "本月沒有食物紀錄"
        lines = [f"{e['date']}：{e['food_name']}（{e['quantity']}）" for e in entries]
        return "\n".join(lines)

    elif text.startswith("/加入"):
        parts = text.split()
        if len(parts) >= 3:
            food_name = parts[1]
            quantity = parts[2]
            nutrition, _ = query_nutrition(food_name)
            db.insert({
                "user_id": user_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "food_name": food_name,
                "quantity": quantity,
                "nutrition": nutrition
            })
            return f"{food_name} 已加入記錄"
        else:
            return "格式錯誤，請用：/加入 食物名稱 份量"

    elif text == "/幫助":
        return "指令列表：\n/本月健康\n/本月食物\n/幫助\n/加入 食物 份量"

    else:
        return "不支援的指令"

# === LINE webhook ===
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# === 訊息處理 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id

    if text.startswith("/"):
        reply = handle_special_command(user_id, text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    parts = text.strip().split()
    name = parts[0]
    quantity = parts[1] if len(parts) > 1 else "100g"

    nutrition_info, nutrition_text = query_nutrition(name)

    carousel = TemplateSendMessage(
        alt_text='食物營養資訊',
        template=CarouselTemplate(
            columns=[
                CarouselColumn(
                    title=f"{name}（{quantity}）",
                    text=nutrition_text[:60],
                    actions=[
                        MessageAction(label='加入', text=f"/加入 {name} {quantity}")
                    ]
                )
            ]
        )
    )
    line_bot_api.reply_message(event.reply_token, carousel)

# === 主程式啟動（Render會用這段）===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)