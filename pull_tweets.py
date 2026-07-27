import os
import csv
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from xdk import Client

load_dotenv()

TOKEN = os.getenv("X_BEARER_TOKEN")

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

TWEET_FIELDS = [
    "id",
    "text",
    "created_at",
    "public_metrics",
    "referenced_tweets",
    "author_id",
    "attachments",
]

START_TIME = datetime(2024, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")
END_TIME = datetime(2025, 6, 24, 20, 25, tzinfo=UTC).isoformat().replace("+00:00", "Z")
#2025-06-24T20:25:35.000Z
OUTPUT_DIR = "x_posts"
COST_PER_READ = 0.005

ACCOUNTS = ["Benioff"]
# ACCOUNTS = ["satyanadella", "Benioff", "levie", "cristianoamon", "vladtenev", "tobi"]

CSV_COLUMNS = [
    "id",
    "author_id",
    "created_at_utc",
    "text",
    "like_count",
    "retweet_count",
    "reply_count",
    "quote_count",
    "is_quote_tweet",
    "referenced_tweets_json",
    "attachments_json",
]


def field(obj, name, default=None):
    """
    Reads `name` off `obj` regardless of whether obj is a dict or an
    attribute-based object. Necessary because different parts of the xdk
    response are NOT uniformly one shape or the other -- confirmed by
    user.data.id failing with "'dict' object has no attribute 'id'",
    even though other nested fields (public_metrics) came back as
    attribute-based objects. Don't assume consistency across the response;
    use this everywhere a response field is read.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def get_user_id(client, username: str) -> str:
    user = client.users.get_by_username(username=username)
    return field(user.data, "id")


def fetch_posts(client, uid: str) -> list:
    pages = client.users.get_posts(
        id=uid,
        exclude=["replies", "retweets"],
        tweet_fields=TWEET_FIELDS,
        start_time=START_TIME,
        end_time=END_TIME,
    )
    posts = []
    for page in pages:
        for post in page.data:
            posts.append(post)
    return posts


def post_to_row(p) -> list:
    metrics = field(p, "public_metrics")
    referenced = field(p, "referenced_tweets") or []
    attachments = field(p, "attachments")

    like_count = field(metrics, "like_count", "")
    retweet_count = field(metrics, "retweet_count", "")
    reply_count = field(metrics, "reply_count", "")
    quote_count = field(metrics, "quote_count", "")

    referenced_plain = [
        {"type": field(r, "type"), "id": field(r, "id")}
        for r in referenced
    ]
    is_quote = any(r["type"] == "quoted" for r in referenced_plain)

    attachments_plain = {}
    media_keys = field(attachments, "media_keys")
    if media_keys:
        attachments_plain["media_keys"] = list(media_keys)

    return [
        field(p, "id"),
        field(p, "author_id", ""),
        field(p, "created_at"),
        field(p, "text", "").replace("\n", " ").strip(),
        like_count,
        retweet_count,
        reply_count,
        quote_count,
        is_quote,
        json.dumps(referenced_plain) if referenced_plain else "",
        json.dumps(attachments_plain) if attachments_plain else "",
    ]


def main():
    guard = input("do you want to run")
    if guard != "yes":
        print("cancelling")
        return
    client = Client(bearer_token=TOKEN)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_reads = 0
    summary = {}

    for username in ACCOUNTS:
        print(f"{username}...", end=" ", flush=True)
        try:
            uid = get_user_id(client, username)
            posts = fetch_posts(client, uid)
        except Exception as e:
            print(f"FAILED: {e}")
            summary[username] = None
            continue

        out_path = os.path.join(OUTPUT_DIR, f"{username}.csv")
        file_exists = os.path.isfile(out_path)
        with open(out_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(CSV_COLUMNS)
            for p in posts:
                writer.writerow(post_to_row(p))

        n = len(posts)
        total_reads += n
        summary[username] = n
        running_cost = total_reads * COST_PER_READ
        print(f"{n} posts (running total: {total_reads}, est. cost so far: ${running_cost:.2f})")

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for username, n in summary.items():
        status = f"{n} posts" if n is not None else "FAILED -- check error above"
        print(f"  {username}: {status}")
    print(f"\nTotal posts pulled: {total_reads}")


if __name__ == "__main__":
    main()