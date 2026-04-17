# Syntetisk-kart

Syntetisk-kart er et Python-prosjekt som genererer syntetiske GIS-data for et avgrenset område i Norge i UTM-koordinater. Målet er å bygge opp et komplett kartdatasett med realistisk sammenheng mellom terreng, vann, vegnett, bygninger og AR5-arealtyper.

Se også [Oppgavebeskrivelse.md](Oppgavebeskrivelse.md) for full oppgavebeskrivelse og videre plan.

## Siste skjermdump

![Siste skjermdump av kartresultat](skjermdumper/Skjermbilde%202026-04-17%20kl.%2023.19.18.png)

## Status

Foreløpig er disse N50-lagene implementert og verifisert:

- én sammenhengende N50-kystkontur
- lukket havflate basert på kystkonturen
- N50-StedsnavnTekst som 3D-punkt for tettsteder
- N50-VegSenterlinje som 3D-linjer mellom tettsteder
- tilfeldig generering med ny seed for hver kjøring
- tester for geometri, variasjon og robusthet

## Teknologi

Prosjektet bruker blant annet:

- Python 3.9+
- GeoPandas
- Shapely
- NumPy
- Pyogrio
- CRS: EPSG:25833

## Arkitektur

Løsningen er bygd modulært:

- `synthetic_map.py` er orkestrator og samler all konfigurasjon
- N50-logikken ligger i `src/syntetisk_kart/synthetic_n50_module.py`
- foreløpig genereres kystkontur, havflate, tettsteder og vegsenterlinjer i N50
- videre temalag for høydekurver, vann, bygninger og AR5 kommer i egne moduler

## Kjøring

Kjør generatoren slik:

```bash
PYTHONPATH=src .venv/bin/python -m syntetisk_kart.main
```

For reproducerbar kjøring kan du oppgi egen seed:

```bash
PYTHONPATH=src .venv/bin/python synthetic_map.py --seed 12345
```

## Output

Ved kjøring opprettes foreløpig:

- `N50.gpkg`
  - laget `n50_kystkontur`
  - laget `n50_havflate`
  - laget `n50_stedsnavntekst`
  - laget `n50_vegsenterlinje`

## Konfigurasjon

Sentrale parametre ligger i `synthetic_map.py`, blant annet:

- bbox og koordinatsystem
- antall mulige kystsider
- avstand fra bbox til kystlinje
- hvor langt hjørnepunkter kan trekkes inn fra hjørnene
- hvor mye kystlinjen kan variere rekursivt
- antall tettsteder og spredning mellom dem
- vegparametre for riksveg, blant annet segmentlengde, vegbredde og bueradius `150–250 m`

## Testing

Kjør testene slik:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

