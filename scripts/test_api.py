import os
import requests
from dotenv import load_dotenv 

#load local enviornment variables from .env file
#Keeps the API out of Github and source code
load_dotenv()

API_KEY = os.getenv("STOCK_API_KEY")

#stop early if API key is missing to catch errors early
if not API_KEY:
    raise ValueError("Missing STOCK_API_KEY. add it to .env file")

#starting with one ticker and one trading day to test the API response
TICKER = "AAPL"
DATE = "2026-06-18"

#get daily open/close points from massive needed for formula
url = f"https://api.massive.com/v1/open-close/{TICKER}/{DATE}"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

#adjusted for stock splits (ex. $100 - 1stock = $50 - 2 stocks)
params = {
    "adjusted": "true"
}
	
# send GET request to the stock API
# timeout prevents the script from hanging after 10 secs
response = requests.get(url, headers=headers, params=params, timeout=10)

print("Status code:", response.status_code)

#convert the API response into JSON so Python can read it
try:
    data = response.json()
except ValueError:
    print("Response was not JSON:")
    print(response.text)
    raise

print("Raw response:")
print(data)

#only continue if the API request succeeded.
if response.status_code != 200:
    raise Exception(f"API request failed: {data}")

#get the open and close prices from the response.
open_price = data.get("open")
close_price = data.get("close")

#check that both required fields exist before doing the calculation.
#can account for weekends, holidays, API errors
if open_price is None or close_price is None:
    raise ValueError("Missing open or close price in API response.")

#formula:
# ((Close - Open) / Open) * 100
percent_change = ((close_price - open_price) / open_price) * 100

print(f"\nTicker: {TICKER}")
print(f"Open: {open_price}")
print(f"Close: {close_price}")
print(f"Percent change: {percent_change:.2f}%")

