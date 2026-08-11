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

## Running the app from CLI

```bash
uvicorn app.main:app --reload
```

## Running the app from docker

```bash
docker build -t wedding-app .
```
```bash
docker run -p 8000:8000 --env-file .env -v "$(pwd)/inputs:/app/inputs" -v "$(pwd)/data:/app/data" wedding-app
```
  
- Invit card link : `http://localhost:8000/invite/nom-prenom-xxxx`
- Login organizer : `http://localhost:8000/organisateur/login`
- Dashboard : `http://localhost:8000/organisateur/dashboard`
- QR Scan : `http://localhost:8000/organisateur/scan` (nécessite HTTPS ou
  localhost pour l'accès caméra du navigateur)