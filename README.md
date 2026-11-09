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

## Backend: bookings and admin (Python, PythonAnywhere)
The website stays on GitHub Pages. A small Python (Flask) server in the `backend/` folder stores bookings and website content in a SQLite database, and hosts the owners' dashboard at `/admin`.

- **Bookings:** every enquiry form and trip builder submission is saved with a reference number (like `DP-7K2M9Q`), which also appears in the customer's WhatsApp message. Owners can filter and search, set a status (new, contacted, quoted, confirmed, completed, cancelled), keep a private rate and notes, reply on WhatsApp, call, email and export to CSV.
- **Website content:** add, edit, hide or reorder tours, special offers, hotels and buffet venues. Changes show on the website within about a minute.
- **Security:** owner passwords are stored hashed; sign-in uses a secure cookie with CSRF protection and locks out after repeated wrong passwords. Only this website's address may send bookings, each visitor is rate-limited, and a hidden spam trap drops bot submissions. Visitors can never read bookings.
- **Fallback:** if the server is down or `config.js` is empty, the website shows its built-in content and enquiries still go to WhatsApp.

### Deploy on PythonAnywhere (free plan works)
1. Sign up at https://www.pythonanywhere.com and open a **Bash console** (Consoles tab).
2. Get the code and set it up (use the Python version you will pick in step 3, for example 3.13):
   ```bash
   git clone https://github.com/xumair604-crypto/discover-pakistan-tourism.git
   cd discover-pakistan-tourism/backend
   pip3.13 install --user -r requirements.txt
   python3.13 manage.py init
   python3.13 manage.py create-admin latif      # asks for a password
   python3.13 manage.py create-admin yaseen     # one login per owner
   ```
3. **Web** tab > **Add a new web app** > your free `yourusername.pythonanywhere.com` domain > **Manual configuration** > Python 3.13.
4. On the Web tab, open the **WSGI configuration file** link, delete everything in it, and paste the contents of `backend/pythonanywhere_wsgi.py` with `YOURUSERNAME` changed to your username. Save.
5. On the Web tab, turn on **Force HTTPS**, then press **Reload**.
6. Visit `https://yourusername.pythonanywhere.com/admin` and sign in.
7. Put the server address in `config.js` in this repository and commit it:
   ```js
   window.DP_CONFIG = { apiBase: "https://yourusername.pythonanywhere.com" };
   ```
   The website's `admin.html` will then forward owners to the dashboard too.

### Looking after it
- **Update the server after code changes:** in a Bash console run `cd ~/discover-pakistan-tourism && git pull`, then press **Reload** on the Web tab.
- **Owner logins:** `python3.13 manage.py create-admin NAME`, `set-password NAME`, `delete-admin NAME`, `list-admins` (run inside `backend/`). Owners can also change their own password from the dashboard.
- **New website address** (for example a custom domain): `python3.13 manage.py add-origin https://www.yourdomain.pk`, then Reload.
- **Backups:** `python3.13 manage.py backup` copies the database into `backend/instance/backups/`. On the Tasks tab you can schedule it daily: `python3.13 /home/yourusername/discover-pakistan-tourism/backend/manage.py backup`.
- **Free plan:** PythonAnywhere asks you to log in and click "Run until 3 months from today" on the Web tab every 3 months to keep a free web app running.
- **Tests:** `cd backend && python3.13 -m pytest -q` (install pytest first with `pip3.13 install --user pytest`).
- `backend/instance/` holds the secret key and the database. It is never committed to GitHub.

## Editing content without the admin page
The built-in fallback content is the `TOURS` list near the bottom of `index.html`, in route order. Once the backend is running, edit tours in its `/admin` dashboard instead.

- **Itineraries:** edit the `plan` lines, `incl` (included) and `excl` (not included).
- **Guides and policies:** edit the `GUIDES` and `POLICIES` text in the same script.

## Photos
Destination photos are real photographs from Wikimedia Commons, credited in the footer under "Photo credits". Replace the hotel and restaurant section photos with your own photography of Al-Maaz Hotel and Dervash Restaurant when available.

## Publish with GitHub Pages
Settings, Pages, Deploy from a branch, branch `main`, folder `/ (root)`.
