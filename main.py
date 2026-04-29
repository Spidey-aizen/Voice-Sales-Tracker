from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from datetime import datetime
import os
import requests
import json
import re

app = FastAPI()

# ✅ CORS - allow all origins (dev mode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State ──────────────────────────────────────────────
FILE_NAME = "sales.xlsx"  # default; can be changed via API


class Sale(BaseModel):
    product: str
    quantity: int
    price: float


class FileRequest(BaseModel):
    filename: str


# ── Excel helpers ───────────────────────────────────────

def get_filepath():
    return FILE_NAME


def save_to_excel(data: Sale):
    new_row = {
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Product": data.product.capitalize(),
        "Quantity": data.quantity,
        "Price": data.price,
    }
    path = get_filepath()
    try:
        if os.path.exists(path):
            df = pd.read_excel(path, engine="openpyxl")
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            df = pd.DataFrame([new_row])
        df.to_excel(path, index=False, engine="openpyxl")
    except PermissionError:
        raise HTTPException(status_code=423, detail="Close the Excel file and try again.")


# ── Text parsing ────────────────────────────────────────

WORD_NUMS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
    "fifty": "50", "hundred": "100",
}


def word_to_number(text: str) -> str:
    for word, num in WORD_NUMS.items():
        text = re.sub(rf"\b{word}\b", num, text, flags=re.IGNORECASE)
    return text


def parse_text_ai(text: str) -> dict:
    prompt = f"""Extract product, quantity and total price from this sales statement.
Return ONLY valid JSON, nothing else.

Example:
Input: sold 2 apples for 100 rupees
Output: {{"product":"apples","quantity":2,"price":100}}

Now parse:
{text}
"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False,
                  "options": {"temperature": 0}},
            timeout=10,
        )
        result = response.json().get("response", "")
        match = re.search(r"\{.*\}", result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            if data.get("product") and data.get("quantity") is not None:
                return data
    except Exception as e:
        print("AI parse failed:", e)

    # ── Fallback regex parser ──
    print("⚠️  Using fallback parser")
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    quantity = int(float(numbers[0])) if len(numbers) > 0 else 1
    price = float(numbers[1]) if len(numbers) > 1 else 0.0

    stop = {"sold", "for", "rupees", "rs", "₹", "i", "bro", "the", "a", "at"}
    product = "unknown"
    for word in text.lower().split():
        clean = re.sub(r"[^a-z]", "", word)
        if clean and clean not in stop and not clean.isdigit():
            product = clean
            break

    return {"product": product, "quantity": quantity, "price": price}


# ── Routes ──────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Sales API running"}


@app.get("/current-file")
def current_file():
    return {"filename": FILE_NAME, "exists": os.path.exists(FILE_NAME)}


@app.post("/set-file")
def set_file(req: FileRequest):
    global FILE_NAME
    name = req.filename.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")
    if not name.endswith(".xlsx"):
        name += ".xlsx"
    FILE_NAME = name
    return {"filename": FILE_NAME, "created": not os.path.exists(FILE_NAME)}


@app.post("/add-sale")
def add_sale(sale: Sale):
    save_to_excel(sale)
    return {"message": "Sale added", "data": sale.dict()}


@app.post("/add-sale-text")
def add_sale_text(body: dict = Body(...)):
    raw_text = body.get("text", "")
    if not raw_text:
        raise HTTPException(status_code=400, detail="'text' field is required.")

    text = word_to_number(raw_text)
    parsed = parse_text_ai(text)
    print("PARSED:", parsed)

    sale = Sale(
        product=parsed.get("product", "unknown"),
        quantity=int(parsed.get("quantity", 1)),
        price=float(parsed.get("price", 0)),
    )
    save_to_excel(sale)
    return {"message": "Parsed and saved", "data": sale.dict()}


@app.get("/sales")
def get_sales():
    path = get_filepath()
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_excel(path, engine="openpyxl")
        return df.fillna("").to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clear-sales")
def clear_sales():
    path = get_filepath()
    if os.path.exists(path):
        os.remove(path)
    return {"message": "Sales cleared"}
