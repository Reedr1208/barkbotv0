const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: '.env.development.local' });
const supabaseUrl = process.env.SUPABASE_URL || process.env.storage_SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.storage_SUPABASE_SERVICE_ROLE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);
async function query() {
  const { data, error } = await supabase.from('shelters').select('*').eq('shelter_id', 'HHS');
  console.log(JSON.stringify(data, null, 2));
}
query();
