## À faire


## En cours
- [] Modification du questionnaire , Ajout de date dans son calendrier.
- [ ] Implementer modif du questionnaire une semaine avant.
- [ ] Si scan différent du jour J, retourner un message, la fonctionalité sera activée le jour J
- [ ] Add loggin file 

## Fait
- [X] Modification invit: Ajout couleurs
- [X] Passage en MSSQL 
- [X] Orga - Creation de compte avec username et password à remplir automatiquement
- [x] Squelette FastAPI de base
- [x] Design templates Invitation
- [X] Deploiment sur le cloud
- [X] Home page: should contain html with two link: invite (ask invite code) / organisateur/login (organzer shal become organisateur). 
- [X] Automatic deployment: CI/CD 
- [X] In organisateur/dashbord, Add a link to share send the message message: "Bonjour {invite.nom} {Invite.prenom} \n, votre invivation vous a été envoyée via {DOMAIN}. Votre code d'accès est {invite.link[-4::]}. \n N'oubliez pas de confirmer votre présence. En espérant vous revoir bientôt, {WEDDING_NAME_1} & {WEDDING_NAME_2}"