import os
from flask import Flask, request, jsonify
import yfinance as tf
import mplfinance as mpf
import requests
import io

app = Flask(__name__)

IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY', '你的預設KEY')

def get_live_price(full_stock_id):
    """取得即時股價與漲跌幅"""
    try:
        ticker = tf.Ticker(full_stock_id)
        info = ticker.info
        # 嘗試取得即時價格，若無則取前一次收盤
        price = info.get('regularMarketPrice') or info.get('currentPrice') or 0.0
        prev_close = info.get('regularMarketPreviousClose') or price
        
        name = info.get('shortName') or full_stock_id.split('.')[0]
        change = price - prev_close
        change_percent = (change / prev_close) * 100 if prev_close else 0
        
        # 決定顏色與符號
        if change > 0:
            status_text = f"▲ +{change:.2f} (+{change_percent:.2f}%)"
            color = "#FF0000" # 紅漲
        elif change < 0:
            status_text = f"▼ {change:.2f} ({change_percent:.2f}%)"
            color = "#00CC00" # 綠跌
        else:
            status_text = f" 0.00 (0.00%)"
            color = "#888888"
            
        return name, f"{price:.2f}", status_text, color
    except:
        return full_stock_id.split('.')[0], "0.0", "暫無資料", "#888888"

@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        req_data = request.get_json() or {}
        
        # 判斷是文字輸入，還是點擊按鈕的 Postback 密碼
        # LINE Postback 會傳入 data 欄位，例如 "action=kline&time=5m&id=2313"
        raw_data = req_data.get('data', '')
        stock_id = req_data.get('stock_id', '2330') # 預設值
        time_frame = '1d' # 預設日線
        
        # 解析按鈕傳過來的參數
        if raw_data:
            params = dict(x.split('=') for x in raw_data.split('&') if '=' in x)
            if 'id' in params: stock_id = params['id']
            if 'time' in params: time_frame = params['time']

        # 確保代號格式正確
        stock_id = str(stock_id).strip().upper()
        if not stock_id.endswith('.TW') and not stock_id.endswith('.TWO'):
            full_stock_id = f"{stock_id}.TW"
        else:
            full_stock_id = stock_id
            stock_id = stock_id.split('.')[0]

        # 根據 Yahoo Finance API 規範嚴格設定 period 與 interval
        # 分K線圖不能抓太長的時間，否則 Yahoo 會拒絕回傳資料
        period_map = {
            '1m': '5d',    # 1分K：只抓最近 5 天（法規上限 7 天）
            '5m': '7d',    # 5分K：只抓最近 7 天（法規上限 60 天）
            '15m': '14d',  # 15分K：只抓最近 14 天
            '30m': '30d',  # 30分K：只抓最近 30 天
            '60m': '30d',  # 60分K：只抓最近 30 天
            '1d': '3mo',   # 日K：抓 3 個月
            '1w': '1y',    # 週K：抓 1 年
            '1M': '2y'     # 月K：抓 2 年
        }
        
        interval_map = {
            '1m': '1m', 
            '5m': '5m', 
            '15m': '15m', 
            '30m': '30m', 
            '60m': '60m', 
            '1d': '1d', 
            '1w': '1wk', 
            '1M': '1mo'
        }
    
        
        period = period_map.get(time_frame, '3mo')
        interval = interval_map.get(time_frame, '1d')

        # 1. 抓取股票數據
        df = tf.download(full_stock_id, period=period, interval=interval)
        
        if df.empty:
            return jsonify({"status": "error", "message": "找不到此股票數據"})

        # 2. 繪製 K 線圖
        buf = io.BytesIO()
        mc = mpf.make_marketcolors(up='r', down='g', inherit=True)
        s  = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, gridstyle='--')
        mpf.plot(df, type='candle', style=s, volume=True, savefig=buf, format='png', dimensions=(800, 600))
        buf.seek(0)

        # 3. 上傳圖片到 ImgBB
        files = {'image': ('chart.png', buf, 'image/png')}
        payload = {'key': IMGBB_API_KEY}
        img_res = requests.post('https://api.imgbb.com/1/upload', data=payload, files=files)
        image_url = img_res.json()['data']['url']

        # 4. 撈取即時股價資訊填入卡片
        stock_name, price_now, status_text, text_color = get_live_price(full_stock_id)

        # 5. 動態動手組裝 Flex Message JSON 結構
        # 幫當前選中的時間按鈕加上顏色控制 (style="secondary" 為選中，"link" 為沒選中)
        def get_btn_style(t): return "secondary" if time_frame == t else "link"

        flex_contents = {
          "type": "bubble",
          "size": "mega",
          "header": {
            "type": "box", "layout": "vertical",
            "contents": [
              {
                "type": "box", "layout": "horizontal",
                "contents": [
                  {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "xl", "flex": 1},
                  {"type": "text", "text": price_now, "weight": "bold", "size": "xl", "color": text_color, "align": "end"},
                  {"type": "text", "text": status_text, "size": "sm", "color": text_color, "align": "end", "gravity": "bottom"}
                ]
              }
            ]
          },
          "body": {
            "type": "box", "layout": "vertical", "paddingAll": "sm",
            "contents": [
              {
                "type": "box", "layout": "horizontal", "spacing": "xs",
                "contents": [
                  {"type": "button", "action": {"type": "postback", "label": "1分", "data": f"action=kline&time=1m&id={stock_id}"}, "style": get_btn_style("1m"), "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "5分", "data": f"action=kline&time=5m&id={stock_id}"}, "style": get_btn_style("5m"), "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "15分", "data": f"action=kline&time=15m&id={stock_id}"}, "style": get_btn_style("15m"), "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "日", "data": f"action=kline&time=1d&id={stock_id}"}, "style": get_btn_style("1d"), "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "週", "data": f"action=kline&time=1w&id={stock_id}"}, "style": get_btn_style("1w"), "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "月", "data": f"action=kline&time=1M&id={stock_id}"}, "style": get_btn_style("1M"), "height": "sm"}
                ]
              },
              {
                "type": "image", "url": image_url, "size": "full", "aspectRatio": "4:3", "aspectMode": "cover", "margin": "md"
              }
            ]
          },
          "footer": {
            "type": "box", "layout": "vertical",
            "contents": [
              {
                "type": "box", "layout": "horizontal", "spacing": "xs",
                "contents": [
                  {"type": "button", "action": {"type": "postback", "label": "即時", "data": f"action=tab&tab=realtime&id={stock_id}"}, "style": "link", "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "K線", "data": f"action=tab&tab=kline&id={stock_id}"}, "style": "secondary", "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "法人", "data": f"action=tab&tab=legal&id={stock_id}"}, "style": "link", "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "資訊", "data": f"action=tab&tab=info&id={stock_id}"}, "style": "link", "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "持股", "data": f"action=tab&tab=hold&id={stock_id}"}, "style": "link", "height": "sm"},
                  {"type": "button", "action": {"type": "postback", "label": "融資券", "data": f"action=tab&tab=margin&id={stock_id}"}, "style": "link", "height": "sm"}
                ]
              }
            ]
          }
        }

        # 把整串精美的卡片結構裝在 "flex_contents" 欄位回傳給 Make.com
        return jsonify({
            "status": "success",
            "image_url": image_url,
            "flex_contents": flex_contents
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
