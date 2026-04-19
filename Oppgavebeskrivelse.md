# Oppgavebeskrivelse for Syntetisk-kart

_Dette dokumentet beskriver oppgaven og kravene til prosjektet Syntetisk-kart._

Lag et Python-program som genererer et komplett syntetisk kartdatasett for et avgrenset område i Norge (UTM), med realistisk intern sammenheng mellom terreng, vann, vegnett, bygninger og AR5-arealtyper.

## Mål

Programmet skal produsere GIS-klare data i GeoPackage-format, der hvert tema ligger i egen fil og med konsistent geometri mellom lagene.

## Teknologi og rammer

- Språk: Python 3.9+
- Avhengigheter: GeoPandas, Shapely, NumPy, SciPy (Delaunay), Pandas/Fiona etter behov
- CRS: EPSG:25833
- Input: Ingen eksterne datasett (alt skal være syntetisk generert)
- Output: fem GeoPackage-filer

## Overordnet arkitektur

Bygg løsningen modulært med én orkestrator og temamoduler:

- `Syntetisk_Kart.py`: orkestrerer kjøring, konfig, avhengigheter og lagring
- `Syntetisk_N50.py`: TODO
- `Syntetisk_Veg.py`: vegsenterlinjer og vegkant
- `Syntetisk_Hoydekurve.py`: terrengpunkter, TIN, høydekurver
- `Syntetisk_Vann.py`: innsjøer, bekker/elv, myr
- `Syntetisk_Bygning.py`: bygningsflater
- `Syntetisk_AR5.py`: heldekkende AR5-flater med prioritet og clipping

## Overordnet plan for generering av syntetisk kart:
1) 🗺️ Lag først et Oversiktskart, N50. Dette er en slags disposisjon for overordnet kart.
    - a) Lag Sjøkant. Denne går langs kanten på området, og dekker minimul en side, men kan også gå rundt hele som en øy
    - b) Lag Tettsteder, jo større område - jo flere tettsteder
    - c) Lag Fylkesveger (senterlinje) mellom tettsteder
    - d) Legg på høyder på Tettsteder og Fylkesveger, Lag åser mellom riksveger, Lag noen flate områder også
2) 🚗 Lag Veger
3) ⛰️ Lag Høydekurver
4) 💧 Lag Vann 
5) 🏠 Lag Bygninger
6)    Lag AR5   

## De ulike kartlagene

1) N50
- Kartfil: N50.gpkg
- Modulskript: Syntetisk_N50.py
- Objekttyper: 
  - N50-Kystkontur(2D-kurve)  
  - N50-StedsnavnTekst(3D-Punkt, Egenskap: Navneobjekttype=By)
  - N50-VegSenterlinje(3D-linje)
  - N50-Terrengpunkt(3D-Punkt)
  - N50-Hoydekurve(2D-kurve)

2) Veg
- Kartfil: FKB-Veg.gpkg
- Modulskript: Syntetisk_Veg.py
- Objekttyper: 
    - FKB-Vegdekkekant(3D-kurve)
    - FKB-VegSenterlinje(3D-kurve)

3) Høydekurve
- Kartfil: FKB-Hoydekurve.gpkg
- Modulskript: Syntetisk_Hoydekurve.py
- Objekttyper: 
  - TIN-Punkt(3D-Punkt)
  - TIN-Trekant
  - FKB-Hoydekurve(2D-kurve, egenskap:Høyde)

4) Vann
- Kartfil: FKB-Vann.gpkg
- Modulskript: Syntetisk_Vann.py
- Objekttyper: 
  - FKB-Vann

5) Bygning
- Kartfil: FKB-Bygning.gpkg
- Modulskript: Syntetisk_Bygning.py
- Objekttyper: 
  - FKB-Takkant

6) AR50
- <TODO>

## Algoritmer for generering av objekttyper

### N50-Kystkontur (2D-kurve) 
Kystkontur skal alltid følge 4 kanter, slik at det lages en øy hver gang.
Det skal være én sammenhengende kystlinje som går rundt hele øya.
Ved generering av hjørnepunkter skal disse ikke være plassert helt ut i hjørnet, men tilfeldig inntil 30%inn fra hjørnekanten.
For de kantene som skal ha kystkontur, lag kystkontur som en rett linje 300m fra ytterkanten av bbox.
Linje deles i to, og midtpunktet forskyves fra linjen med en tilfeldig verdi < Linjeavtande/3. Prosessen gjentas rekursivt for de nye linjesegmentene for å skape ujevnheter, inntil linjeavstand er <1m. Sjekk for at linjen ikke krysser bbox eller kystkontur.
Lag et lukket polygon av havet med kystkontur

