from typing import Optional, List
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient

# ----（本機開發時，如果有用 .env 就打開這段）----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 如果沒有裝 python-dotenv 就略過，Render 上只會用環境變數
    pass

# ---- MongoDB 連線設定 ----
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    # 這樣在本機沒設定 MONGO_URI 的時候會看得出問題
    raise RuntimeError("MONGO_URI is not set. Please set it in .env or Render environment.")

client = MongoClient(MONGO_URI)
db = client["emogo"]           # database 名稱，可改
entries_col = db["entries"]    # collection 名稱，可改


# ---- Pydantic Model：定義一筆 EmoGo 資料長相 ----
class EmoEntry(BaseModel):
    id: Optional[int] = None
    latitude: float
    longitude: float
    mood: int
    photoUri: Optional[str] = None
    # 為了避免時間格式 parse 問題，這裡用 str，前端就送 ISO 字串
    timestamp: str


# ---- 建立 FastAPI app ----
app = FastAPI()

# ---- CORS 設定（讓 Expo / Web 前端可以叫這個 API）----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 作業方便，先全開
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 基本測試用 endpoints ----
@app.get("/")
def root():
    return {"message": "EmoGo backend is running."}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


# ---- EmoGo 主要 API：新增紀錄 ----
@app.post("/entries")
def create_entry(entry: EmoEntry):
    doc = entry.dict()
    result = entries_col.insert_one(doc)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"status": "ok", "inserted_id": str(result.inserted_id)}


# ---- EmoGo 主要 API：列出所有紀錄（純 JSON）----
@app.get("/entries")
def list_entries():
    # 投影片／TA 看資料時，不一定想看到 MongoDB 的 _id，就先隱藏
    docs: List[dict] = list(entries_col.find({}, {"_id": 0}))
    return {"data": docs}


# ---- 匯出三種資料：Vlogs / Sentiments / GPS / All ----
@app.get("/export/vlogs")
def export_vlogs():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "photoUri": 1,
                "timestamp": 1,
            },
        )
    )
    return {"vlogs": docs}


@app.get("/export/sentiments")
def export_sentiments():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "mood": 1,
                "timestamp": 1,
            },
        )
    )
    return {"sentiments": docs}


@app.get("/export/gps")
def export_gps():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "latitude": 1,
                "longitude": 1,
                "timestamp": 1,
            },
        )
    )
    return {"gps": docs}


@app.get("/export/all")
def export_all():
    docs = list(entries_col.find({}, {"_id": 0}))
    return {"data": docs}


# ---- 匯出頁面（作業要求的 data-exporting/downloading page）----
@app.get("/export", response_class=HTMLResponse)
def export_page():
    # 注意：下面的 href 是「相對路徑」，部署到 Render 後會自動補成完整網址
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo Data Export</title>
      </head>
      <body>
        <h1>EmoGo Data Export</h1>
        <p>You can download all EmoGo data here (JSON format):</p>
        <ul>
          <li><a href="/export/all">All data (vlogs + sentiments + GPS)</a></li>
          <li><a href="/export/vlogs">Vlogs only</a></li>
          <li><a href="/export/sentiments">Sentiments only</a></li>
          <li><a href="/export/gps">GPS only</a></li>
        </ul>
      </body>
    </html>
    """
