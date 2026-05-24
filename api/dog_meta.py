import html
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from supabase import create_client

CANONICAL_ORIGIN = "https://chattyhound.com"


def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)

DEFAULT_OG_IMAGE = f"{CANONICAL_ORIGIN}/og-image.jpg"


def _clean_age(age_str):
    if not age_str:
        return ""
    clean = re.sub(r"The shelter staff think I am", "", age_str, flags=re.I)
    clean = re.sub(r"\bold\b", "", clean, flags=re.I).strip()
    clean = re.sub(r"^(?:about|around)\s+", "", clean, flags=re.I)
    return clean.strip()


def _pronoun(gender_str):
    g = (gender_str or "").lower()
    if "female" in g:
        return "her"
    if "male" in g:
        return "him"
    return "them"


def _dog_image_url(profile):
    if profile.get("image_file") and profile.get("image_base_url"):
        return profile["image_base_url"] + profile["image_file"]
    if profile.get("image_public_url"):
        return profile["image_public_url"]
    if profile.get("image_url"):
        return profile["image_url"]
    return DEFAULT_OG_IMAGE


def _build_meta_copy(profile):
    name = profile.get("name") or "This pup"
    age = _clean_age(profile.get("age") or "")
    shelter = profile.get("located_at") or "Pima Animal Care Center"
    pron = _pronoun(profile.get("gender"))

    title = f"Meet {name} | ChattyHound"
    og_title = f"Meet {name} on ChattyHound"

    age_part = f"{age} " if age else ""
    description = (
        f"{name} is an adoptable rescue dog at {shelter}. "
        f"Chat with {pron} on ChattyHound and continue to the official shelter page."
    )
    share_text = (
        f"{name} is a sweet {age_part}rescue mix at {shelter}. "
        f"Chat with {pron} and learn more on ChattyHound."
    ).replace("  ", " ").strip()

    return {
        "title": title,
        "og_title": og_title,
        "description": description,
        "share_text": share_text,
    }


def _fetch_dog_profile(animal_id):
    client = get_supabase_client()
    pima_res = (
        client.table("pima_all_dogs")
        .select("animal_id, name, gender, age, weight")
        .eq("animal_id", animal_id)
        .limit(1)
        .execute()
    )
    prompts_res = (
        client.table("system_prompts")
        .select("animal_id, important_facts")
        .eq("animal_id", animal_id)
        .limit(1)
        .execute()
    )
    profile_res = (
        client.table("animals").select("*").eq("animal_id", animal_id).limit(1).execute()
    )
    if not pima_res.data or not profile_res.data:
        return None

    pima_dog = pima_res.data[0]
    profile = profile_res.data[0]
    profile["name"] = pima_dog.get("name") or "Unknown"
    profile["gender"] = pima_dog.get("gender") or "Unknown"
    profile["important_facts"] = (
        prompts_res.data[0].get("important_facts", []) if prompts_res.data else []
    )
    supabase_url_val = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
    profile["image_base_url"] = f"{supabase_url_val}/storage/v1/object/public/{bucket}/"
    return profile


def _inject_head(html_text, meta, dog_id, image_url):
    canonical = f"{CANONICAL_ORIGIN}/dogs/{dog_id}"
    esc = html.escape
    desc = esc(meta["description"])
    title = esc(meta["title"])
    og_title = esc(meta["og_title"])
    img = esc(image_url)

    out = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>", html_text, count=1)
    out = re.sub(
        r'<meta name="description"\s+content="[^"]*">',
        f'<meta name="description" content="{desc}">',
        out,
        count=1,
    )
    out = out.replace(
        '<link rel="canonical" href="https://chattyhound.com/" />',
        f'<link rel="canonical" href="{canonical}" />',
    )
    out = re.sub(
        r'<meta property="og:url" content="[^"]*">',
        f'<meta property="og:url" content="{canonical}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:title" content="[^"]*">',
        f'<meta property="og:title" content="{og_title}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:description"\s+content="[^"]*">',
        f'<meta property="og:description" content="{desc}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="og:image" content="[^"]*">',
        f'<meta property="og:image" content="{img}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="twitter:url" content="[^"]*">',
        f'<meta property="twitter:url" content="{canonical}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="twitter:title" content="[^"]*">',
        f'<meta property="twitter:title" content="{og_title}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="twitter:description"\s+content="[^"]*">',
        f'<meta property="twitter:description" content="{desc}">',
        out,
        count=1,
    )
    out = re.sub(
        r'<meta property="twitter:image" content="[^"]*">',
        f'<meta property="twitter:image" content="{img}">',
        out,
        count=1,
    )

    extra = "window.__CH_DOG_UNAVAILABLE__=true;" if meta.get("unavailable") else ""
    bootstrap = (
        f'<script>{extra}window.__CH_INITIAL_DOG_ID__={json_dumps(dog_id)};'
        f'window.__CH_PAGE_META__={json_dumps(meta)};</script>\n'
    )
    out = out.replace("<body>", f"<body>\n{bootstrap}", 1)
    return out


def json_dumps(val):
    import json

    return json.dumps(val)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            dog_id = (params.get("dogId") or params.get("dog_id") or [""])[0].strip()
            if not dog_id:
                path_parts = [p for p in parsed.path.split("/") if p]
                if len(path_parts) >= 2 and path_parts[-2] == "dogs":
                    dog_id = path_parts[-1]

            if not dog_id:
                self._redirect_home()
                return

            public_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
            index_path = os.path.join(public_dir, "index.html")
            if not os.path.isfile(index_path):
                self._send_text(500, "index.html not found")
                return

            with open(index_path, "r", encoding="utf-8") as f:
                html_text = f.read()

            profile = _fetch_dog_profile(dog_id)
            if not profile:
                unavailable_meta = {
                    "title": "Dog unavailable | ChattyHound",
                    "og_title": "Dog unavailable | ChattyHound",
                    "description": "This dog may no longer be available. Meet other adoptable dogs on ChattyHound.",
                    "share_text": "",
                    "unavailable": True,
                }
                html_out = _inject_head(html_text, unavailable_meta, dog_id, DEFAULT_OG_IMAGE)
                self._send_html(html_out)
                return

            meta = _build_meta_copy(profile)
            image_url = _dog_image_url(profile)
            html_out = _inject_head(html_text, meta, dog_id, image_url)
            self._send_html(html_out)

        except Exception as e:
            self._send_text(500, str(e))

    def _redirect_home(self):
        self.send_response(302)
        self.send_header("Location", CANONICAL_ORIGIN + "/")
        self.end_headers()

    def _send_html(self, body):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_text(self, code, message):
        self.send_response(code)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))