### N50-StedsnavnTekst (3D-Punkt)
N50-StedsnavnTekst er objekttypen som beskriver tettsted. Dette er en 3D-punkt. 
Området skal ha minst to StedsnavnTekst, jo større område - jo flere tettsteder.
Minst ett kyst-tettsted skal ligge 200m ved kysten, med høyde=15m.
Minst ett innlands-tettsted lengst fra kysten, med høyde=avstand til kyst / 20.
Det skal være tettsteder ved kysten med tilfeldig avstand mellom 2km og 6km. Tettstedene ved kysten har høyde=15m
Generer flere innlands-tettsteder slik at avstanden mellom tettsteder har avstand mellom 2km og 6km.  Høyde=avstand til kyst / 20.

### N50-VegSenterlinje (3D-linje)
Lag rette linjer som N50-VegSenterlinje mellom tettstedene etter TIN-prinsippet.
Generer tilfeldig horisontalkurvatur på veiene. Bruk "Veggenereringsalgoritmen" med parametre for Riksveg. Vegbredde=10 m. Bueradius=tilfeldig tall for hver sving i intervallet[150, 250] m. Segmentlengde=bueradius * tilfeldig faktor i intervallet [1.0, 1.6]
Veger skal ikke krysses, og ikke krysse kystkontur.
Legg på høyden på alle punkter i VegSenterlinje: Start og slutt på alle veger er på et tettsted, hent høyden fra disse punktene. Senterlinje deles i to, og midtpunktet er snitt av de to endepunkthøydene, pluss/minus et tilfeldig tall < Linjeavtande/40. Prosessen gjentas rekursivt inntill alle punkter i N50-VegSenterlinje har høyde.

#### Veggenereringsalgoritmen
Startpunkt og endepunkt.
Vegen bygges iterativt fra start mot slutt som en polyline. 
Hver iterasjon 
 - beregnes retningen fra nåværende punkt mot målet.
 - enten et buesegment med tilfeldig radius og tilfeldig segmentlengde, eller et rett-segment med tilfeldig lengde. Buesegment og rett-segment har minimum og maksimumverdi.
 - Maksimal lengde på rett veg-segment = lengde på bue-segment
 - La segmentlengde for hvert buesegment beregnes som segmentets radius * (tilfeldig tall i intervallet [1.0 , 1.6])
 - hvis buesegmentet: sirkelbue som er tangent til forrige retning. Radiusens fortegn bestemmes av om vegen må dreie mot høyre eller venstre for å nærme seg målretningen/endepunktet. 
 - hvis rett-segment: Sjekk om antall påfølgende rettstrekk er overskredet, da velges buesegment
 - Fra et segment til et annet skal det være tangentkontinuitet.
 - Når vegen er nær nok endepunktet(<3*segmentlengden), legges siste del inn som bue mot avslutning mot målet. Buen beregnes slik at den er tangent-kontinuerlig, og avsluttes i endepunkt.
 Til slutt valideres kandidatlinjen. Hvis linjen krysser seg selv, eller er nærmere en annen veg enn 15m, forkastes den og algoritmen prøver på nytt opptil et gitt antall forsøk.

### N50-Terrengpunkt (3D-Punkt)
Tettsteder ligger i daler. Nå skal det genereres punkter for fjell.
Dette skjer gjennom flere itterasjoner:
#### Nivå1:
- Plukk ut terrengpunkter som senere skal brukes til å generere TIN:
- Bruk parametre for avstand mellom Tettsteder, som er et intervall. Bruk parameter for nederste grense av intervallet som nivåets-punkt-tetthet. 
- Langs Kystlinje plukk ut punkt slik at avstanden mellom punktene er oppunder nivåets-punkt-tetthet.
- Langs veg plukk ut punkt ikke nærmere hverandre enn nivåets-punkt-tetthet.
- Alle Tettstedene er med i utvalget av terrengpunkter
- Lagre alle terrengpunktene i Nivå1, med høyde.
Bygg TIN
#### Nivå2:
- I hver TIN-trekant generer ett terrengpunkt i miten av TIN-trekanten. 
- Terrengpunkt-høyden = (TIN-interpolerte høyden for midtpunktet) + Tilfeldig tall i intervallet [100, 400]
Bygg TIN
#### Nivå3:
For hver trekant genereres nye punkter inne i trekanten.
AntallPunktPrTrekant=5
Høyden på nye punkt er TIN-interpolert høyde for x,y + tilfeldig verdi med MaxAvvikFraTIN=3.0
Bygg TIN
#### Nivå4:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=1.0
Bygg TIN
#### Nivå5:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=0.4
Bygg TIN
#### Nivå6:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=0.1
Bygg TIN

