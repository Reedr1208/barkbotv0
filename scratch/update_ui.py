import re

html_path = 'public/index.html'

with open(html_path, 'r') as f:
    content = f.read()

# Add formatRelativeTime function right before it's used or at the top of the script tag.
# We will just inject it before `async function fetchRandomDog` or similar.
format_fn = """
function formatRelativeTime(isoString) {
  if (!isoString) return 'Today';
  const updated = new Date(isoString);
  const now = new Date();
  const diffMs = now - updated;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) {
    return diffDays === 1 ? '1 day ago' : `${diffDays} days ago`;
  } else if (diffHours > 0) {
    return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
  } else {
    return 'Just now';
  }
}
"""

if 'function formatRelativeTime' not in content:
    content = content.replace('async function fetchRandomDog', format_fn + '\n    async function fetchRandomDog')

# Replacements
content = content.replace('d?.image_url', 'd?.shelter_image_url')
content = content.replace('dog?.located_at', 'dog?.shelter_name')
content = content.replace('dog.located_at', 'dog.shelter_name')
content = content.replace('dog.data_updated || \'Today\'', 'formatRelativeTime(dog.updated_at)')
content = content.replace('dog.image_url', 'dog.shelter_image_url')
content = content.replace('dog.url', 'dog.shelter_profile_url')
content = content.replace('d.located_at', 'd.shelter_name')
content = content.replace('d.url', 'd.shelter_profile_url')
content = content.replace('d.image_url', 'd.shelter_image_url')
content = content.replace('payload.url', 'payload.shelter_profile_url')

# In save_preferences.py or anywhere else? Wait, payload.url was in index.html for shareCurrentDog
# shareCurrentDog(btn, { animal_id: aid, name, located_at: loc });
# Wait, located_at: loc should be shelter_name: loc.
content = content.replace('located_at: loc', 'shelter_name: loc')

with open(html_path, 'w') as f:
    f.write(content)
print("Updated index.html")
