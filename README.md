# Syntetisk-kart

Syntetisk-kart er et Python-prosjekt som genererer syntetiske GIS-data for et avgrenset område i Norge i UTM-koordinater. Målet er å bygge opp et komplett kartdatasett med realistisk sammenheng mellom terreng, vann, vegnett, bygninger og AR5-arealtyper.

Se også [Oppgavebeskrivelse.md](Oppgavebeskrivelse.md) for full oppgavebeskrivelse og videre plan.

## Siste skjermdump

![Siste skjermdump av kartresultat](skjermdumper/Skjermbilde%202026-04-19%20kl.%2020.45.33.png)

Eksempel på syntetisk kart med kystkontur, tettsteder, vegsenterlinjer, terrengpunkter og glattede høydekurver.

## Status

Pipeline genererer og verifiserer følgende N50-lag:

- én sammenhengende N50-kystkontur
- lukket havflate basert på kystkonturen
- N50-StedsnavnTekst som 3D-punkt for tettsteder
- N50-VegSenterlinje som 3D-linjer mellom tettsteder
- N50-Terrengpunkt (inkl. fortetting nivå 4 og 5, fjellkjerner, flatepunkter)
- N50-høydekurver (med filtrering og Chaikin-glatting)
- tilfeldig generering med ny seed for hver kjøring
- alle parametre sentralisert i `synthetic_map.py`
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

Ved kjøring opprettes:

- `N50.gpkg` med følgende lag:
  - `n50_kystkontur`
  - `n50_havflate`
  - `n50_stedsnavntekst`
  - `n50_vegsenterlinje`
  - `n50_terrengpunkt`
  - `n50_hoydekurve`

## Konfigurasjon

Alle sentrale parametre og konfigurasjon ligger i `synthetic_map.py` og sendes eksplisitt til alle moduler. Eksempler:

- bbox og koordinatsystem (EPSG:25833)
- seed for tilfeldig generering
- kystparametre: antall sider, avstand fra bbox, variasjon
- tettsted: antall, kystandel, min/maks avstand, høyde, navn
- veg: segmentlengde, bueradius, sannsynlighet for rette strekninger
- terreng: punktavstand, fjellkjerner, flatepunkter, fortetting nivå 4 og 5
- høydekurver: ekvidistanse, min. lengde, antall glatte-iterasjoner (Chaikin)

## Testing

Kjør testene slik:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