### N50-Hoydekurve (2D-kurve)
Generer TIN.
Generer Hoydekurver med ekvidistande=20m basert på TIN.

----------------------------------------------------------------------------
**HIT HAR JEG KOMMET**
----------------------------------------------------------------------------

### 1. Terreng
Målet er å generere objekttypen Høydekurve

1) primær-TIN-punkter:
4 hjørnepunkter med tilfeldig høyde.
Antall primærpunkter med tilfeldig høyde: 15
Bygg TIN

2) sekundærpunkter-TIN-punkter:
For hver trekant genereres nye punkter inne i trekanten.
AntallPunktPrTrekant=5
Høyden på nye punkt er TIN-interpolert høyde for x,y + tilfeldig verdi med MaxAvvikFraTIN=3.0
Bygg TIN

3) tertiær-TIN-punkter:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=1.0
Bygg TIN

4) kvaternær-TIN-punkter:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=0.4
Bygg TIN

5) kvintær-TIN-punkter:
AntallPunktPrTrekant=3
MaxAvvikFraTIN=0.1
Bygg TIN

Kurvegenerering:
Lag høydekurver med ekvidistanse=1m
Lagre høyden som egenskap på hver enkelt kurve
Fjern kurver kortere enn = 50 m
Glatt kurver.


## 2. Vann
Bruk TIN og høydekurver fra Terreng for å lage objekttypene Innsjøkant, MyrGrense og ElvBekk


### Innsjøkant:
Områder som er en grop, eller "lukket" lavpunkt, er kandidat for innsjø.
Objekttypen Innsjøkant er et lukket polygon.
Høydekurver som er lukket, og som har 1, 2 eller 3 lukkede høydekurver inni seg med lavere høyde er kandidat for innsjø. La da Innsjøkant følge denne høydekurven.
Store Innsjøkant-polygoner, reduseres ved å bruke en av de høydekurvene som ligger inni som Innsjøkant. 

### ElvBekk:
Jeg har en syntetisk terrengmodell. Både TIN og høydekurver. Ønsker å generere vann og bekk. Ikke raster, men vektor. Hvordan? Hvilke algoritmer? Har hørt om ‘TIN-based Flow Accumulation’.

Inn til hver sjø rener det 0,1 eller 2 bekker. De er plassert oppover, men ikke langs rygger, men helst i søkk. 
Lengden på bekk inn til sjø er mellom 100m og 500m
Ut fra hvert vann kan det renne 1 bekk. Ettersom innsjøen er i grop, må det noen ganger klatres opp en høydekurve eller to før en finner en vei nedover. Denne skal følge avrenning, altså fallretningene fra gradienten på TIN-trekanten. 
Lengden på bekk ut av en sjø er mellom 300m og 700m 

### MyrGrense:
Noen av de aller flateste områdene defineres som myr
Noen ganger kommer to myr-flater rett ved siden av hverandre. Slå disse sammen til en flate

Organiser alle parametre samlet i hoved-skriptet. 
Dokumenter alle parametre i readme

## 3. Vegnett
Målet er å generere objekttypen SenterlinjeVeg, og Vegkant

### Nivåer på veger:
Riksveg: Mellom tettsteder. Vegbredde=10 m. Bueradius=[150, 250] m.
Kommunalveg: Fortetting i tettsted. Vegbredde=5 m. Bueradius=[70, 100] m. 
Privat veg (avkjørsel): Veg inn til eiendommer. Vegbredde=4 m. Genereres som rett 2-punktslinje. Lengde=[10, 50] m.
Segmentlengde og bueradius styres per vegtype i konfigurasjonen (ikke nødvendigvis like).

