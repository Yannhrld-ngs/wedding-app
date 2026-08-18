# Wedding App

Web app for managing wedding invites: sending invites, tracking RSVPs, check-in via QR code, seating, and an organizer dashboard.

## 1. Install

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure

- Copy `.env.example` to `.env` and fill in `SECRET_KEY` (any random string) and `BASE_URL`.
  `BREVO_API_KEY` + `SMTP_FROM` are only needed to send organizer password-reset emails.
- Edit `inputs/config.yaml` with the wedding's name, date, and venue info.
- Edit `inputs/invites_list.csv` with the guest list (columns: `prenom,nom,sexe,categorie,role,mail,contact`).

## 3. Create an organizer account

Add a row to `inputs/invites_list.csv` for the organizer with a `role` from
`ORGANIZER_ROLES` in `app/config.py` (e.g. `accueil`) and a valid `mail`. That
person then sets their own password via "mot de passe oublié" on the login
page (requires `BREVO_API_KEY` to be configured so the reset email can be sent).

## 4. Run

```bash
uvicorn app.main:app --reload
```

Or with Docker:

```bash
docker build -t wedding-app .
docker run -p 8000:8000 --env-file .env -v "$(pwd)/inputs:/app/inputs" -v "$(pwd)/data:/app/data" wedding-app
```

- Invite card : `http://localhost:8000/invite/nom-prenom-xxxx`
- Organizer login : `http://localhost:8000/organisateur/login`
- Dashboard : `http://localhost:8000/organisateur/dashboard`
- QR scan : `http://localhost:8000/organisateur/scan` (needs HTTPS or `localhost` for camera access)
