# Wedding App — squelette

Web app for managing invites during a wedding: sending invites, checking confirmation, food restriction etc. 

A code QR is generated for each invites and must be scan the d day. 

For organizer, a web page is provided for tracking invite info. 


## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Personal information
Edit info in  `app/config.py` and `data/config.yml` or use environment variable

## Create an organizer account

```bash
python scripts/create_organizer.py admin password
```

## Invite Link

Run for getting invit link for all invites.
```bash
python scripts/sync_guests.py
```

## Running the app

```bash
uvicorn app.main:app --reload
```

- Invit card link : `http://localhost:8000/invite/nom-prenom-xxxx`
- Login organizer : `http://localhost:8000/organizer/login`
- Dashboard : `http://localhost:8000/organizer/dashboard`
- QR Scan : `http://localhost:8000/organizer/scan` (nécessite HTTPS ou
  localhost pour l'accès caméra du navigateur)