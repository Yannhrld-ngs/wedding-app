/*
SELECT name
FROM sys.tables
ORDER BY name;^
*/

/*
CREATE TABLE test_invites_list (
    prenom VARCHAR(50) NOT NULL,
    nom VARCHAR(50),
    sexe VARCHAR(10) NOT NULL,
    categorie VARCHAR(50) NOT NULL,
    role VARCHAR(50),
    mail VARCHAR(100),
    PRIMARY KEY (prenom, nom)
); 
*/
Select * from test_guests;
