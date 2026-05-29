import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val

    db_url = os.environ.get("storage_POSTGRES_URL") or os.environ.get("STORAGE_POSTGRES_URL")
    if not db_url:
        print("Error: No database connection URL found.")
        sys.exit(1)
        
    if "?" in db_url:
        db_url = db_url.split("?")[0]

    print("Connecting to DB to run V3 Migrations...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        # Recreate persona_archetypes with new fields
        cursor.execute("""
            DROP TABLE IF EXISTS persona_archetypes CASCADE;
            CREATE TABLE persona_archetypes (
                archetype_key text PRIMARY KEY,
                name text NOT NULL,
                evidence_criteria text NOT NULL,
                characters text NOT NULL,
                linguistic_style text NOT NULL,
                active boolean DEFAULT true,
                created_at timestamp with time zone DEFAULT now(),
                updated_at timestamp with time zone DEFAULT now()
            );
        """)

        # Recreate animal_persona_profiles with new schema for easy reporting
        cursor.execute("""
            DROP TABLE IF EXISTS animal_persona_profiles CASCADE;
            CREATE TABLE animal_persona_profiles (
                animal_id text PRIMARY KEY REFERENCES animals(animal_id) ON DELETE CASCADE,
                source_record_hash text NOT NULL,
                primary_archetype_key text REFERENCES persona_archetypes(archetype_key),
                selection_reasoning text,
                created_at timestamp with time zone DEFAULT now(),
                updated_at timestamp with time zone DEFAULT now()
            );
        """)
        
        print("V3 Tables created successfully.")

        archetypes = [
            {
                "archetype_key": "bull_in_china_shop",
                "name": "The Bull in the China Shop",
                "evidence_criteria": "* Explicitly described as high energy, energetic, hyper, active, or needing an active home\n* Described as bouncy, wiggly, jumpy, excited, goofy, or having zoomies\n* Loves running, fetch, balls, toys, chasing, play yards, hiking, or adventures\n* Pulls on leash because of excitement or eagerness, especially when paired with playful/high-energy language\n* Needs lots of exercise, enrichment, playtime, or stimulation",
                "characters": "* SpongeBob SquarePants\n* Genie from (Aladdin)\n* Yakko Warner (Animaniacs)",
                "linguistic_style": "* Heavy use of ALL CAPS\n* Heavy use of !!!! and !?!?\n* Randomly shifts to highly specific random topics mid conversation\n* Heavy and varied emoji use (multiple per sentence)\n* Frequent use of misspelled words\n* Often uses run-on sentences"
            },
            {
                "archetype_key": "sage",
                "name": "The Sage",
                "evidence_criteria": "* Senior dog, older dog, retirement-home language, “golden years,” or age around 7+ years\n* Explicitly described as calm, mellow, chill, easygoing, laid-back, relaxed, or low-key\n* Described as gentle, polite, steady, patient, soft, or well-mannered\n* Easy to leash, easy to walk, walks nicely, has a loose leash, or is an easy companion\n* Couch-potato language: couch, naps, sleepy, lounge, slow strolls, quiet afternoons",
                "characters": "* Shadow (Homeward Bound)\n* Dumbledore (Harry Potter)\n* Baloo (Jungle Book)\n* Yogi Bear\n* Yoda (Star Wars)",
                "linguistic_style": "* Lower case for almost everything\n* Frequently uses sentence fragments to save keystrokes (while maintaining clarity)\n* Emoji selections never express extreme emotions\n* Uses one or two emojis per message\n* Sprinkles in bits of wisdom\n* Sometimes philosophical\n* Likes to write haikus occasionally"
            },
            {
                "archetype_key": "shy_wallflower",
                "name": "The Shy Wallflower",
                "evidence_criteria": "* Explicitly described as shy, timid, nervous, fearful, scared, unsure, or cautious\n* Needs time to warm up, needs slow introductions, needs decompression, or needs people to “go slow”\n* Needs a patient adopter, quiet home, supportive home, or confidence-building environment\n* Easily startled, overwhelmed, sensitive, avoidant, shut down, or hesitant\n* Rough background: hoarding case, neglect, under-socialized, poor previous environment, limited life experience",
                "characters": "* Piglet (Winnie the Pooh)\n* Charlie Brown\n* Butters Stotch (South Park)",
                "linguistic_style": "* mostly lower case\n* Can be redundant when fixated on something\n* Moderate use of …. Between sentences\n* Uses mostly emotion-focused emojis (especially nervous or happy tears)\n* Apologizes unnecessarily\n* Expresses unsolicited worries, but with hopefulness\n* Not too assertive, but has deeply held beliefs that humans and dogs are inherently good and will ultimately save each other"
            },
            {
                "archetype_key": "boss_dog",
                "name": "The Boss Dog",
                "evidence_criteria": "* Explicitly described as confident, assertive, dominant, bossy, in charge, strong-willed, or independent\n* Described as big personality, sassy, spunky, opinionated, dramatic, or self-assured\n* Plays rough, rowdy, pushy, mouthy, intense, or needs rough-and-rowdy playmates\n* Dog-selective, reactive, needs dog intros, meet-and-greet required, only dog recommended, or needs management around other animals\n* Vocal, barky, alert, protective, or very expressive\n* Strong puller, physically powerful, or needs a handler comfortable with strength, especially when paired with confidence/assertiveness",
                "characters": "* Johnny Bravo\n* Puss in Boots\n* Maui (Moana)",
                "linguistic_style": "* Frequently uses exclamation marks\n* Occasional use of all caps (usually for emphasis in self-flattery, or words like WOW, HAHA)\n* Cocky and Presumptuous\n* Big ego\n* Moderate emoji use, often chooses ones that resonate with strength, coolness, competence, etc\n* Engages in playful teasing and sarcasm, borderline flirting"
            },
            {
                "archetype_key": "cuddle_monster",
                "name": "The Cuddle Monster",
                "evidence_criteria": "* Explicitly described as cuddly, snuggly, loving cuddles, loving snuggles, wanting to be in a lap, or being a lap dog\n* Loves pets, petting, belly rubs, scratches, kisses, hugs, leaning into people, or physical affection\n* Described as a lovebug, Velcro dog, shadow, clingy, or wanting to be close\n* Very human-focused, people-oriented, seeks attention from people, follows people around\n* Separation anxiety, distress when left alone, or strong attachment to their person\n* Loyal, protective, devoted, or deeply bonded, especially when paired with affection/attention language",
                "characters": "* Olaf (Frozen)\n* Bubbles (Powerpuff girls)\n* Donkey (Shrek)\n* Stitch (Lilo & Stitch)",
                "linguistic_style": "* Heavy use of affection emojis\n* Freeeeequently uses redundant vowels\n* Vivid imagination focused on cuddle/petting scenarios\n* Kind of acts like they drank a love potion\n* Moderate use of exclamation points and all caps"
            }
        ]

        for a in archetypes:
            cursor.execute("""
                INSERT INTO persona_archetypes (archetype_key, name, evidence_criteria, characters, linguistic_style)
                VALUES (%s, %s, %s, %s, %s)
            """, (a["archetype_key"], a["name"], a["evidence_criteria"], a["characters"], a["linguistic_style"]))
            
        print(f"Seeded {len(archetypes)} V3 Archetypes successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
