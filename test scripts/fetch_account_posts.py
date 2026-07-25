import os
from datetime import datetime, timezone
from dotenv import load_dotenv

import csv
import json

from xdk import Client

TWEET_FIELDS = [
    "created_at",
    "public_metrics",
    "lang",
    "possibly_sensitive",
    "referenced_tweets",
    "conversation_id",
    "author_id",
]
MAX_RESULTS_PER_PAGE = 100     

def fetch_recent_posts(username: str, limit: int) -> list[dict]:
    load_dotenv()
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token: 
        raise RuntimeError("Set the X_BEARER_TOKEN environment variable before running this script.")
    client = Client(bearer_token=bearer_token)


    user_id = client.users.get_by_username(username=username).id
    if not user_id:
        raise ValueError(f"No user found for username '{username}'")

    collected: list[dict] = []
    pages = client.users.get_posts(
        id=user_id,
        max_results=MAX_RESULTS_PER_PAGE,
        exclude=["replies", "retweets"],
        tweet_fields=TWEET_FIELDS,
    )

    for page in pages:
        if not page.data:
            break
        for post in page.data:
            collected.append(extract_post_record(post))
            if len(collected) >= limit:
                return collected

    return collected


def extract_post_record(post) -> dict:
    
    def field(obj, name, default=None):
        if hasattr(obj, name):
            return getattr(obj, name)
        if isinstance(obj, dict):
            return obj.get(name, default)
        return default
 
    metrics = field(post, "public_metrics", {}) or {}
 
    return {
        "id": field(post, "id"),
        "text": field(post, "text"),
        "created_at": field(post, "created_at"),  # ISO 8601 / RFC 3339, UTC
        "author_id": field(post, "author_id"),
        "conversation_id": field(post, "conversation_id"),
        "lang": field(post, "lang"),
        "possibly_sensitive": field(post, "possibly_sensitive"),
        "referenced_tweets": field(post, "referenced_tweets"),
        "retweet_count": field(metrics, "retweet_count"),
        "reply_count": field(metrics, "reply_count"),
        "like_count": field(metrics, "like_count"),
        "quote_count": field(metrics, "quote_count"),
        "impression_count": field(metrics, "impression_count"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def save_json(records: list[dict], path: str) -> None:
    with open(path, "w") as f:
        json.dump(records, f, indent=2, default=str)
 
 
def save_csv(records: list[dict], path: str) -> None:
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            row = dict(row)
            if isinstance(row.get("referenced_tweets"), (list, dict)):
                row["referenced_tweets"] = json.dumps(row["referenced_tweets"])
            writer.writerow(row)


fetch_recent_posts("realDonaldTrump", 10)