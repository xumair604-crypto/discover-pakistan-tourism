/*
  Supabase settings for the website and admin.html.

  Fill these in from Supabase: Project Settings > API (or "Connect").
  - supabaseUrl:     the Project URL, like https://abcdefgh.supabase.co
  - supabaseAnonKey: the "anon" / "publishable" public key

  The anon key is designed to be public. The database security rules in
  supabase/schema.sql decide what it can do (visitors can only send
  bookings and read published content). NEVER put the "service_role" or
  "secret" key here.

  While these are empty, the website uses its built-in content and
  enquiries go to WhatsApp only.
*/
window.DP_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: ""
};
