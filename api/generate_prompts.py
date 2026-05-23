import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List
from pathlib import Path
from pydantic import BaseModel, Field
from openai import OpenAI
from supabase import create_client
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# For parsing structured outputs, use a model that supports it
PROMPT_GENERATION_MODEL = "gpt-5.4-mini"

class DogPromptPackage(BaseModel):
    system_prompt: str = Field(
        description="The complete final system prompt to use for this specific dog's chat persona."
    )
    important_facts: List[str] = Field(
        description="Important factual adoption notes that should be preserved and surfaced when relevant."
    )
    risk_flags: List[str] = Field(
        description="Safety, behavior, medical, handling, or placement concerns that should not be minimized."
    )
    unknowns: List[str] = Field(
        description="Relevant adoption or behavior details that are not known from the animal record."
    )
    ideal_home_summary: str = Field(
        description="Plain-English summary of the kind of home likely to be a good fit."
    )

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        start_time = time.time()
        logging.info("Starting generate_prompts job...")

        # Time limit in seconds (170 seconds = 2m 50s) to comfortably avoid 3m Vercel limit
        MAX_EXECUTION_TIME = 60
        try:
            # Setup clients
            supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                raise RuntimeError("Missing Supabase environment variables.")
                
            sb_client = create_client(supabase_url, supabase_key)
            openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            # Load template
            template_path = Path(__file__).resolve().parent.parent / "app" / "systemPromptTemplate.txt"
            if not template_path.exists():
                raise RuntimeError(f"Template not found at {template_path}")
            prompt_template = template_path.read_text(encoding="utf-8")

            # 1. Fetch active dogs from pima_all_dogs
            pima_res = sb_client.table("pima_all_dogs").select("animal_id").execute()
            active_ids = {row["animal_id"] for row in pima_res.data}
            
            if not active_ids:
                logging.info("No active dogs found in pima_all_dogs.")
                self._send_response(200, {"message": "No active dogs found"})
                return

            # 2. Fetch all animals with bio length checking
            # Since length() is tricky in REST without an RPC, fetch bio and animal_id for active dogs
            animals_res = sb_client.table("animals").select("animal_id, bio").execute()
            
            eligible_animal_ids = []
            for row in animals_res.data:
                aid = row["animal_id"]
                bio = row.get("bio") or ""
                if aid in active_ids and len(bio) > 1000:
                    eligible_animal_ids.append(aid)

            if not eligible_animal_ids:
                logging.info("No active dogs with bio length > 1000.")
                self._send_response(200, {"message": "No eligible dogs found"})
                return

            # 3. Fetch existing system_prompts
            prompts_res = sb_client.table("system_prompts").select("animal_id, updated_at").execute()
            existing_prompts = {row["animal_id"]: row["updated_at"] for row in prompts_res.data}

            # 4. Filter and sort targets
            three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
            
            targets = []
            for aid in eligible_animal_ids:
                if aid not in existing_prompts:
                    # Missing (highest priority, assign oldest possible time)
                    targets.append((aid, datetime.min.replace(tzinfo=timezone.utc)))
                else:
                    # Parse updated_at
                    # Supabase returns ISO format
                    dt_str = existing_prompts[aid]
                    try:
                        # Handle Python 3.10+ fromisoformat
                        if dt_str.endswith("Z"):
                            dt_str = dt_str[:-1] + "+00:00"
                        updated_at = datetime.fromisoformat(dt_str)
                    except ValueError:
                        # Fallback
                        updated_at = datetime.min.replace(tzinfo=timezone.utc)
                        
                    if updated_at < three_days_ago:
                        targets.append((aid, updated_at))

            # Sort by updated_at ascending (oldest/missing first)
            targets.sort(key=lambda x: x[1])
            
            target_ids = [t[0] for t in targets]
            logging.info(f"Found {len(target_ids)} dogs requiring prompt generation.")

            processed_count = 0
            
            # 5. Process loop
            for aid in target_ids:
                if time.time() - start_time > MAX_EXECUTION_TIME:
                    logging.info("Nearing execution time limit. Halting gracefully.")
                    break
                    
                logging.info(f"Processing animal_id: {aid}")
                
                # Fetch full animal record
                animal_record_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
                if not animal_record_res.data:
                    continue
                    
                animal_record = animal_record_res.data[0]
                
                # Strip developer fields before sending to LLM to save tokens/confusion
                internal_keys = ["id", "record_hash", "qa_status", "qa_notes", "created_at", "updated_at", "last_scrape_run_id", "data_updated"]
                for key in internal_keys:
                    animal_record.pop(key, None)

                # Generate prompt
                try:
                    response = openai_client.beta.chat.completions.parse(
                        model=PROMPT_GENERATION_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You generate high-quality system prompts for adoptable-dog chatbot personas. "
                                    "Your job is to transform an animal record and a reusable prompt template into a "
                                    "dog-specific system prompt. Preserve all adoption-relevant facts. Do not invent facts. "
                                    "Do not minimize safety or behavior concerns. Keep the final dog persona warm, lovable, "
                                    "honest, and useful for adoption/foster fit."
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    "Create a dog-specific system prompt package using the following template and animal record.\n\n"
                                    "Requirements:\n"
                                    "- Output must match the requested structured schema.\n"
                                    "- The system_prompt should be complete and ready to pass directly as a system message.\n"
                                    "- The system_prompt should be written as instructions for the live chat model.\n"
                                    "- Preserve serious facts such as bite history, stranger sensitivity, dog-selectivity, "
                                    "escape/containment needs, required introductions, medical notes, or adoption deadlines.\n"
                                    "- Do not include unsupported claims such as house-trained, kid-friendly, cat-friendly, "
                                    "dog-friendly, crate-trained, or safe off leash unless explicitly present in the record.\n"
                                    "- If the source record contains placeholders or unclear text, treat that as an unknown "
                                    "rather than filling it in.\n\n"
                                    f"PROMPT TEMPLATE:\n{prompt_template}\n\n"
                                    f"ANIMAL RECORD JSON:\n{json.dumps(animal_record, ensure_ascii=False)}"
                                ),
                            },
                        ],
                        response_format=DogPromptPackage,
                        temperature=0.4
                    )
                    
                    prompt_package = response.choices[0].message.parsed
                    
                    # Upsert to DB
                    upsert_data = prompt_package.model_dump()
                    upsert_data["animal_id"] = aid
                    
                    sb_client.table("system_prompts").upsert(upsert_data, on_conflict="animal_id").execute()
                    processed_count += 1
                    
                except Exception as gen_exc:
                    logging.error(f"Failed to generate/upsert for {aid}: {gen_exc}")

            elapsed = time.time() - start_time
            logging.info(f"Job completed. Processed {processed_count} prompts in {elapsed:.2f}s.")
            self._send_response(200, {"ok": True, "processed": processed_count, "elapsed_seconds": elapsed})
            
        except Exception as e:
            logging.exception("An unexpected error occurred in generate_prompts.")
            self._send_response(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        self.do_GET()

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
