# Passer à PostgreSQL

Le site marche déjà avec PostgreSQL : il suffit de lui donner l'adresse de la base dans `.env`.
Tous les tests passent sur PostgreSQL 16, y compris un vrai test où cinq personnes achètent le dernier billet
au même instant (une seule l'obtient).

## Sur votre ordinateur Windows

1. Installer PostgreSQL : https://www.postgresql.org/download/windows/ (programme d'installation « EDB »).
   Gardez le port 5432 et notez le mot de passe choisi pour l'utilisateur `postgres`.
   Inutile d'installer « Stack Builder » à la fin.
2. Créer la base. Ouvrez « SQL Shell (psql) » depuis le menu Démarrer, appuyez sur Entrée aux 4 premières
   questions, tapez le mot de passe, puis :
   ```
   CREATE DATABASE eventlead;
   \q
   ```
3. Copier vos données actuelles (SQLite) dans un fichier, dans PowerShell, dossier du projet :
   ```
   cd C:\Users\faitz\downloads\event_lead
   git pull
   python -m pip install -r requirements.txt
   python manage.py migrate
   python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -e admin.logentry --indent 1 -o donnees.json
   ```
   (Gardez bien `-o donnees.json` : avec `>` PowerShell abîme le fichier.)
4. Dire au site d'utiliser PostgreSQL : dans le fichier `.env` (copie de `.env.example` s'il n'existe pas),
   ajoutez une ligne, avec votre mot de passe :
   ```
   DATABASE_URL=postgres://postgres:VOTRE_MOT_DE_PASSE@localhost:5432/eventlead
   ```
   Si le mot de passe contient `@`, `:` ou `/`, choisissez-en un sans ces signes.
5. Créer les tables dans PostgreSQL, y remettre vos données, lancer le site :
   ```
   python manage.py migrate
   python manage.py loaddata donnees.json
   python manage.py runserver
   ```

Le fichier `db.sqlite3` n'est pas effacé : pour revenir en arrière, mettez `#` devant la ligne `DATABASE_URL`.
Une fois que tout marche, rangez `donnees.json` hors du projet (il contient les données des invités).

## En ligne

Chez l'hébergeur, créez une base PostgreSQL et mettez son adresse dans `DATABASE_URL` du `.env` du serveur.
Les mêmes étapes 3 et 5 copient les données si le site a déjà tourné ailleurs.
