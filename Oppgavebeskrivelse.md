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
Det skal være tettsteder ved kysten med tilfeldig avstand mellom 2km og 6km. Tettsteder ved kysten har høyde=15m
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
 - hvis buesegmentet: sirkelbue som er tangent til forrige retning. Radiusens fortegn bestemmes av om vegen må dreie mot høyre eller venstre for å nærme seg målretningen/endepunktet. 
 - hvis rett-segment: Sjekk om antall påfølgende rettstrekk er overskredet, da velges buesegment
 - Fra et segment til et annet skal det være tangentkontinuitet.
 - Når vegen er nær nok endepunktet(<3*segmentlengden), legges siste del inn som bue mot avslutning mot målet. Buen beregnes slik at den er tangent-kontinuerlig, og avsluttes i endepunkt.
 Til slutt valideres kandidatlinjen. Hvis linjen krysser seg selv, eller er nærmere en annen veg enn 15m, forkastes den og algoritmen prøver på nytt opptil et gitt antall forsøk.

### N50-Terrengpunkt (3D-Punkt)
Tettsteder ligger i daler. Nå skal det genereres punkter for fjell.
Dette skjer gjennom flere itterasjoner:
#### Nivå1: Finn lavtliggende punkter (nivåets-punkt-tetthet=tettsted_avstand_min)
- Plukk ut terrengpunkter som senere skal brukes til å generere TIN:
- Bruk parametre for avstand mellom Tettsteder, som er et intervall. Bruk parameter for nederste grense av intervallet som nivåets-punkt-tetthet. 
- Langs Kystlinje plukk ut punkt slik at avstanden mellom punktene er oppunder nivåets-punkt-tetthet.
- Langs veg plukk ut punkt ikke nærmere hverandre enn nivåets-punkt-tetthet.
- Alle Tettstedene er med i utvalget av terrengpunkter
- Lagre alle terrengpunktene i Nivå1, med høyde.
Bygg TIN
#### Nivå2: Definer noen få fjellkjerner
- I hver TIN-trekant generer ett terrengpunkt i miten av TIN-trekanten. 
- Terrengpunkt-høyden = (TIN-interpolerte høyden for midtpunktet) + Tilfeldig tall i intervallet [100, 400]
- Terrengpunkt for fjellkjerner må ligge >1000 meter fra både nærmeste tettsted og nærmeste senterlinjeveg.
Bygg TIN
#### Nivå3: Definer flate områder rundt Tettsteder
Generer 6 punkter 500m fra tettstedsenter i tilfeldig retning fra tettstedsenter.
Disse punkter har Høyde = tettstedhøyde +/- tilfeldig tall i intervallet [1, 10].
Bygg TIN 
### Nivå4: Fortetting - jevnere størrelse på trekanter
- Bruk samme nivåets-punkt-tetthet som Nivå0
- For alle trekanter som har to lengste sider med sidelengde>nivåets-punkt-tetthet, og korteste sidelengde>nivåets-punkt-tetthet/4, lages et Terrengpunkt for fortetting i trekantens midtpunkt.
- Høyden på nye punkt er TIN-interpolert høyde for x,y + tilfeldig verdi for hvert punkt: [-10 , 30.0]
- Bygg TIN4 basert på alle terrengpunktene, lagre TIN4 til N50
### Nivå5: Fortetting (nivåets-punkt-tetthet=tettsted_avstand_min/4)
- Generer terrengpunkter langs veg hver 200 meter (bruk lineær høyde mellom start og slutt på vegsegmentet).
- Generer terrengpunkter langs kyst hver 200 meter (høyde=0).
- For hver trekant genereres nye punkter inne i trekanten. Punktenes plassering i TIN-trekanten er tilfeldig, men ingen punkter skal være nærmere hverandre enn nivåets-punkt-tetthet.
  - nivåets-punkt-tetthet=tettsted_avstand_min/4. 
  - MaksAntallPunktPrTrekant = 5.
Høyden på nye punkt er TIN-interpolert høyde for x,y + tilfeldig verdi for hvert punkt:
dersom punktet er nærmere veg enn 100m,      brukes intervallet [-2.0 , 2.0],
dersom punktet er nærmere tettsted enn 500m, brukes intervallet [-2.0 , 2.0], 
dersom punktet er nærmere kyst enn 100m,     brukes intervallet [0.0 , 2.0], 
ellers                                       brukes intervallet [-10 , 30.0]
Bygg TIN

