import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('.env.local')

supabase_url = os.getenv('VITE_SUPABASE_URL')
supabase_key = os.getenv('VITE_SUPABASE_ANON_KEY')

if not supabase_url or not supabase_key:
    raise ValueError('Missing Supabase environment variables')

supabase: Client = create_client(supabase_url, supabase_key)
