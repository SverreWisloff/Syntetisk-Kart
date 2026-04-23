# Copilot-instruksjoner for Syntetisk-kart

## Status
- [x] Verify that the copilot-instructions.md file in the .github directory is created.
- [x] Clarify Project Requirements
- [x] Scaffold the Project
- [x] Customize the Project
- [x] Install Required Extensions
- [x] Compile the Project
- [x] Create and Run Task
- [x] Launch the Project
- [x] Ensure Documentation is Complete

## Oppsummering
- Grunnprosjektet for Python er opprettet i arbeidsområdet.
- Kildepakke, tester, dokumentasjon og kjøretask er inkludert.
- Prosjektet er verifisert ved kjøring og beståtte tester.

## Utviklingsregler

### Konfigurasjon og parametere
- `synthetic_map.py` er orkestrator og eneste sted for konfigurasjon.
- All konfigurasjon og alle parametere samles i orkestratorfilen.
- Funksjoner mottar alltid parametre som argumenter, aldri fra globale variabler eller hardkodede verdier.
- Legg aldri tallverdier direkte i modulkoden. Send dem alltid som parametere.
- Alle tallverdier som kan variere sendes via parametere, aldri hardkodet i modulen.
- Bruk `_merge_config(defaults, overrides)` for å slå sammen standardverdier med brukerparametre.
- Tilfeldig valg fra intervall brukes der variasjon er ønsket: `np.random.uniform(min, max)`.

### Koordinatsystem og geodata
- Alle `GeoDataFrame` som opprettes i koden skal få eksplisitt `crs=konfig["crs"]`, ikke stole på at CRS arves automatisk.
- Ved lagring til GeoPackage skal laget som skrives alltid komme fra en `GeoDataFrame` med eksplisitt CRS satt.
- Hvis et lag er tomt, skal tom `GeoDataFrame` fortsatt opprettes med korrekt `geometry`-kolonne og eksplisitt CRS.
- Ved innføring av nye lag eller moduler skal det legges inn en enkel test som verifiserer at laget har korrekt CRS.

### Modularkitektur
- Hver temamodul (`synthetic_*_module.py`) mottar parametre som argumenter, uten hardkoding av verdier i modulene.
- Moduler returnerer `dict` eller `GeoDataFrame`.
- Moduler skriver ikke til disk selv.

### Språk og dokumentasjon
- Funksjonsnavn, variabelnavn, kommentarer og docstrings skal skrives på norsk der det er praktisk mulig.
- README, oppgavebeskrivelse og commit-meldinger skal alltid være på norsk.

### Versjonskontroll
- `.gpkg`, `.gpkg-shm` og `.gpkg-wal` skal aldri sjekkes inn.

### Videre forbedringer
- Dersom det er naturlig å utvide instruksjonene, skal forslag gis med kort begrunnelse.


