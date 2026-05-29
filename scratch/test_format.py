import os, psycopg2
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

cursor.execute("SELECT shelter_id, age, weight, gender FROM active_dogs WHERE shelter_id = 'MUDDYPAWS'")
m_dogs = cursor.fetchall()
print("MUDDYPAWS:")
for d in m_dogs[:5]:
    print(d)

cursor.execute("SELECT shelter_id, age, weight, gender FROM active_dogs WHERE shelter_id = 'PIMA'")
p_dogs = cursor.fetchall()
print("PIMA:")
for d in p_dogs[:5]:
    print(d)
