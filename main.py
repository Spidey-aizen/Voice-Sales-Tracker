from fastapi import FastAPI, Body
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from datetime import datetime
import os
import requests
import json
import re

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FILE_NAME = "sales.xlsx"

class Sale(BaseModel):
    product: str
    quantity: int
    price: float


# ✅ Save to Excel safely
def save_to_excel(data):
    new_row = {
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Product": data.product,
        "Quantity": data.quantity,
        "Price": data.price
    }

    try:
        if os.path.exists(FILE_NAME):
            df = pd.read_excel(FILE_NAME, engine="openpyxl")
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            df = pd.DataFrame([new_row])

        df.to_excel(FILE_NAME, index=False)

    except PermissionError:
        print("❌ Close Excel file (sales.xlsx) and try again")
def word_to_number(text):
    words = {
        "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6",
        "seven": "7", "eight": "8", "nine": "9",
        "ten": "10"
    }

    for word, num in words.items():
        text = re.sub(rf"\b{word}\b", num, text)

    return text

# 🔥 AI PARSER (CLEAN + FIXED)
def parse_text_ai(text):
    prompt = f"""
Extract product, quantity and total price.

STRICT:
- Only JSON
- No explanation

Example:
Input: sold 2 apples for 100 rupees
Output:
{{"product":"apples","quantity":2,"price":100}}

Now:
{text}
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0}
            },
            timeout=10
        )

        result = response.json()["response"]
        print("RAW AI:", result)

        match = re.search(r'\{.*\}', result, re.DOTALL)

        if match:
            data = json.loads(match.group())

            if data.get("product"):
                return data

    except Exception as e:
        print("AI FAILED:", e)

    # 🔥 FALLBACK (VERY IMPORTANT)
    print("⚠️ Using fallback parser")

    numbers = re.findall(r'\d+', text)

    quantity = int(numbers[0]) if len(numbers) > 0 else 1
    price = float(numbers[1]) if len(numbers) > 1 else 0

    words = text.lower().split()
    product = "unknown"

    for word in words:
        if word not in ["sold", "for", "rupees", "rs", "bro", "i"]:
            if not word.isdigit():
                product = word
                break

    return {
        "product": product,
        "quantity": quantity,
        "price": price
    }
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0
                }
            },
            timeout=20
        )

        result = response.json()["response"]
        print("RAW AI:", result)

        # ✅ Extract JSON block safely
        match = re.search(r'\{.*\}', result, re.DOTALL)

        if match:
            data = json.loads(match.group())

            # 🔥 CLEAN PRODUCT NAME (IMPORTANT FIX)
            product = data.get("product", "unknown")

            # remove unwanted words
            product = re.sub(r'(product|name|is|the)', '', product)

            # remove symbols
            product = re.sub(r'[^a-zA-Z ]', '', product)

            product = product.strip()

            # take only first word
            product = product.split()[0] if product else "unknown"

            data["product"] = product.lower()

            return data

    except Exception as e:
        print("AI ERROR:", e)

    return {"product": "unknown", "quantity": 0, "price": 0}


# ✅ Manual API
@app.post("/add-sale")
def add_sale(sale: Sale):
    save_to_excel(sale)
    return {"message": "Sale added successfully"}


# 🔥 Text → AI → Excel
@app.post("/add-sale-text")
def add_sale_text(text: str = Body(...)):
    text = word_to_number(text)
    parsed = parse_text_ai(text)

    print("FINAL PARSED:", parsed)

    sale = Sale(
        product=parsed["product"],
        quantity=parsed["quantity"],
        price=parsed["price"]
    )

    save_to_excel(sale)

    return {
        "message": "Parsed and saved",
        "data": parsed
    }
@app.get("/sales")
def get_sales():
    if os.path.exists(FILE_NAME):
        df = pd.read_excel(FILE_NAME, engine="openpyxl")
        return df.to_dict(orient="records")
    return []