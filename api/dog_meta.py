import html
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from supabase import create_client

CANONICAL_ORIGIN = "https://chattyhound.com"
_INDEX_HTML_CACHE = None


def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)

DEFAULT_OG_IMAGE = f"{CANONICAL_ORIGIN}/chattyhound_og.png"


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
    if profile.get("shelter_image_url"):
        return profile["shelter_image_url"]
    return DEFAULT_OG_IMAGE


def _build_meta_copy(profile):
    name = profile.get("name") or "This pup"
    age = _clean_age(profile.get("age") or "")
    shelter = profile.get("shelter_name") or "Pima Animal Care Center"
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
    active_res = (
        client.table("active_dogs")
        .select("animal_id, name, gender, age, weight")
        .eq("animal_id", animal_id)
        .limit(1)
        .execute()
    )
    prompts_res = (
        client.table("animal_fact_profiles")
        .select("animal_id, important_facts_jsonb")
        .eq("animal_id", animal_id)
        .limit(1)
        .execute()
    )
    profile_res = (
        client.table("animals").select("*").eq("animal_id", animal_id).limit(1).execute()
    )
    if not active_res.data or not profile_res.data:
        return None

    active_dog = active_res.data[0]
    profile = profile_res.data[0]
    profile["name"] = active_dog.get("name") or "Unknown"
    profile["gender"] = active_dog.get("gender") or "Unknown"
    profile["important_facts"] = (
        prompts_res.data[0].get("important_facts_jsonb", []) if prompts_res.data else []
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
    og_image_block = (
        f'<meta property="og:image" content="{img}">\n'
        f'  <meta property="og:image:secure_url" content="{img}">\n'
        f'  <meta property="og:image:alt" content="{esc(meta["og_title"])}">\n'
        f'  <meta property="og:image:type" content="image/jpeg">'
    )
    out = re.sub(
        r'<meta property="og:image" content="[^"]*">\s*'
        r'(?:<meta property="og:image:secure_url" content="[^"]*">\s*)?'
        r'(?:<meta property="og:image:alt" content="[^"]*">\s*)?'
        r'<meta property="og:image:type" content="[^"]*">\s*'
        r'<meta property="og:image:width" content="[^"]*">\s*'
        r'<meta property="og:image:height" content="[^"]*">',
        og_image_block
        + '\n  <meta property="og:image:width" content="1024">'
        + '\n  <meta property="og:image:height" content="1024">',
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


def _index_html_candidates():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lambda_root = os.environ.get("LAMBDA_TASK_ROOT", "")
    cwd = os.getcwd()
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"),
        "/var/task/api/index.html",
        os.path.join(root, "public", "index.html"),
        os.path.join(cwd, "public", "index.html"),
        os.path.join(lambda_root, "public", "index.html") if lambda_root else "",
        "/var/task/public/index.html",
    ]
    seen = set()
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            yield path


def _fetch_index_html_from_origin():
    base = (
        os.environ.get("VERCEL_URL")
        or os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        or CANONICAL_ORIGIN
    )
    if not base.startswith("http"):
        base = "https://" + base
    url = base.rstrip("/") + "/index.html"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ChattyHound-dog-meta/1.0", "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def _load_index_html():
    global _INDEX_HTML_CACHE
    if _INDEX_HTML_CACHE is not None:
        return _INDEX_HTML_CACHE

    for path in _index_html_candidates():
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                _INDEX_HTML_CACHE = f.read()
                return _INDEX_HTML_CACHE

    debug_info = []
    try:
        debug_info.append(f"cwd={os.getcwd()}")
        debug_info.append(f"__file__={__file__}")
        debug_info.append(f"candidates={list(_index_html_candidates())}")
        for folder in ["/var/task", os.getcwd(), os.path.dirname(os.path.abspath(__file__))]:
            if os.path.isdir(folder):
                files = []
                for r, d, fs in os.walk(folder):
                    for file in fs:
                        files.append(os.path.relpath(os.path.join(r, file), folder))
                    if len(files) > 50:
                        files.append("...")
                        break
                debug_info.append(f"Files in {folder}: {files}")
            else:
                debug_info.append(f"{folder} is not a directory")
    except Exception as dbg_err:
        debug_info.append(f"failed to gather debug info: {dbg_err}")

    try:
        _INDEX_HTML_CACHE = _fetch_index_html_from_origin()
        return _INDEX_HTML_CACHE
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise RuntimeError(f"index.html not found: {err}. Debug: {'; '.join(debug_info)}") from err


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

            html_text = _load_index_html()

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
