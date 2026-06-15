require('dotenv').config({ path: '.env.development.local' });
const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(
  process.env.storage_SUPABASE_URL || process.env.SUPABASE_URL,
  process.env.storage_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY
);

async function run() {
  const { data, error } = await supabase.from('shelters').select('*').eq('shelter_id', 'AHSCN');
  console.log(data);
}
run();
