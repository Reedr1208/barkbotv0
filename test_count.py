import os
from supabase import create_client

with open('.env.local') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            os.environ[k] = v.strip('"\'')

c = create_client(os.environ['storage_SUPABASE_URL'], os.environ['storage_SUPABASE_SERVICE_ROLE_KEY'])

count = c.table('active_dogs').select('*', count='exact').execute()
print(f"Total active dogs: {count.count}")