### Veg konstrueres slik:
Startpunkt og endepunkt.
Vegen bygges iterativt fra start mot slutt som en polyline. 
Hver iterasjon 
 - beregnes retningen fra nåværende punkt mot målet.
 - enten et buesegment med tilfeldig radius og tilfeldig segmentlengde, eller et rett-segment med tilfeldig lengde. Buesegment og rett-segment har minimum og maksimumverdi.
 - hvis buesegmentet: sirkelbue som er tangent til forrige retning. Radiusens fortegn bestemmes av om vegen må dreie mot høyre eller venstre for å nærme seg målretningen/endepunktet. 
 - hvis rett-segment: Sjekk om antall påfølgende rettstrekk er overskredet, da velges buesegment
 - Når vegen er nær nok endepunktet, legges siste del inn som en rett interpolert avslutning mot målet.
 Til slutt valideres kandidatlinjen. Hvis linjen krysser seg selv, eller er nærmere en annen veg enn 15m, forkastes den og algoritmen prøver på nytt opptil et gitt antall forsøk.

### Private avkjørsler:
Parametre: MinLengdeFraKryss=50 m. AvstandMellomPrivateAvkjørsler=[70, 120] m.
Parametre: MinLengde=10 m, Makslengde=50 m for private avkjørsler.
Retningen er normalvektor 90 grader på tangent til veien den går ut fra. 

## 4. Bygninger
Målet er å generere objekttypen Takkant.
- Plasser bygninger i grupper ved private avkjørsler.
- Bruk minst to bygningstyper (rektangulær, L-formet).
- Filtrer/sanér bygg som kolliderer med veg eller ligger for nær hovedveg.

Generer Bygninger i eget kartlag: synthetic_bygning.gpkg
To typer Bygninger: Rektangulært, og L-formet. 
Parametre for husstørrelse er BygningSizeMin=6 meter, BygningSizeMax=25 meter. AvstandMellomBygningGruppe=5 meter.
Retningen på en bygning er tilfeldig.
Lag Bygningsgrupper på 2 eller 3 bygninger. Avstandene mellom bygningene innad i en Bygningsgruppe er AvstandMellomBygningGruppe.
For hver PrivatAvkjørsel genereres en Bygningsgruppe.
Dersom to bygninger overlapper hverandre, slettes den minste Bygningen
Dersom en bygninger overlapper med veg, slettes Bygningen
Bygninger som er nærmere enn 8 meter fra RiksVeg eller KommunalVeg flyttes tilsvarende bort fra vegen

Avstanden fra veg til Bygningsgruppe er 20 meter (langs avkjørsel-retning).
Avstanden fra Bygningsgruppe til neste Bygningsgruppe styres indirekte av avstand mellom private avkjørsler: [70, 120] meter.
Avstanden fra Bygningsgruppe til nærmeste veg-ende styres indirekte av MinLengdeFraKryss=50 meter.
Generer Bygningsgruppe langs en side av alle Kommunale veger


## 5. AR5 (heldekkende)
Målet er å generere objekttypen Arealressursflate
- Generer heldekkende AR5-klasser: `Fulldyrka jord`, `Barskog`, `Bebygd`, `Samferdsel`, `Myr`, `Ferskvann`.
- Bruk fast prioritet i overlapping:
  1. `Samferdsel`
  2. `Bebygd`
  3. `Ferskvann`
  4. `Myr`
  5. `Fulldyrka jord`
  6. `Barskog` (restareal)
AR5 er et heldekkende arealressursdatasett som beskriver alt areal. 

Ønsker å lage et geopackage for AR5.
Denne skal genereres sist av alle kartlag.
I AR5 vil jeg ha generert følgende arealtype-klassene (AR-flater):
-Fulldyrka jord
-Barskog
-Bebygd
-Samferdsel
-Myr
-Ferskvann

Alle Arealressursflater er lukket polygon.

### Myr: 
Hent alle Vann-myrgrense-polygoner til AR5-Myr 

### Ferskvann: 
Hant alle Vann-Innsjøkant polygoner til AR5-Ferskvann 

### Samferdsel: 
Lag buffer rundt alle senterlinje-veg med vegbredden fra parametrene. Disse flatene lagres som Samferdsel i AR5. 
Alle arealer for veger slås sammen til Samferdsel.
Om det er andre AR-Flater som overlappes med Samferdsel, skal Samferdsel bli, og de andre AR5-flatene klippes bort.

