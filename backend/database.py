import firebase_admin
from firebase_admin import credentials
from pymongo import MongoClient

# Khởi tạo Firebase Admin
cred = credentials.Certificate("firebase-service-account.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Khởi tạo MongoDB
MONGO_URI = "mongodb://localhost:27017"
client = MongoClient(MONGO_URI)

# Trỏ vào DB NCKH và Collection UserInfo
db = client["NCKH"]
users_collection = db["UserInfo"]