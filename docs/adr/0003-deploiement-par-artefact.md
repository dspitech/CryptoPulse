# 0003. Déploiement par artefact Blob et timer systemd

Statut : acceptée

## Contexte

Les TP déployaient en se connectant en SSH et en créant les fichiers à la main. Le but est zéro action manuelle et des mises à jour par simple `terraform apply`, sans recréer la VM ni exposer SSH.

## Décision

Terraform empaquette le dossier `app/` en `app.zip` et le publie dans le container `artifacts`. Un timer systemd sur la VM compare l'ETag de l'artefact toutes les 5 minutes. S'il change, les fichiers sont synchronisés en place avec `rsync --inplace` (les bind mounts Docker restent valides) puis `deploy.sh` relance la stack. Le cloud-init ne contient que le strict minimum, de sorte que modifier le code n'oblige jamais à recréer la VM.

## Alternatives écartées

- **git clone au démarrage** : exige un dépôt public ou un jeton Git sur la VM.
- **Provisioners Terraform en SSH** : fragile, impose d'ouvrir SSH et de garder les clés côté Terraform.
- **Image Docker poussée dans un registre** : plus propre à terme, mais ajoute un ACR et un pipeline de build.

## Conséquences

- Les secrets locaux ne doivent jamais entrer dans l'artefact : `archive_file` exclut `.env.local`, les tests et les fichiers de développement.
- Un changement dans `app/` est déployé en moins de 5 minutes, sans interruption de la VM.
- Les scripts ajoutés au cloud-init (sync, unités systemd) restent figés à la création de la VM, d'où leur petit nombre.
