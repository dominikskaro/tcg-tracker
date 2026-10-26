import os

import requests


EVENT_LABELS = {
    "NEW": "Novi proizvod",
    "RESTOCK": "Ponovno dostupan",
    "PRICE_DROP": "Pad cijene",
    "PREORDER_AVAILABLE": "Prednarudžba dostupna za narudžbu",
}


def _format_event(shop, event):
    label = EVENT_LABELS.get(event["type"], event["type"])
    lines = [f"{label} — {shop}", event["name"], f"Cijena: {event['price']:.2f} €"]
    if event["type"] == "PRICE_DROP":
        lines.append(f"Prije: {event['old_price']:.2f} €")
    if event.get("url"):
        lines.append(event["url"])
    return "\n".join(lines)


def send_events(shop, events):
    token = os.getenv("TCG_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TCG_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Postavi TCG_TELEGRAM_BOT_TOKEN i TCG_TELEGRAM_CHAT_ID.")

    messages = []
    current = []
    current_length = 0
    for event in events:
        formatted = _format_event(shop, event)
        extra_length = len(formatted) + (2 if current else 0)
        if current and current_length + extra_length > 3500:
            messages.append("\n\n".join(current))
            current = []
            current_length = 0
        current.append(formatted)
        current_length += len(formatted) + (2 if len(current) > 1 else 0)
    if current:
        messages.append("\n\n".join(current))

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    for message in messages:
        response = requests.post(
            endpoint,
            json={"chat_id": chat_id, "text": message},
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", "Telegram API nije prihvatio poruku."))

def send_status(text):
    token = os.getenv("TCG_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TCG_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Postavi TCG_TELEGRAM_BOT_TOKEN i TCG_TELEGRAM_CHAT_ID.")

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        endpoint,
        json={"chat_id": chat_id, "text": text},
        timeout=20,
    )
    response.raise_for_status()

    if not response.json().get("ok"):
        raise RuntimeError("Telegram nije prihvatio statusnu poruku.")