### N50-Hoydekurve (2D-kurve)
Lagre TIN i N50.
Generer Hoydekurver med ekvidistande=20m basert på TIN.
Slett høydekurver som har kortere lengde enn 250 m
Glatt høydekurvene.

### N50-TrigonometriskPunkt
Terrengpunkt av typen "fjellkjede" kopieres med høyden til et eget lag: N50-TrigonometriskPunkt (3D-punkt)

--------------------------
## TODO CHAT
--------------------------
Ikke lag fortettingspunkter som er nermere et annet  fortettingspunkt enn 20m

Lag noen forsenklinger på 30m i terrenget.?

I Nivå 4 settes høyden på nye punkt er TIN-interpolert høyde for x,y + tilfeldig verdi for hvert punkt: [-10 , 30.0]. Gjør om dette til[-30 , 30.0], som kan medføre noen lavere områder


## Arealdekke
N50 har heldekkende Arealdekke som beskriver alt areal. 
Arealdekke består av disse objekttypene
- Kystkontur
- Tettbebyggelse
- Innsjøkant
- Myr
- DyrketMark
- Skog

### N50-Tettbebyggelse
Lag et polygon rundt tettsted-punktene. I steden for en sirkel med radius=500m, la den avvike fra sirkelen som en amøbefigur. 

Tettbebyggelse-agoritme:
Fra senter generer punkt i 8 retninger, alle med avstand fra senter lik bebyggelses-radius +- tilfeldig avvik på 30%.
Lag et polygon baset på disse 8 punktene. 
Fortett dette polygonet slik at det blir et glatt polygon.
Punktavstand i polygonen trenger ikke fortettes tettere enn punktavstand 100m.

Når Tettbebyggelse genereres kan bebyggelses-radius settes lik et tilfeldig tall i intervallet [400, 1000], slik at de ulike Tettbebyggelse blir litt ulikt store

Lagre som N50-Tettbebyggelse.

### N50-Innsjøkant
Områder som er en grop, eller "lukket" lavpunkt, er kandidat for innsjø.
Objekttypen Innsjøkant er et lukket polygon.
Bruk TIN til å finne groper. Når gropfunnet lag høydekurve med en passende høyde som Innsjøkant.
Høydekurver inni Innsjøkant kan slettes.
Innsjøer som er større enn 300 m² og bredere enn 15 meter, tas med.

### N50-Myr
Noen av de aller flateste områdene defineres som myr
Noen ganger kommer to myr-flater rett ved siden av hverandre. Slå disse sammen til en flate.
Myr som er større enn 2000m2 og bredere enn 30 m, tas med

### N50-DyrketMark
Av det gjenværende arealet, finn noen relativt flate områder > 2000m2. Disse lagres som N50-DyrketMark

Det skel ikke være overlapp mellom Arealbruk. Dersom det er overlapp mellom Myr, Innsjø, Bebyggelse, skal Innsjø gå foran Bebyggelse, som går foran Myr

### N50-Skog
Resten av arealene er lagres som Barskog

## N50-VegSenterlinjeR (3D-linje)
Beskrivelse for N50-VegSenterlinje er for Riksveger. Korriger både her og i koden slik at det heter N50-VegSenterlinjeR

## N50-VegSenterlinjeK (3D-linje)
Rund tettstedene skal Kommunale veger genereres.


--------------------------
**HIT HAR JEG KOMMET**
--------------------------









Linker:

N50: Produktspesifikasjon for N50 Kartdata
https://register.geonorge.no/data/documents/Produktspesifikasjoner_N50%20Kartdata_v15_produktspesifikasjon-kartverket-n50kartdata-versjon20170401_.pdf

N50: Produktspesifikasjon for N50 Raster
https://register.geonorge.no/data/documents/produktspesifikasjoner_N50%20Raster_v1_produktspesifikasjon-kv-n50-raster-versjon20150401_.pdf

FKB Registreringsinstrukser
https://register.geonorge.no/nasjonale-standarder-og-veiledere/kartleggingsinstrukser

Kartografi
https://register.geonorge.no/data/documents/N50%20Kartdata._Spesifikasjon%20Skjermkartografi%2020091102.pdf


