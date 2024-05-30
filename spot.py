import requests
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import time

# Constants
TAKER_FEE = 0.001  # 0.10%
MAKER_FEE = 0.0  # 0.00%


# Fetch crypto price
def fetch_crypto_price(symbol):
    url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}"
    response = requests.get(url)
    response.raise_for_status()
    price = float(response.json()['price'])

    # Save price history
    file_path = f"{symbol}_price_history.txt"
    with open(file_path, 'a') as file:
        file.write(f"{datetime.utcnow().isoformat()},{price}\n")

    return price



# Initialize price history
def initialize_price_history(symbol):
    file_path = f"{symbol}_price_history.txt"
    if not os.path.exists(file_path):
        print(f"Initializing price history for {symbol}")
        for _ in range(15):  # Fetch initial 15 data points
            fetch_crypto_price(symbol)
            time.sleep(1)  # Sleep to avoid hitting rate limits


# Read balances from file
def read_balances_from_file():
    balances = {}
    usd_balance = 2000.0
    if os.path.exists("balances.txt"):
        with open("balances.txt", 'r') as file:
            for line in file:
                currency, amount = line.strip().split(',')
                if currency == "USD":
                    usd_balance = float(amount)
                else:
                    balances[currency] = float(amount)
    return usd_balance, balances


# Write balances to file
def write_balances_to_file(usd_balance, balances):
    with open("balances.txt", 'w') as file:
        file.write(f"USD,{usd_balance}\n")
        for currency, amount in balances.items():
            file.write(f"{currency},{amount}\n")


# Record trade history
def record_trade_history(symbol, amount, price, trade_type):
    file_path = f"{symbol}_trade_history.txt"
    with open(file_path, 'a') as file:
        file.write(f"{datetime.utcnow().isoformat()},{trade_type},{amount},{price},{amount * price}\n")


# Calculate ATR
def calculate_atr(symbol, period):
    file_path = f"{symbol}_price_history.txt"
    if not os.path.exists(file_path):
        raise FileNotFoundError("Price history file not found")

    prices = pd.read_csv(file_path, header=None, names=['timestamp', 'price'])
    if len(prices) < period + 1:
        raise ValueError("Not enough data to calculate ATR")

    prices['price'] = prices['price'].astype(float)
    prices['prev_close'] = prices['price'].shift(1)
    prices['tr'] = prices.apply(lambda row: max(row['price'] - row['price'], abs(row['price'] - row['prev_close']),
                                                abs(row['price'] - row['prev_close'])), axis=1)
    atr = prices['tr'].rolling(window=period).mean().iloc[-1]

    return atr


# Trade and hedge
def trade_and_hedge(cryptos, usd_balance, balances):
    prices = {crypto: fetch_crypto_price(crypto) for crypto in cryptos}

    for crypto, price in prices.items():
        crypto_name = crypto.replace("USDT", "")
        last_price = balances.get(crypto_name, price)
        atr = calculate_atr(crypto, 14)

        min_trade_amount = 5.0
        trade_size_factor = max(min_trade_amount / 500000.0, atr / price)
        trade_amount_usd = 500000.0 * trade_size_factor

        if trade_amount_usd < min_trade_amount:
            continue

        if price < last_price:
            crypto_balance = balances.get(crypto_name, 0.0)
            if crypto_balance * price >= trade_amount_usd and crypto_balance > 0.0:
                crypto_amount = trade_amount_usd / price
                fee = trade_amount_usd * TAKER_FEE
                net_trade_amount_usd = trade_amount_usd - fee
                balances[crypto_name] = crypto_balance - crypto_amount
                usd_balance += net_trade_amount_usd
                print(f"Short sold {crypto_amount:.10f} of {crypto} for ${net_trade_amount_usd:.2f} (Fee: ${fee:.2f})")
                record_trade_history(crypto, -crypto_amount, price, "sell")
        else:
            if usd_balance >= trade_amount_usd:
                crypto_amount = trade_amount_usd / price
                fee = trade_amount_usd * TAKER_FEE
                net_trade_amount_usd = trade_amount_usd - fee
                balances[crypto_name] = balances.get(crypto_name, 0.0) + crypto_amount
                usd_balance -= net_trade_amount_usd
                print(f"Bought {crypto_amount:.10f} of {crypto} for ${net_trade_amount_usd:.2f} (Fee: ${fee:.2f})")
                record_trade_history(crypto, crypto_amount, price, "buy")

    return usd_balance, balances


# Main function
def main():
    usd_balance, balances = read_balances_from_file()
    cryptos = ["XTZUSDT", "PEPEUSDT", "BOMEUSDT", "BXXUSDT", "BONKUSDT"]

    for crypto in cryptos:
        try:
            initialize_price_history(crypto)
        except Exception as e:
            print(f"Error initializing price history for {crypto}: {e}")

    while True:
        usd_balance, balances = trade_and_hedge(cryptos, usd_balance, balances)
        write_balances_to_file(usd_balance, balances)

        current_portfolio_value = usd_balance
        for crypto, amount in balances.items():
            try:
                price = fetch_crypto_price(f"{crypto}USDT")
                current_portfolio_value += amount * price
            except Exception as e:
                print(f"Error fetching price for {crypto}: {e}")

        print(f"Total Portfolio Value in USD: {current_portfolio_value:.2f}")
        time.sleep(30)


if __name__ == "__main__":
    main()
