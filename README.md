# TCGate — Cyberpunk TCG Database v0.4.0

Base indépendante destinée à TCGate. **Card Registry n'est pas requis pour l'alpha privée.**

## État du snapshot

- WNTC : **130 / 140 slots révélés et suivis**
- WNTC prêts dans le runtime : **125**
- 5 reveals récents sont explicitement suivis mais attendent encore la résolution complète de leurs métadonnées dans ce snapshot.
- 10 slots WNTC restent mécaniquement non révélés.
- 10 cartes exclusives aux deux starters sont intégrées.
- 2 promos autonomes sont suivies séparément : Rebecca est prête pour le runtime ; Lucyna Kushinada — Fresh Beginnings reste en métadonnées partielles et n’est pas exposée au runtime.
- 168 impressions sont enregistrées ; 133 ont actuellement une image exploitable par l'index Vision.

Cette version **ne prétend donc pas être la v1.0 finale du set** : elle suit proprement la reveal season sans inventer les données manquantes.

## Fichiers consommés par TCGate

- `manifest.json` : point d'entrée stable à utiliser depuis GitHub.
- `runtime/cards.min.json` : cartes sûres pour le runtime.
- `runtime/vision-index.json` : impressions avec image résolue.

TCGate peut pointer une seule fois sur l'URL RAW GitHub de `manifest.json`. Les mises à jour suivantes gardent le même chemin.


## Mise à jour depuis GitHub Actions

Après avoir placé ce package à la racine du dépôt GitHub :

1. ouvrir **Actions** ;
2. choisir **Build or update TCGate database** ;
3. cliquer sur **Run workflow**.

L’action vérifie les sources, écrit le résultat dans `staging/`, valide la base et reconstruit les fichiers `runtime/`. Elle commit les changements de staging/runtime si nécessaire.

**Sécurité Cyberpunk :** contrairement aux TCG disposant d’un export officiel exhaustif, les nouvelles données Cyberpunk ne sont pas promues aveuglément dans `data/`. Une entrée non résolue ou uniquement issue de la source secondaire reste en staging jusqu’à validation.

## Mise à jour pendant l'alpha privée

```bash
pip install -r requirements.txt
python source/sync.py
python scripts/validate_db.py
python scripts/build_runtime.py
```

`source/sync.py` **n'écrit jamais dans GitHub et ne remplace pas la production**. Il écrit uniquement dans `staging/`. Après inspection/validation, le dépôt GitHub est mis à jour manuellement.

## Sources

1. Galerie officielle Cyberpunk TCG / WeirdCo / NetDeck : autorité.
2. PUNKSIM SDK : accélérateur technique secondaire pour le repérage des cartes déjà révélées et une image de travail. Ses données ne doivent jamais écraser un champ officiel vérifié.

## Sécurité

- aucune suppression automatique ;
- aucune publication automatique ;
- une chute anormale de la source secondaire est bloquée ;
- les cartes sans nom/métadonnées résolues ne sont pas exposées dans le runtime ;
- Vision n'indexe jamais une impression sans image.
