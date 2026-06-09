import re

with open('api/index.html', 'r') as f:
    content = f.read()

content = content.replace('formatRelativeTime(dog.updated_at)', 'formatRelativeTime(dog.info_refreshed_at)')

with open('api/index.html', 'w') as f:
    f.write(content)
