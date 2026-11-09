# Discover Pakistan Tourism

Website for Discover Pakistan Tourism: private tours across Pakistan, Al-Maaz Hotel and Dervash Restaurant on The Mall, Murree, partner stays at Hotel Felton, and private transport.

Live site: https://xumair604-crypto.github.io/discover-pakistan-tourism/

## What is on the site
- Tours with day-by-day sample plans, inclusions, best season, search, filters and side-by-side compare. Prices are intentionally not shown; the owners share costs with each customer directly.
- Destinations in route order: Murree, Galiyat (Ayubia, Nathia Gali), Abbottabad, Mansehra and Balakot, Kaghan Valley (Kiwai, Shogran, Siri Paye, Naran), Kashmir, Swat and Kalam, Skardu, Hunza and Khunjerab (China border), then Islamabad and Lahore city tours.
- Group, family, school, college and university tours, with meal plans (breakfast, hi-tea, lunch, dinner, buffets, half and full board).
- Special discount offers (details shared on request).
- Hotels we book: Al-Maaz (own), Hotel Felton, Ramada by Wyndham Murree, Mövenpick Centaurus Islamabad and partner hotels in Ayubia, Nathia Gali, Shogran and Naran.
- Group meals and buffets: Ramada by Wyndham Islamabad, Usmania Restaurant Murree, Dervash Restaurant (own).
- Mobile numbers only (no landline numbers).
- Private transport, a custom trip builder, travel information (seasons, visas, roads, packing) and three travel guides.
- Map, FAQs, privacy policy and booking terms.
- Every enquiry opens WhatsApp with the details filled in. Hotel Felton enquiries go to Hotel Felton's number; everything else goes to the main number.
- SEO: page description, Open Graph tags and schema.org data (TravelAgency, Hotel, Restaurant). Light and dark mode.

## Backend: bookings and admin (Supabase)
The site stays on GitHub Pages. Supabase (free plan) stores bookings and website content, and owners manage both at **`admin.html`**:
https://xumair604-crypto.github.io/discover-pakistan-tourism/admin.html

- **Bookings:** every enquiry form and trip builder submission is saved with a reference number (like `DP-7K2M9Q`), which also appears in the customer's WhatsApp message. Owners can filter and search, set a status (new, contacted, quoted, confirmed, completed, cancelled), keep a private rate and notes, reply on WhatsApp, call, email and export to CSV.
- **Website content:** add, edit, hide or reorder tours, special offers, hotels and buffet venues. Changes show on the website on the next page load.
- **Security:** visitors can only send bookings and read published content. Only emails in the `admins` table can see bookings or change content (rules in `supabase/schema.sql`).
- **Fallback:** if Supabase is not set up or cannot be reached, the website shows its built-in content and enquiries still go to WhatsApp.

### One-time setup (about 15 minutes)
1. Create a free account and a new project at https://supabase.com (choose a region close to Pakistan, such as Mumbai or Singapore).
2. Open **SQL Editor**, paste the contents of `supabase/schema.sql`, and press **Run**. Then do the same with `supabase/seed.sql` (this copies the current tours, offers, hotels and venues into the database).
3. Create owner logins: **Authentication > Users > Add user**, enter each owner's email and a password, and tick "Auto confirm user".
4. Allow those emails into the admin page. In the SQL Editor run, with your real emails:
   ```sql
   insert into public.admins (email) values ('owner1@example.com'), ('owner2@example.com');
   ```
5. Stop strangers creating accounts: **Authentication > Sign In / Providers**, turn off **Allow new users to sign up**.
6. For password reset emails: **Authentication > URL Configuration**, set Site URL to `https://xumair604-crypto.github.io/discover-pakistan-tourism/admin.html`.
7. Copy **Project URL** and the **anon public key** (Project Settings > API, or the "Connect" button) into `config.js`, then commit it. Never use the `service_role` / secret key.

To add or remove an owner later, repeat steps 3 and 4 (or `delete from public.admins where email = '...';`).

## Editing content without the admin page
The built-in fallback content is the `TOURS` list near the bottom of `index.html`, in route order. Once Supabase is set up, edit tours in `admin.html` instead.

- **Itineraries:** edit the `plan` lines, `incl` (included) and `excl` (not included).
- **Guides and policies:** edit the `GUIDES` and `POLICIES` text in the same script.

## Photos
Destination photos are real photographs from Wikimedia Commons, credited in the footer under "Photo credits". Replace the hotel and restaurant section photos with your own photography of Al-Maaz Hotel and Dervash Restaurant when available.

## Publish with GitHub Pages
Settings, Pages, Deploy from a branch, branch `main`, folder `/ (root)`.
