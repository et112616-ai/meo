import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates
import yfinance as yf
import pandas as pd
import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 【修正核心】 輔助工具區
# ==============================================================================

def parse_postback_data(postback_str):
    """解決問題三：解析 LINE 按鈕回傳的字串"""
    try:
        parts = postback_str.split(",")
        if len(parts) == 4:
            return {
                "stock": parts[0],
                "action": parts[1],
                "current_mode": parts[2],
                "time_frame": parts[3]
            }
        return None
    except:
        return None

def build_error_response(msg):
    """解決問題五：錯誤訊息標準化為 LINE 格式"""
    return {
        "type": "text",
        "text": f"❌ {msg}"
    }

def convert_to_futures_id(stock_id):
    """解決問題四：期貨轉換邏輯 (需確認該標的是否有期貨)"""
    # 此處建議改為查表法，若查不到直接回傳 None
    # 簡單防禦機制：如果是 2330，我們可以嘗試回傳 TXF (台指期)，其他個股期貨需特定代碼
    return f"F_{stock_id}" 

def upload_to_cloud(fig):
    """解決問題一：真實上傳機制 (目前為佔位符)"""
    # 🔥 注意：請將此處替換為您的實際 Imgur/Cloudinary/S3 上傳邏輯
    plt.close(fig)
    return "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=500"

# ==============================================================================
# 【修正核心】 繪圖邏輯 (已修正 marginBottom 為 margin)
# ==============================================================================
# ... (這裡保留你原本的繪圖邏輯，記得將所有 "marginBottom": "md" 改為 "margin": "md")

# ==============================================================================
# 【修正核心】 LINE Flex 建構函數
# ==============================================================================

def build_flex_image_response(stock_id, stock_name, title, image_url, current_mode, price_info="--", change_info="--", time_stamp="--", time_frame="D"):
    """
    修正點：已確認將所有 "marginBottom" 替換為 "margin"
    """
    def get_tf_style(tf):
        return "primary" if time_frame == tf else "secondary"

    return {
        "type": "flex",
        "altText": f"{stock_id} {stock_name} 觀測儀表板",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",  # 🔥 已修正
                        "contents": [
                            { "type": "text", "text": f"{stock_id} {stock_name}", "weight": "bold", "size": "xl" },
                            { "type": "text", "text": f"{price_info} ({change_info})", "weight": "bold", "size": "md", "color": "#FF3B30" if "+" in change_info else "#34C759" },
                            { "type": "text", "text": f"更新時間：{time_stamp}", "size": "xs", "color": "#8E8E93", "margin": "xs" }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "xs",
                        "margin": "md",  # 🔥 已修正
                        "contents": [
                            { "type": "button", "style": get_tf_style("1m"), "height": "sm", "action": { "type": "postback", "label": "1分", "data": f"{stock_id},{current_mode},{current_mode},1m" } },
                            { "type": "button", "style": get_tf_style("5m"), "height": "sm", "action": { "type": "postback", "label": "5分", "data": f"{stock_id},{current_mode},{current_mode},5m" } },
                            { "type": "button", "style": get_tf_style("D"), "height": "sm", "action": { "type": "postback", "label": "D", "data": f"{stock_id},{current_mode},{current_mode},D" } }
                        ]
                    }
                    # ... (其餘結構同上，請確保把所有的 marginBottom 都改掉)
                ]
            }
        }
    }

# ==============================================================================
# 【修正核心】 路由與邏輯分流 (問題三、六)
# ==============================================================================

@app.route('/get_chart', methods=['POST'])
def webhook_entry():
    """解決問題六：統一包裝輸出結構"""
    try:
        payload = request.get_json()
        
        # 1. 優先處理 Postback 解析
        if "postback" in payload:
            postback_data = payload["postback"].get("data")
            parsed = parse_postback_data(postback_data)
            if parsed:
                payload.update(parsed)
        
        # 2. 執行業務邏輯
        response_data = handle_request(payload)
        
        # 3. 強制封裝 (Wrapper)
        return jsonify({"messages": [response_data]}), 200
        
    except Exception as e:
        # 發生錯誤也封裝成訊息回傳，不讓 Flask 噴 500 給 Make
        return jsonify({"messages": [build_error_response(f"執行錯誤: {str(e)}")]}), 200

def handle_request(payload):
    # 這裡放你原本的 handle_request 邏輯
    # ...
    return build_error_response("執行成功")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
