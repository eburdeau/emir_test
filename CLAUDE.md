# EMIR Refit - DATREC Parser

## Objectif du projet

Produire et tester une fonction Python qui **met à plat** (aplatit / dénormalise) des fichiers XML conformes au schéma **auth.091.001.02 DATREC** (DerivativesTradeReportReconciliationStatisticalReport) en un `pandas.DataFrame`, avec export CSV optionnel.

Ces fichiers sont envoyés par les référentiels centraux (Trade Repositories) aux contreparties déclarantes pour rapporter les statistiques de réconciliation des dérivés (EMIR Refit, ESMA).

---

## Stack technique

- **Python 3.11+**
- **lxml** — parsing XML avec support streaming (`iterparse`) pour les gros fichiers
- **pandas** — sortie DataFrame
- **pytest** — framework de test
- Pas de dépendances lourdes supplémentaires

---

## Structure du projet

```
emir_refit_-_outgoing_messages_-_final_-_v1.0.0/
├── CLAUDE.md                          ← ce fichier
├── EMIR Refit - Outgoing Messages - FINAL - V1.1.0/
│   ├── auth.091.001.02_ESMAUG_DATREC_1.0.0.xsd   ← schéma de référence
│   ├── auth.091.001.02_ESMAUG_DATREC_1.0.0.xlsx  ← dictionnaire de données
│   ├── head.001.001.01_ESMA_restricted.xsd        ← BAH header
│   └── ...autres messages EMIR...
├── src/
│   └── datrec_parser/
│       ├── __init__.py
│       ├── parser.py        ← fonction principale flatten_datrec()
│       └── schema.py        ← constantes namespaces, chemins XPath
├── tests/
│   ├── fixtures/            ← fichiers XML de test
│   └── test_parser.py
├── pyproject.toml
└── requirements.txt
```

---

## Schéma XML DATREC — structure clé

**Namespace** : `urn:iso:std:iso:20022:tech:xsd:auth.091.001.02`  
**Préfixe conventionnel** : `auth091`

**Arborescence du message** :
```
Document
└── DerivsTradRcncltnSttstclRpt   (DerivativesTradeReconciliationStatisticalReportV02)
    └── RcncltnSttstcs             (StatisticsPerCounterparty15Choice__1)
        ├── [par contrepartie / choix]
        └── ...données de réconciliation...
```

Le fichier peut être accompagné d'un **Business Application Header** (`head.001.001.01`) dans une enveloppe, ou livré seul.

**Namespace BAH** : `urn:iso:std:iso:20022:tech:xsd:head.001.001.01`

---

## Règles de développement

### Namespaces XML
- Conserver et gérer les namespaces **explicitement** — ne pas les stripper.
- Déclarer les namespaces comme constantes dans `schema.py`, pas en dur dans le parseur.

```python
# schema.py
NS = {
    "auth091": "urn:iso:std:iso:20022:tech:xsd:auth.091.001.02",
    "head":    "urn:iso:std:iso:20022:tech:xsd:head.001.001.01",
}
```

### Gros fichiers
- Utiliser **`lxml.etree.iterparse`** avec `tag` filtering pour éviter de charger tout le DOM en mémoire.
- Libérer les éléments traités avec `elem.clear()` + suppression des références ascendantes.

### Sortie
- La fonction principale retourne un `pandas.DataFrame` (une ligne = un enregistrement de réconciliation).
- Un paramètre optionnel `output_csv: str | Path | None = None` déclenche l'export CSV.
- Nommage des colonnes : chemin XPath simplifié avec `__` comme séparateur de niveau  
  (ex. `RcncltnSttstcs__CtrPty__Id`).

### Signature cible

```python
def flatten_datrec(
    xml_path: str | Path,
    output_csv: str | Path | None = None,
    validate: bool = False,
) -> pd.DataFrame:
    ...
```

- `xml_path` : chemin vers le fichier XML DATREC
- `output_csv` : si fourni, écrit le CSV à ce chemin
- `validate` : si True, valide le XML contre le XSD avant parsing (optionnel, coûteux)

---

## Tests

- Framework : **pytest**
- Fixtures XML dans `tests/fixtures/` — fichiers XML minimalistes représentant les cas métier
- Cas à couvrir :
  - Fichier XML valide complet → DataFrame avec le bon nombre de lignes et colonnes
  - Fichier avec éléments optionnels absents → colonnes présentes avec `NaN`
  - Export CSV → fichier créé et lisible
  - Fichier volumineux (streaming) → pas d'explosion mémoire

### Commandes

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer les tests
pytest tests/ -v

# Lancer avec couverture
pytest tests/ --cov=src/datrec_parser --cov-report=term-missing
```

---

## Fichiers de référence

| Fichier | Rôle |
|---|---|
| `auth.091.001.02_ESMAUG_DATREC_1.0.0.xsd` | Schéma XSD — source de vérité |
| `auth.091.001.02_ESMAUG_DATREC_1.0.0.xlsx` | Dictionnaire des champs (noms, cardinalités, types) |
| `auth.091.001.02_ESMAUG_DATREC_1.0.0.pdf` | Documentation narrative |
| `head.001.001.01_ESMA_restricted.xsd` | Schéma du Business Application Header |