### Bebygd: 
Rundt alle bygg lages buffer på 100m. 
Slå bufferene sammen. 
Nærliggende Bebygd-flater slås sammen.
Dersom Bebygd overlapper med Samferdsel, reduseres Bebygd tilsvarende.
Dersom Bebygd overlapper med Myr, reduseres Myr tilsvarende.
Dersom Bebygd overlapper med Ferskvann, fjernes hele Ferskvann-flaten.

### Fulldyrka jord:
Av det gjenværende arealet, finn noen relativt flate områder > 20.000m2. Disse lagres i AR5 som FulldyrkaJord

### Barskog: 
Resten av arealene er lagres som Barskog

Like AF-flater som ligger inntil hverandre slås sammen.
Kontroll: Ingen overlappende AR-flater. 
Kontroll: Hele området dekkes av AR-flater

Noen AR-flater er hentet og modifiserte. Oppdater disse i andre kartbaser:
Dersom ulik polygon Vann-myrgrense og AR5-Myr, erstattes Vann-myrgrense av AR5-Myr
Dersom ulik polygon Vann-Innsjøkant og AR5-Ferskvann, erstattes Vann-Innsjøkant av AR5-Ferskvann

Til slutt litt kosmetikk i hovedskriptet:
Slett høydekurver som er innenfor Innsjøkant.

## Datastruktur og output

Programmet skal skrive disse filene:

- `synthetic_terrain.gpkg` med lagene `terrain_points`, `terrain_tin`, `hoydekurver_1m`
- `synthetic_vann.gpkg` med lagene `innsjokant`, `elvbekk`, `myrgrense`
- `synthetic_vegnett.gpkg` med lagene `vegnett_riksveg`, `vegkant`
- `synthetic_bygning.gpkg` med laget `bygninger`
- `synthetic_ar5.gpkg` med laget `ar5_areal`

## Kjøring og CLI

`synthetic_map.py` skal støtte:

- Standard: kjør alt
- `--layers terrain|water|roads|buildings|ar5|all`
- Automatisk oppløsning av avhengigheter:
  - `water` krever `terrain`
  - `roads` krever `terrain`
  - `buildings` krever `terrain` + `roads`
  - `ar5` krever alle foregående

## Kvalitetskrav

- Geometrier skal være gyldige (bruk reparasjon ved behov, f.eks. `buffer(0)` der det er forsvarlig).
- Resultatet skal være robust for flere kjøringer med ulike tilfeldige utfall.
- Programmet skal skrive kort statistikk per lag etter generering.
- Kode skal være modulær, lesbar og dokumentert med korte docstrings.
- Ingen legacy-skript eller duplisert kjernelogikk.

## Konfigurasjon

Samle sentrale parametre i `synthetic_map.py`:

- BBOX, CRS
- `TERRAIN_CONFIG`
- `WATER_CONFIG`
- `ROAD_CONFIG`
- `ROAD_EDGE_CONFIG`
- `AR5_CONFIG`

Parametre skal være enkle å justere uten å endre algoritmekode.

## Instruksjoner
Commit-kommentarer er på norsk.
All ny kode, alle kommentarer og all dokumentasjon skal være på norsk.

Se også [.github/copilot-instructions.md](.github/copilot-instructions.md) for utfyllende regler om arkitektur, konfigurasjon, geometrikvalitet og git-rutiner.


## Validering før levering

1. Kjør full pipeline: `python synthetic_map.py`
2. Verifiser at alle fem GeoPackage-filer opprettes.
3. Verifiser at AR5-arealdekning matcher BBOX-areal innen liten toleranse.
4. Verifiser at det ikke finnes uønskede midlertidige filer i git.
5. Oppdater README med arkitektur, bruk, output og konfigurasjon.

## Leveranseformat

Lever en ryddig repository-struktur med:

- kildekode i modulene over
- oppdatert README
- `requirements.txt`
- `.gitignore` som ignorerer miljø- og låsefiler

# 💡 Ideer til neste versjon
Kysten er preget av en firkant.
Forslag til løsning: Når linjen deles i to, og midtpunktet forskyves fra linjen med en tilfeldig verdi, bør denne verdien være større. Er du enig?

Ser at det er litt få tettsteder ved kysten. Nå som dette er en øy hver gang. Foreslå e

Det ser ut som at det er riksveger som tar tettstedene i en sekvens. Foreslå en algoritme som skaper noen flere riksveger mellom tettstedene



