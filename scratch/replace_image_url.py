import re

with open('api/index.html', 'r') as f:
    content = f.read()

# Replace all occurrences
content = content.replace('.image_public_url', '.shelter_image_url')
content = content.replace("dog.shelter_image_url || dog.shelter_image_url", "dog.shelter_image_url")

# Also let's replace sex_neuter_status with sex
content = content.replace('sex_neuter_status', 'sex')

with open('api/index.html', 'w') as f:
    f.write(content)
