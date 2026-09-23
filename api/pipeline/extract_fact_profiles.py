import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class FactProfileExtraction(BaseModel):
    dog_name: str = Field(description="The dog's name.")
    intro_summary: Optional[str] = Field(description="A 5-7 sentence summary that is both informative and fun, highlighting the dog's unique features or fun quirks while also highlighting the most important standout info for the potential adopter to know.")
    age_summary: Optional[str] = Field(description="Short summary of age.")
    age_bucket: Optional[str] = Field(description="Age bucket category: 'Puppy (<1yr)', 'Young (1-3yrs)', 'Adult (3-7yrs)', 'Senior (8+yrs)', or 'N/A'.")
    weight_summary: Optional[str] = Field(description="Short summary of weight.")
    weight_class: Optional[str] = Field(description="Weight class category: 'Small (<25lbs)', 'Medium (25-60lbs)', 'Large (60+lbs)', or 'N/A'.")
    breed_or_description: Optional[str] = Field(description="Short summary of breed or visual description.")
    sex: Optional[str] = Field(description="Sex ('Male', 'Female', or 'N/A').")
    altered_status: Optional[str] = Field(description="Altered status ('Spayed', 'Neutered', 'Unaltered', or 'N/A').")
    location_detail: Optional[str] = Field(description="Detailed location note.")
    backstory_summary: Optional[str] = Field(description="Concise, factual summary of how they arrived and backstory.")
    highlights: List[str] = Field(description="2-4 short, punchy phrases (1-4 words each) highlighting what makes this dog lovable or uniquely awesome — positive traits only. Think 'what makes someone stop scrolling and fall in love'. Examples: 'Cuddle Bug', 'Gentle Giant', 'Total Sweetheart', 'Loyal Companion', 'Curious Explorer', 'Playful Goofball'. NEVER include sex, age, weight, breed, color, or any stat already displayed elsewhere. Always return at least 2.")
    important_facts_jsonb: List[str] = Field(description="2-5 short phrases (1-5 words each) of adoption-critical information a potential adopter must know. Focus on: special needs, house training status, compatibility with kids/dogs/cats, behavioral concerns, medical notes, containment needs, energy considerations. Examples: 'Needs Slow Intros', 'House Trained', 'No Small Children', 'Dog Selective', 'Leash Training Needed', 'On Medication', 'Escape Artist'. NEVER include sex, age, weight, breed, color, or physical stats. Always return at least 2.")
    risk_flags_jsonb: List[str] = Field(description="Array of short strings of risks (bites, escapes, etc).")
    unknowns_jsonb: List[str] = Field(description="Array of short strings of things explicitly unknown or ambiguous.")
    challenges_jsonb: List[str] = Field(description="Array of short strings of behavioral or medical challenges.")
    ideal_home_jsonb: List[str] = Field(description="Array of short strings describing ideal home environment.")
    management_notes_jsonb: List[str] = Field(description="Array of short strings for handling/management advice.")
    other_animals_notes: Optional[str] = Field(description="Plain-language summary of behavior with other animals.")
    people_notes: Optional[str] = Field(description="Plain-language summary of behavior with people/strangers/kids.")
    containment_notes: Optional[str] = Field(description="Plain-language summary of containment/yard/leash needs.")
    medical_notes: Optional[str] = Field(description="Plain-language summary of medical needs or status.")
    adoption_process_notes: Optional[str] = Field(description="Plain-language summary of adoption rules or deadlines.")
    energy_level: Optional[str] = Field(description="Energy level inferred from behavioral descriptions: 'calm', 'high', or 'N/A' if not determinable.")
    good_with_dogs: Optional[str] = Field(description="Good with other dogs: 'yes' if explicitly confirmed, 'no' if explicitly stated, or 'unknown' if not mentioned or ambiguous.")
    house_trained: Optional[str] = Field(description="House trained / potty trained: 'yes' if explicitly confirmed, 'no' if explicitly stated, or 'unknown' if not mentioned or ambiguous.")
    evidence_jsonb: List[str] = Field(description="List of exact short quotes used as evidence.")

def extract_fact_profile(openai_client: OpenAI, animal_record: dict) -> FactProfileExtraction:
    """
    Calls OpenAI to extract a factual profile from a raw animal record.
    """
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    with open(os.path.join(base_dir, "prompts/fact_profile_developer_prompt.txt"), "r") as f:
        developer_prompt = f.read()
        
    with open(os.path.join(base_dir, "prompts/fact_profile_user_prompt.txt"), "r") as f:
        user_prompt_template = f.read()

    user_prompt = user_prompt_template.format(
        RAW_ANIMAL_JSON=json.dumps(animal_record, ensure_ascii=False)
    )

    logging.info(f"Extracting facts for {animal_record.get('animal_id')}...")
    
    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=FactProfileExtraction
    )
    
    return response.choices[0].message.parsed
