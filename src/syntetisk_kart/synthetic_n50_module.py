# Legg til etter alle imports og type hints
# Legg til etter alle imports og type hints
import geopandas as gpd

"""Generering av syntetiske N50-objekter."""

import math
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, MultiLineString, MultiPoint, Point, Polygon, box
from shapely.ops import linemerge, triangulate, unary_union

Punkt = Tuple[float, float]
SIDE_REKKEFOLGE = ["vest", "nord", "ost", "sor"]

def generer_stedsnavntekst(
    kystkontur: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Generer N50-stedsnavntekst som 3D-punkter for tettsteder."""
    tilfeldig = np.random.default_rng()
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landgeometri = bbox_polygon.difference(havflate.geometry.iloc[0])
    kystlinje = kystkontur.geometry.iloc[0]
    antall_tettsteder = _beregn_antall_tettsteder(konfig, bbox_polygon.area)
    antall_kysttettsteder = max(1, min(antall_tettsteder - 1, int(round(antall_tettsteder * float(konfig["tettsted_kystandel"])))) )
    antall_innlandstettsteder = max(1, antall_tettsteder - antall_kysttettsteder)
    navn_liste = list(konfig["tettsted_navn"])

    tettsteder: List[dict] = []
    eksisterende_punkter: List[Point] = []

    for indeks in range(antall_kysttettsteder):
        punkt = _finn_kystnaert_tettstedspunkt(kystlinje, landgeometri, konfig, tilfeldig, eksisterende_punkter)
        hoyde = float(konfig["tettsted_kyst_hoyde"])
        geometri = Point(punkt.x, punkt.y, hoyde)
        eksisterende_punkter.append(Point(punkt.x, punkt.y))
        tettsteder.append(
            {
                "navn": navn_liste[indeks % len(navn_liste)],
                "navneobjekttype": "By",
                "stedstype": "kyst",
                "hoyde": hoyde,
                "geometry": geometri,
            }
        )

    for indeks in range(antall_innlandstettsteder):
        punkt = _finn_innlandstettstedspunkt(
            kystlinje,
            landgeometri,
            konfig,
            tilfeldig,
            eksisterende_punkter,
            indeks,
            antall_innlandstettsteder,
        )
        avstand_til_kyst = punkt.distance(kystlinje)
        hoyde = float(avstand_til_kyst / float(konfig["tettsted_hoyde_divisor"]))
        geometri = Point(punkt.x, punkt.y, hoyde)
        eksisterende_punkter.append(Point(punkt.x, punkt.y))
        navn_indeks = antall_kysttettsteder + indeks
        tettsteder.append(
            {
                "navn": navn_liste[navn_indeks % len(navn_liste)],
                "navneobjekttype": "By",
                "stedstype": "innland",
                "hoyde": hoyde,
                "geometry": geometri,
            }
        )

    print(f"Stedsnavn generert: {[t['navn'] for t in tettsteder]}")
    return gpd.GeoDataFrame(tettsteder, geometry="geometry", crs=konfig["crs"])


def generer_kystkontur(konfig: Dict[str, object]) -> gpd.GeoDataFrame:
    """Generer én sammenhengende N50-kystkontur innenfor angitt bbox."""
    print("Starter generering av kystkontur...")
    bbox_verdier = tuple(konfig["bbox"])
    bbox_polygon = box(*bbox_verdier)
    tilfeldig = np.random.default_rng()
    valgte_sider = _velg_sammenhengende_sider(konfig, tilfeldig)
    maks_forsok = 10
    for forsok in range(1, maks_forsok + 1):
        try:
            kystlinje = _lag_sammenhengende_kystlinje(bbox_polygon, valgte_sider, konfig, tilfeldig)
            break
        except ValueError as e:
            print(f"Kystlinje-generering feilet i forsøk {forsok}: {e}")
            if forsok == maks_forsok:
                raise
    else:
        raise ValueError("Klarte ikke å generere en gyldig sammenhengende kystlinje etter flere forsøk.")

    print(f"Kystkontur generert med {len(kystlinje.coords)} punkter og sider: {valgte_sider}")
    return gpd.GeoDataFrame(
        [{"sider": ",".join(valgte_sider), "geometry": kystlinje}],
        geometry="geometry",
        crs=konfig["crs"],
    )


def generer_havflate(kystkontur: gpd.GeoDataFrame, konfig: Dict[str, object]) -> gpd.GeoDataFrame:
    """Generer en lukket havflate basert på kystkonturen."""
    bbox_polygon = box(*tuple(konfig["bbox"]))
    kystlinje = kystkontur.geometry.iloc[0]
    valgte_sider = str(kystkontur.iloc[0]["sider"]).split(",")

    if len(valgte_sider) == len(SIDE_REKKEFOLGE) and kystlinje.is_ring:
        landflate = Polygon(kystlinje.coords)
        havgeometri = bbox_polygon.difference(landflate)
    else:
        havgeometri = _lag_havpolygon_fra_kystlinje(kystlinje, valgte_sider, bbox_polygon.bounds)

    if not havgeometri.is_valid:
        havgeometri = havgeometri.buffer(0)

    return gpd.GeoDataFrame(
        [{"objekttype": "N50-Havflate", "geometry": havgeometri}],
        geometry="geometry",
        crs=konfig["crs"],
    )



def generer_vegsenterlinje(
    stedsnavntekst: gpd.GeoDataFrame,
    kystkontur: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Generer N50-vegsenterlinjer som 3D-linjer mellom tettsteder."""
    tilfeldig = np.random.default_rng()
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landgeometri = bbox_polygon.difference(havflate.geometry.iloc[0]).buffer(0)
    kystlinje = kystkontur.geometry.iloc[0]

    tettsteder = [
        {
            "navn": rad["navn"],
            "punkt": Point(rad.geometry.x, rad.geometry.y),
            "hoyde": float(rad["hoyde"]),
        }
        for _, rad in stedsnavntekst.iterrows()
    ]

    forbindelser = _bygg_vegforbindelser(tettsteder, landgeometri, kystlinje, konfig)
    eksisterende_veger: List[LineString] = []
    vegobjekter: List[dict] = []

    print("Starter generer_vegsenterlinje: lager tettsteder-liste")
    for fra_indeks, til_indeks in forbindelser:
        fra_tettsted = tettsteder[fra_indeks]
        til_tettsted = tettsteder[til_indeks]
        print(f"Bygger veg fra {fra_tettsted['navn']} til {til_tettsted['navn']}")
        try:
            veg2d = _lag_veglinje_mellom_tettsteder(
                startpunkt=fra_tettsted["punkt"],
                sluttpunkt=til_tettsted["punkt"],
                landgeometri=landgeometri,
                kystlinje=kystlinje,
                eksisterende_veger=eksisterende_veger,
                konfig=konfig,
                tilfeldig=tilfeldig,
            )
        except ValueError:
            print(f"Feil under bygging av veg fra {fra_tettsted['navn']} til {til_tettsted['navn']}")
            continue

        veg3d = _lag_3d_veglinje(
            veg2d=veg2d,
            starthoyde=fra_tettsted["hoyde"],
            slutthoyde=til_tettsted["hoyde"],
            konfig=konfig,
            tilfeldig=tilfeldig,
        )
        eksisterende_veger.append(veg2d)
        vegobjekter.append(
            {
                "vegtype": str(konfig["vegtype"]),
                "fra_navn": fra_tettsted["navn"],
                "til_navn": til_tettsted["navn"],
                "geometry": veg3d,
            }
        )
    print("Ferdig hovedløkke for veger")

    if not vegobjekter and len(tettsteder) >= 2:
        for fra_indeks in range(len(tettsteder) - 1):
            for til_indeks in range(fra_indeks + 1, len(tettsteder)):
                direkte = LineString(
                    [
                        (tettsteder[fra_indeks]["punkt"].x, tettsteder[fra_indeks]["punkt"].y),
                        (tettsteder[til_indeks]["punkt"].x, tettsteder[til_indeks]["punkt"].y),
                    ]
                )
                if _er_gyldig_veglinje(direkte, landgeometri, kystlinje, [], konfig):
                    vegobjekter.append(
                        {
                            "vegtype": str(konfig["vegtype"]),
                            "fra_navn": tettsteder[fra_indeks]["navn"],
                            "til_navn": tettsteder[til_indeks]["navn"],
                            "geometry": _lag_3d_veglinje(
                                veg2d=direkte,
                                starthoyde=tettsteder[fra_indeks]["hoyde"],
                                slutthoyde=tettsteder[til_indeks]["hoyde"],
                                konfig=konfig,
                                tilfeldig=tilfeldig,
                            ),
                        }
                    )
                    break
            if vegobjekter:
                break

    return gpd.GeoDataFrame(vegobjekter, geometry="geometry", crs=konfig["crs"])


def generer_terrengpunkt(
    kystkontur: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    stedsnavntekst: gpd.GeoDataFrame,
    vegsenterlinje: gpd.GeoDataFrame,
    konfig: Dict[str, object],
    ) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Generer N50-terrengpunkt som 3D-punkter over landarealet."""
    tilfeldig = np.random.default_rng()
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landgeometri = bbox_polygon.difference(havflate.geometry.iloc[0]).buffer(0)
    kystlinje = kystkontur.geometry.iloc[0]
    punktavstand = float(konfig["terreng_niva1_punktavstand"])
    minste_avstand = float(konfig["terreng_min_punktavstand"])

    # Nivå 5: Bruk fast avstand 200m for punkter langs veg og kyst
    punktavstand_n5 = 200.0

    tettsteder = [
        {
            "navn": rad["navn"],
            "punkt": Point(rad.geometry.x, rad.geometry.y),
            "hoyde": float(rad["hoyde"]),
        }
        for _, rad in stedsnavntekst.iterrows()
    ]
    fjellkjerner = _lag_fjellkjerner(landgeometri, kystlinje, tettsteder, vegsenterlinje, konfig, tilfeldig)
    trig_punkt_liste = []

    terrengpunktdata: List[dict] = []
    brukte_punkter: List[Point] = []
    total_teller = 0
    type_teller = {"tettsted": 0, "kyst": 0, "veg": 0, "fjellkjerne": 0, "flate": 0, "fortetting": 0}

    print("Starter generering av terrengpunkter: tettsted")
    for tettsted in tettsteder:
        _legg_til_terrengpunkt(
            terrengpunktdata,
            brukte_punkter,
            tettsted["punkt"],
            tettsted["hoyde"],
            "tettsted",
            0.0,
        )
        type_teller["tettsted"] += 1
        total_teller += 1
    print("Ferdig tettsted, starter kyst")

    # Kystpunkter: bruk alltid høyde = 0 (havnivå)

    # Nivå 5: punkter langs kyst hver 200m, høyde=0
    for kystpunkt in _lag_linjeprover(kystlinje, punktavstand_n5):
        _legg_til_terrengpunkt(
            terrengpunktdata,
            brukte_punkter,
            kystpunkt,
            0.0,
            "kyst",
            minste_avstand,
        )
        type_teller["kyst"] += 1
        total_teller += 1
    print("Ferdig kyst, starter veg")

    # Vegpunkter: bruk Z-verdi fra vegpunktet (alle punkter på vegsenterlinje skal ha Z)
    # Nivå 5: punkter langs veg hver 200m, bruk lineær høyde mellom start og slutt
    veg_punktavstand_n5 = 200.0
    for veggeometri in vegsenterlinje.geometry:
        for vegpunkt in _lag_linjeprover(veggeometri, veg_punktavstand_n5):
            # Sikre at vegpunkt har Z-verdi, ellers bruk terrengmodell
            if hasattr(vegpunkt, "z"):
                hoyde = float(vegpunkt.z)
            else:
                hoyde = _beregn_terrenghoyde(
                    vegpunkt,
                    kystlinje,
                    tettsteder,
                    fjellkjerner,
                    konfig,
                )
            _legg_til_terrengpunkt(
                terrengpunktdata,
                brukte_punkter,
                vegpunkt,
                hoyde,
                "veg",
                minste_avstand,
            )
            type_teller["veg"] += 1
            total_teller += 1
    print("Ferdig veg, starter fjellkjerne")

    for kjerne in fjellkjerner:
        hoyde = _beregn_terrenghoyde(kjerne["punkt"], kystlinje, tettsteder, fjellkjerner, konfig)
        _legg_til_terrengpunkt(
            terrengpunktdata,
            brukte_punkter,
            kjerne["punkt"],
            hoyde,
            "fjellkjerne",
            minste_avstand,
        )
        trig_punkt_liste.append({
            "hoyde": hoyde,
            "geometry": Point(kjerne["punkt"].x, kjerne["punkt"].y, hoyde),
        })
        type_teller["fjellkjerne"] += 1
        total_teller += 1
    print("Ferdig fjellkjerne, starter flate")


    # Nivå 3: Flatepunkter rundt tettstedene
    radius = 1300.0  # meters, doblet fra 650.0
    for tettsted in tettsteder:
        for _ in range(6):
            vinkel = float(tilfeldig.uniform(0.0, math.tau))
            punkt = Point(
                tettsted["punkt"].x + math.cos(vinkel) * radius,
                tettsted["punkt"].y + math.sin(vinkel) * radius,
            )
            if not landgeometri.covers(punkt):
                continue
            hoyde = float(tettsted["hoyde"] + tilfeldig.uniform(-10.0, 10.0))
            _legg_til_terrengpunkt(
                terrengpunktdata,
                brukte_punkter,
                punkt,
                hoyde,
                "flate",
                min(minste_avstand, radius * 0.2),
            )
            type_teller["flate"] += 1
            total_teller += 1


    print("Ferdig flate, starter fortetting nivå 4")
    # Nivå 4: Fortetting - jevnere størrelse på trekanter
    punkt_tetthet = float(konfig["tettsted_avstand_min"])
    tin_trekanter = _bygg_tin_objekter_fra_punktdata(terrengpunktdata, landgeometri)
    fortettingspunkter = []
    tilfeldig = np.random.default_rng()
    for trekant in tin_trekanter:
        koordinater = trekant["koordinater"]
        hoyder = trekant["hoyder"]
        a = math.dist(koordinater[0], koordinater[1])
        b = math.dist(koordinater[1], koordinater[2])
        c = math.dist(koordinater[2], koordinater[0])
        sidelengder = sorted([a, b, c])
        if sidelengder[1] > punkt_tetthet and sidelengder[2] > punkt_tetthet and sidelengder[0] > punkt_tetthet / 4.0:
            mx = sum([p[0] for p in koordinater]) / 3.0
            my = sum([p[1] for p in koordinater]) / 3.0
            midtpunkt = Point(mx, my)
            if not landgeometri.covers(midtpunkt):
                continue
            interpolert_hoyde = _interpoler_hoyde_i_trekant((mx, my), koordinater, hoyder)
            hoyde = interpolert_hoyde + tilfeldig.uniform(-20.0, 30.0)
            fortettingspunkter.append({
                "kilde": "fortetting",
                "x": mx,
                "y": my,
                "hoyde": float(max(0.0, hoyde)),
                "geometry": Point(mx, my, float(max(0.0, hoyde))),
            })
            type_teller["fortetting"] += 1
            total_teller += 1
    terrengpunktdata.extend(fortettingspunkter)
    print(f"Ferdig fortetting nivå 4, antall fortettingspunkter nivå 4: {len(fortettingspunkter)}")

    print("Starter fortetting nivå 5 (langs kyst og veg)")
    # Nivå 5: Fortetting (tettsted_avstand_min/4)
    punkt_tetthet_n5 = float(konfig["tettsted_avstand_min"]) / 4.0
    # Fortett langs kyst
    kystpunkter = [p for p in terrengpunktdata if p["kilde"] == "kyst"]
    nye_kystpunkter = []
    for i in range(len(kystpunkter) - 1):
        p1 = kystpunkter[i]
        p2 = kystpunkter[i + 1]
        for j in range(1, 4):
            t = j / 4.0
            x = p1["x"] * (1 - t) + p2["x"] * t
            y = p1["y"] * (1 - t) + p2["y"] * t
            if not landgeometri.covers(Point(x, y)):
                continue
            hoyde = _interpoler_hoyde_i_trekant((x, y), [ (p1["x"], p1["y"]), (p2["x"], p2["y"]), (x, y) ], [p1["hoyde"], p2["hoyde"], (p1["hoyde"] + p2["hoyde"]) / 2])
            hoyde += tilfeldig.uniform(0.0, 2.0)
            nye_kystpunkter.append({
                "kilde": "fortetting",
                "x": x,
                "y": y,
                "hoyde": float(max(0.0, hoyde)),
                "geometry": Point(x, y, float(max(0.0, hoyde))),
            })
            type_teller["fortetting"] += 1
            total_teller += 1
    terrengpunktdata.extend(nye_kystpunkter)
    print(f"Ferdig fortetting nivå 5 kyst, antall nye kystpunkter: {len(nye_kystpunkter)}")

    # Fortett langs veg
    vegpunkter = [p for p in terrengpunktdata if p["kilde"] == "veg"]
    nye_vegpunkter = []
    for i in range(len(vegpunkter) - 1):
        p1 = vegpunkter[i]
        p2 = vegpunkter[i + 1]
        for j in range(1, 4):
            t = j / 4.0
            x = p1["x"] * (1 - t) + p2["x"] * t
            y = p1["y"] * (1 - t) + p2["y"] * t
            if not landgeometri.covers(Point(x, y)):
                continue
            hoyde = _interpoler_hoyde_i_trekant((x, y), [ (p1["x"], p1["y"]), (p2["x"], p2["y"]), (x, y) ], [p1["hoyde"], p2["hoyde"], (p1["hoyde"] + p2["hoyde"]) / 2])
            hoyde += tilfeldig.uniform(-2.0, 2.0)
            nye_vegpunkter.append({
                "kilde": "fortetting",
                "x": x,
                "y": y,
                "hoyde": float(max(0.0, hoyde)),
                "geometry": Point(x, y, float(max(0.0, hoyde))),
            })
            type_teller["fortetting"] += 1
            total_teller += 1
    terrengpunktdata.extend(nye_vegpunkter)
    print(f"Ferdig fortetting nivå 5 veg, antall nye vegpunkter: {len(nye_vegpunkter)}")

    # Fortetting i trekanter (maks 5 pr trekant, avstandskrav)
    tin_trekanter_n5 = _bygg_tin_objekter_fra_punktdata(terrengpunktdata, landgeometri)

    from shapely.strtree import STRtree

    brukte_punkter = [Point(float(p["x"]), float(p["y"])) for p in terrengpunktdata]
    print("Starter fortetting nivå 5 i trekanter (med STRtree)")
    tree = STRtree(brukte_punkter)
    for trekant in tin_trekanter_n5:
        generert = 0
        forsok = 0
        maks_forsok = 50
        while generert < 5 and forsok < maks_forsok:
            kandidat = _tilfeldig_punkt_i_trekant(trekant["koordinater"], tilfeldig)
            forsok += 1
            if not landgeometri.covers(kandidat):
                continue
            # Bruk STRtree for nærhetssjekk
            nære = tree.query(kandidat.buffer(punkt_tetthet_n5))
            if any(isinstance(n, Point) and kandidat.distance(n) < punkt_tetthet_n5 for n in nære):
                continue
            interpolert_hoyde = _interpoler_hoyde_i_trekant((kandidat.x, kandidat.y), trekant["koordinater"], trekant["hoyder"])
            # Høydeavvik etter nærhet
            min_vegavstand = min([kandidat.distance(Point(p["x"], p["y"])) for p in vegpunkter], default=99999)
            min_tettstedavstand = min([kandidat.distance(Point(p["x"], p["y"])) for p in terrengpunktdata if p["kilde"] == "tettsted"], default=99999)
            min_kystavstand = min([kandidat.distance(Point(p["x"], p["y"])) for p in kystpunkter], default=99999)
            if min_vegavstand < 100:
                avvik = tilfeldig.uniform(-2.0, 2.0)
            elif min_tettstedavstand < 500:
                avvik = tilfeldig.uniform(-2.0, 2.0)
            elif min_kystavstand < 100:
                avvik = tilfeldig.uniform(0.0, 2.0)
            else:
                avvik = tilfeldig.uniform(-10.0, 30.0)
            hoyde = interpolert_hoyde + avvik
            terrengpunktdata.append({
                "kilde": "fortetting",
                "x": float(kandidat.x),
                "y": float(kandidat.y),
                "hoyde": float(max(0.0, hoyde)),
                "geometry": Point(float(kandidat.x), float(kandidat.y), float(max(0.0, hoyde))),
            })
            ny_punkt = Point(float(kandidat.x), float(kandidat.y))
            brukte_punkter.append(ny_punkt)
            # Oppdater STRtree for neste punkt
            tree = STRtree(brukte_punkter)
            type_teller["fortetting"] += 1
            total_teller += 1
            generert += 1
        if generert < 5:
            print(f"Advarsel: Kun {generert} punkter generert i trekant pga. avstandskrav.")

    print("Ferdig fortetting nivå 5 i trekanter")
    print("Antall terrengpunkter per type:")
    for t, antall in type_teller.items():
        print(f"  {t}: {antall}")

    # Returner alle genererte terrengpunkter og trigonometriske punkt
    terreng_gdf = gpd.GeoDataFrame(terrengpunktdata, geometry="geometry", crs=konfig["crs"])
    if trig_punkt_liste:
        trig_gdf = gpd.GeoDataFrame(trig_punkt_liste, geometry="geometry", crs=konfig["crs"])
    else:
        trig_gdf = gpd.GeoDataFrame(columns=["hoyde", "geometry"], geometry="geometry", crs=konfig["crs"])
    return terreng_gdf, trig_gdf


def generer_tin(
    terrengpunkt: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Bygg TIN-triangelpolygoner fra terrengpunktene."""
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landgeometri = bbox_polygon.difference(havflate.geometry.iloc[0]).buffer(0)
    punktdata = _terrengdata_fra_gdf(terrengpunkt)
    trekanter = _bygg_tin_objekter_fra_punktdata(punktdata, landgeometri)
    objekter = [
        {
            "trekant_id": indeks + 1,
            "min_hoyde": float(min(trekant["hoyder"])),
            "maks_hoyde": float(max(trekant["hoyder"])),
            "geometry": trekant["polygon"],
        }
        for indeks, trekant in enumerate(trekanter)
    ]
    return gpd.GeoDataFrame(objekter, geometry="geometry", crs=konfig["crs"])


def generer_hoydekurve(
    terrengpunkt: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Generer høydekurver med fast ekvidistanse basert på TIN."""
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landgeometri = bbox_polygon.difference(havflate.geometry.iloc[0]).buffer(0)
    punktdata = _terrengdata_fra_gdf(terrengpunkt)
    trekanter = _bygg_tin_objekter_fra_punktdata(punktdata, landgeometri)
    if not trekanter:
        return gpd.GeoDataFrame(columns=["hoyde", "geometry"], geometry="geometry", crs=konfig["crs"])

    ekvidistanse = float(konfig["hoydekurve_ekvidistanse"])
    minste_lengde = float(konfig["hoydekurve_min_lengde"])
    minimum_hoyde = min(float(punkt["hoyde"]) for punkt in punktdata)
    maksimum_hoyde = max(float(punkt["hoyde"]) for punkt in punktdata)
    startniva = math.ceil(minimum_hoyde / ekvidistanse) * ekvidistanse
    sluttniva = math.floor(maksimum_hoyde / ekvidistanse) * ekvidistanse

    segmenter_per_hoyde: Dict[float, List[LineString]] = {}
    for trekant in trekanter:
        laveste = min(trekant["hoyder"])
        hoyeste = max(trekant["hoyder"])
        nivaa = max(startniva, math.ceil(laveste / ekvidistanse) * ekvidistanse)
        siste = min(sluttniva, math.floor(hoyeste / ekvidistanse) * ekvidistanse)
        while nivaa <= siste + 1e-9:
            segment = _lag_hoydekurvesegment_for_trekant(trekant["koordinater"], trekant["hoyder"], nivaa)
            if segment is not None and segment.length > 0.0:
                segmenter_per_hoyde.setdefault(float(nivaa), []).append(segment)
            nivaa += ekvidistanse

    chaikin_iterasjoner = int(konfig.get("hoydekurve_chaikin_iterasjoner", 2))
    hoydekurver: List[dict] = []
    for hoyde, segmenter in segmenter_per_hoyde.items():
        sammenslatt = linemerge(unary_union(segmenter))
        for linje in _ekstraher_linjer_fra_geometri(sammenslatt):
            klippet = linje.intersection(landgeometri)
            for gyldig_linje in _ekstraher_linjer_fra_geometri(klippet):
                # Filtrer bort korte høydekurver før glatting
                if gyldig_linje.length < minste_lengde or not gyldig_linje.is_valid:
                    continue
                # Glatt linjen med Chaikin-algoritmen
                glatt_linje = _glatt_linje_chaikin(gyldig_linje, chaikin_iterasjoner)
                hoydekurver.append({"hoyde": float(hoyde), "geometry": glatt_linje})

    # Slett høydekurver som er kortere enn 250 meter
    hoydekurver = [obj for obj in hoydekurver if obj["geometry"].length >= 250.0]
    return gpd.GeoDataFrame(hoydekurver, geometry="geometry", crs=konfig["crs"])
# Chaikin-glatting av linje
def _glatt_linje_chaikin(linje: LineString, iterasjoner: int) -> LineString:
    """Glatt en LineString med Chaikin's corner cutting-algoritme."""
    coords = list(linje.coords)
    for _ in range(iterasjoner):
        nye_coords = []
        for i in range(len(coords) - 1):
            p0 = coords[i]
            p1 = coords[i + 1]
            q = (
                0.75 * p0[0] + 0.25 * p1[0],
                0.75 * p0[1] + 0.25 * p1[1],
            )
            r = (
                0.25 * p0[0] + 0.75 * p1[0],
                0.25 * p0[1] + 0.75 * p1[1],
            )
            nye_coords.extend([q, r])
        coords = [coords[0]] + nye_coords + [coords[-1]]
    return LineString(coords)


def _terrengdata_fra_gdf(terrengpunkt: gpd.GeoDataFrame) -> List[dict]:
    return [
        {
            "x": float(rad.geometry.x),
            "y": float(rad.geometry.y),
            "hoyde": float(rad["hoyde"]),
        }
        for _, rad in terrengpunkt.iterrows()
    ]


def _lag_fjellkjerner(
    landgeometri,
    kystlinje: LineString,
    tettsteder: List[dict],
    vegsenterlinje: gpd.GeoDataFrame,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> List[dict]:
    kjerner: List[dict] = []
    min_kystavstand = float(konfig["terreng_fjell_min_kystavstand"])
    min_tettstedavstand = float(konfig["terreng_fjell_min_tettstedavstand"])
    min_vegavstand = min_tettstedavstand  # Bruk samme som tettsted, evt. lag egen parameter

    for _ in range(int(konfig["terreng_fjellkjerner_antall"]) * 20):
        if len(kjerner) >= int(konfig["terreng_fjellkjerner_antall"]):
            break
        kandidat = _lag_tilfeldig_landpunkt(landgeometri, konfig, tilfeldig)
        if kandidat is None or kandidat.distance(kystlinje) < min_kystavstand:
            continue
        if any(kandidat.distance(tettsted["punkt"]) < min_tettstedavstand for tettsted in tettsteder):
            continue
        if any(kandidat.distance(kjerne["punkt"]) < min_tettstedavstand for kjerne in kjerner):
            continue
        # Sjekk avstand til alle vegsenterlinjer
        if any(kandidat.distance(veglinje) < min_vegavstand for veglinje in vegsenterlinje.geometry):
            continue

        kjerner.append(
            {
                "punkt": kandidat,
                "hoyde": float(
                    tilfeldig.uniform(
                        float(konfig["terreng_fjell_hoyde_min"]),
                        float(konfig["terreng_fjell_hoyde_maks"]),
                    )
                ),
                "spredning": float(
                    tilfeldig.uniform(
                        float(konfig["terreng_fjell_spredning_min"]),
                        float(konfig["terreng_fjell_spredning_maks"]),
                    )
                ),
            }
        )
    return kjerner


def _beregn_terrenghoyde(
    punkt: Point,
    kystlinje: LineString,
    tettsteder: List[dict],
    fjellkjerner: List[dict],
    konfig: Dict[str, object],
) -> float:

    hoyde = max(
        float(konfig["tettsted_kyst_hoyde"]),
        punkt.distance(kystlinje) / float(konfig["tettsted_hoyde_divisor"]),
    )

    for fjellkjerne in fjellkjerner:
        avstand = punkt.distance(fjellkjerne["punkt"])
        spredning = max(1.0, float(fjellkjerne["spredning"]))
        hoyde += float(fjellkjerne["hoyde"]) * math.exp(-(avstand * avstand) / (2.0 * spredning * spredning))

    # Begrens maksimal fjellhøyde
    fjell_hoyde_maks = float(konfig.get("terreng_fjell_hoyde_maks", 320.0))
    hoyde = min(hoyde, fjell_hoyde_maks)

    flat_radius = float(konfig["terreng_flate_radius"])
    for tettsted in tettsteder:
        avstand = punkt.distance(tettsted["punkt"])
        if avstand < flat_radius:
            andel = 1.0 - (avstand / flat_radius)
            hoyde = (hoyde * (1.0 - andel)) + (float(tettsted["hoyde"]) * andel)

    return max(0.0, hoyde)


def _legg_til_terrengpunkt(
    terrengpunktdata: List[dict],
    brukte_punkter: List[Point],
    punkt: Point,
    hoyde: float,
    kilde: str,
    minste_avstand: float,
) -> bool:
    punkt2d = Point(float(punkt.x), float(punkt.y))
    if minste_avstand > 0.0 and any(punkt2d.distance(brukt_punkt) < minste_avstand for brukt_punkt in brukte_punkter):
        return False

    # Sikre at alle punkter får 3D-geometri (Point(x, y, z))
    x = float(punkt.x)
    y = float(punkt.y)
    z = float(hoyde)
    punkt3d = Point(x, y, z)
    terrengpunktdata.append(
        {
            "kilde": kilde,
            "x": x,
            "y": y,
            "hoyde": z,
            "geometry": punkt3d,
        }
    )
    brukte_punkter.append(Point(x, y))
    return True


def _lag_linjeprover(linje: LineString, punktavstand: float) -> List[Point]:
    if linje.length == 0.0:
        return []
    avstander = list(np.arange(0.0, linje.length, max(punktavstand, 1.0)))
    avstander.append(linje.length)
    return [linje.interpolate(float(avstand)) for avstand in avstander]


def _lag_fortettingspunkter(
    punktdata: List[dict],
    landgeometri,
    kystlinje: LineString,
    tettsteder: List[dict],
    fjellkjerner: List[dict],
    konfig: Dict[str, object],
    antall_per_trekant: int,
    maks_avvik: float,
    flat_radius: float,
    minste_avstand: float,
    tilfeldig: np.random.Generator,
) -> List[dict]:
    trekanter = _bygg_tin_objekter_fra_punktdata(punktdata, landgeometri)
    brukte_punkter = [Point(float(punkt["x"]), float(punkt["y"])) for punkt in punktdata]
    nye_punkter: List[dict] = []

    for trekant in trekanter:
        for _ in range(antall_per_trekant):
            kandidat = _tilfeldig_punkt_i_trekant(trekant["koordinater"], tilfeldig)
            if not landgeometri.covers(kandidat):
                continue
            if any(kandidat.distance(brukt_punkt) < minste_avstand for brukt_punkt in brukte_punkter):
                continue

            interpolert_hoyde = _interpoler_hoyde_i_trekant(
                (float(kandidat.x), float(kandidat.y)),
                trekant["koordinater"],
                trekant["hoyder"],
            )
            modellhoyde = _beregn_terrenghoyde(kandidat, kystlinje, tettsteder, fjellkjerner, konfig)
            hoyde = (interpolert_hoyde + modellhoyde) / 2.0 + float(tilfeldig.uniform(-maks_avvik, maks_avvik))
            naermeste_tettsted = _finn_naermeste_tettsted(kandidat, tettsteder)
            if naermeste_tettsted is not None:
                avstand = kandidat.distance(naermeste_tettsted["punkt"])
                if avstand < flat_radius:
                    andel = 1.0 - (avstand / flat_radius)
                    hoyde = (hoyde * (1.0 - andel)) + (float(naermeste_tettsted["hoyde"]) * andel)

            nye_punkter.append(
                {
                    "kilde": "fortetting",
                    "x": float(kandidat.x),
                    "y": float(kandidat.y),
                    "hoyde": float(max(0.0, hoyde)),
                    "geometry": Point(float(kandidat.x), float(kandidat.y), float(max(0.0, hoyde))),
                }
            )
            brukte_punkter.append(Point(float(kandidat.x), float(kandidat.y)))
    return nye_punkter


def _finn_naermeste_tettsted(kandidat: Point, tettsteder: List[dict]) -> Optional[dict]:
    if not tettsteder:
        return None
    return min(tettsteder, key=lambda tettsted: kandidat.distance(tettsted["punkt"]))


def _bygg_tin_objekter_fra_punktdata(punktdata: List[dict], landgeometri) -> List[dict]:
    if len(punktdata) < 3:
        return []

    multipunkt = MultiPoint([Point(float(punkt["x"]), float(punkt["y"])) for punkt in punktdata])
    hoydeoppslag = {
        _koordinatnokkel((float(punkt["x"]), float(punkt["y"]))): float(punkt["hoyde"])
        for punkt in punktdata
    }
    trekanter: List[dict] = []

    for trekant in triangulate(multipunkt):
        if not landgeometri.covers(trekant.representative_point()):
            continue
        koordinater = [(float(x), float(y)) for x, y in list(trekant.exterior.coords)[:-1]]
        if len(koordinater) != 3:
            continue
        nøkler = [_koordinatnokkel(koordinat) for koordinat in koordinater]
        if not all(nokkel in hoydeoppslag for nokkel in nøkler):
            continue
        hoyder = [hoydeoppslag[nokkel] for nokkel in nøkler]
        trekanter.append({"polygon": trekant, "koordinater": koordinater, "hoyder": hoyder})

    return trekanter


def _koordinatnokkel(koordinat: Punkt) -> Tuple[float, float]:
    return (round(float(koordinat[0]), 6), round(float(koordinat[1]), 6))


def _tilfeldig_punkt_i_trekant(koordinater: List[Punkt], tilfeldig: np.random.Generator) -> Point:
    a, b, c = koordinater
    u = float(tilfeldig.random())
    v = float(tilfeldig.random())
    if u + v > 1.0:
        u = 1.0 - u
        v = 1.0 - v
    x = a[0] + (b[0] - a[0]) * u + (c[0] - a[0]) * v
    y = a[1] + (b[1] - a[1]) * u + (c[1] - a[1]) * v
    return Point(x, y)


def _interpoler_hoyde_i_trekant(punkt: Punkt, koordinater: List[Punkt], hoyder: List[float]) -> float:
    (x1, y1), (x2, y2), (x3, y3) = koordinater
    determinant = ((y2 - y3) * (x1 - x3)) + ((x3 - x2) * (y1 - y3))
    if abs(determinant) < 1e-9:
        return float(sum(hoyder) / len(hoyder))

    l1 = (((y2 - y3) * (punkt[0] - x3)) + ((x3 - x2) * (punkt[1] - y3))) / determinant
    l2 = (((y3 - y1) * (punkt[0] - x3)) + ((x1 - x3) * (punkt[1] - y3))) / determinant
    l3 = 1.0 - l1 - l2
    return float((hoyder[0] * l1) + (hoyder[1] * l2) + (hoyder[2] * l3))


def _lag_hoydekurvesegment_for_trekant(
    koordinater: List[Punkt],
    hoyder: List[float],
    nivaa: float,
) -> Optional[LineString]:
    krysspunkter: List[Punkt] = []
    for startindeks, sluttindeks in ((0, 1), (1, 2), (2, 0)):
        startpunkt = koordinater[startindeks]
        sluttpunkt = koordinater[sluttindeks]
        starthoyde = float(hoyder[startindeks])
        slutthoyde = float(hoyder[sluttindeks])

        if abs(starthoyde - slutthoyde) < 1e-9:
            continue
        if (nivaa < min(starthoyde, slutthoyde)) or (nivaa > max(starthoyde, slutthoyde)):
            continue

        andel = (nivaa - starthoyde) / (slutthoyde - starthoyde)
        if 0.0 <= andel <= 1.0:
            punkt = (
                startpunkt[0] + (sluttpunkt[0] - startpunkt[0]) * andel,
                startpunkt[1] + (sluttpunkt[1] - startpunkt[1]) * andel,
            )
            if not any(math.dist(punkt, eksisterende) < 1e-6 for eksisterende in krysspunkter):
                krysspunkter.append(punkt)

    if len(krysspunkter) == 2:
        return LineString(krysspunkter)
    if len(krysspunkter) > 2:
        return LineString(krysspunkter[:2])
    return None


def _ekstraher_linjer_fra_geometri(geometri) -> List[LineString]:
    if geometri is None or geometri.is_empty:
        return []
    if isinstance(geometri, LineString):
        return [geometri]
    if isinstance(geometri, MultiLineString):
        return list(geometri.geoms)
    if hasattr(geometri, "geoms"):
        linjer: List[LineString] = []
        for delgeometri in geometri.geoms:
            linjer.extend(_ekstraher_linjer_fra_geometri(delgeometri))
        return linjer
    return []


def _bygg_vegforbindelser(
    tettsteder: List[dict],
    landgeometri,
    kystlinje: LineString,
    konfig: Dict[str, object],
) -> List[Tuple[int, int]]:
    if len(tettsteder) < 2:
        return []

    tilkoblede = [0]
    utilkoblede = list(range(1, len(tettsteder)))
    forbindelser: List[Tuple[int, int]] = []

    while utilkoblede:
        beste_avstand: Optional[float] = None
        beste_forbindelse: Optional[Tuple[int, int]] = None
        reserve_avstand: Optional[float] = None
        reserve_forbindelse: Optional[Tuple[int, int]] = None

        for fra_indeks in tilkoblede:
            for til_indeks in utilkoblede:
                avstand = tettsteder[fra_indeks]["punkt"].distance(tettsteder[til_indeks]["punkt"])
                kandidatlinje = LineString(
                    [
                        (tettsteder[fra_indeks]["punkt"].x, tettsteder[fra_indeks]["punkt"].y),
                        (tettsteder[til_indeks]["punkt"].x, tettsteder[til_indeks]["punkt"].y),
                    ]
                )
                if reserve_avstand is None or avstand < reserve_avstand:
                    reserve_avstand = avstand
                    reserve_forbindelse = (fra_indeks, til_indeks)

                if _er_gyldig_veglinje(kandidatlinje, landgeometri, kystlinje, [], konfig):
                    if beste_avstand is None or avstand < beste_avstand:
                        beste_avstand = avstand
                        beste_forbindelse = (fra_indeks, til_indeks)

        valgt_forbindelse = beste_forbindelse or reserve_forbindelse
        if valgt_forbindelse is None:
            break

        forbindelser.append(valgt_forbindelse)
        tilkoblede.append(valgt_forbindelse[1])
        utilkoblede.remove(valgt_forbindelse[1])

    return forbindelser


def _lag_veglinje_mellom_tettsteder(
    startpunkt: Point,
    sluttpunkt: Point,
    landgeometri,
    kystlinje: LineString,
    eksisterende_veger: List[LineString],
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> LineString:
    for _ in range(int(konfig["veg_maks_forsok"])):
        kandidat = _bygg_iterativ_veglinje(startpunkt, sluttpunkt, konfig, tilfeldig)
        if _er_gyldig_veglinje(kandidat, landgeometri, kystlinje, eksisterende_veger, konfig):
            return kandidat

    direkte = LineString([(startpunkt.x, startpunkt.y), (sluttpunkt.x, sluttpunkt.y)])
    if _er_gyldig_veglinje(direkte, landgeometri, kystlinje, eksisterende_veger, konfig):
        return direkte

    mellompunkt = landgeometri.representative_point()
    omveg = LineString(
        [
            (startpunkt.x, startpunkt.y),
            (mellompunkt.x, mellompunkt.y),
            (sluttpunkt.x, sluttpunkt.y),
        ]
    )
    if _er_gyldig_veglinje(omveg, landgeometri, kystlinje, eksisterende_veger, konfig):
        return omveg

    raise ValueError("Klarte ikke å generere en gyldig veglinje mellom tettsteder.")


def _bygg_iterativ_veglinje(
    startpunkt: Point,
    sluttpunkt: Point,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> LineString:
    punkter: List[Punkt] = [(startpunkt.x, startpunkt.y)]
    gjeldende = (startpunkt.x, startpunkt.y)
    malpunkt = (sluttpunkt.x, sluttpunkt.y)
    forrige_retning = _normaliser_vektor((malpunkt[0] - gjeldende[0], malpunkt[1] - gjeldende[1]))
    antall_rettstrekk = 0
    har_bue = False
    maks_punkter = int(konfig["veg_maks_punkter"])
    maks_sluttavstand = max(
        float(konfig["veg_maks_segmentlengde"]),
        float(konfig["veg_maks_bueradius"]) * float(konfig["veg_bue_lengdefaktor_maks"]),
    ) * float(konfig["veg_slutt_buffer_segmenter"])

    while len(punkter) < maks_punkter:
        avstand_til_mal = math.dist(gjeldende, malpunkt)
        malretning = _normaliser_vektor((malpunkt[0] - gjeldende[0], malpunkt[1] - gjeldende[1]))
        vinkel_til_mal = _vinkel_mellom_retninger(forrige_retning, malretning)

        if avstand_til_mal <= maks_sluttavstand and vinkel_til_mal <= float(konfig["veg_maks_kurvevinkel"]) and har_bue:
            break

        bruk_bue = bool(tilfeldig.random() > float(konfig["veg_rett_sannsynlighet"]))
        if antall_rettstrekk >= int(konfig["veg_maks_rettstrekk"]):
            bruk_bue = True
        if not har_bue and avstand_til_mal > float(konfig["veg_min_segmentlengde"]):
            bruk_bue = True
        if vinkel_til_mal > float(konfig["veg_retnings_toleranse"]):
            bruk_bue = True

        forrige_avstand = avstand_til_mal

        if bruk_bue:
            radius = float(
                tilfeldig.uniform(
                    float(konfig["veg_min_bueradius"]),
                    float(konfig["veg_maks_bueradius"]),
                )
            )
            segmentlengde = _beregn_buesegmentlengde(radius, konfig, tilfeldig)
            svingfortegn = _velg_svingfortegn(forrige_retning, malretning, tilfeldig)
            svingvinkel = max(
                float(konfig["veg_min_svingvinkel"]),
                min(segmentlengde / radius, math.pi * 0.9),
            )
            buepunkter, gjeldende, forrige_retning = _lag_buesegment(
                startpunkt=gjeldende,
                startrretning=forrige_retning,
                radius=radius,
                svingfortegn=svingfortegn,
                svingvinkel=svingvinkel,
                punktavstand=float(konfig["veg_bue_punktavstand"]),
            )
            if not buepunkter:
                break
            punkter.extend(buepunkter)
            antall_rettstrekk = 0
            har_bue = True
        else:
            segmentlengde = float(
                tilfeldig.uniform(
                    float(konfig["veg_min_segmentlengde"]),
                    float(konfig["veg_maks_segmentlengde"]),
                )
            )
            segmentlengde = min(segmentlengde, max(float(konfig["veg_min_segmentlengde"]) * 0.5, forrige_avstand * 0.6))
            if segmentlengde <= 0.0:
                break
            gjeldende = (
                gjeldende[0] + forrige_retning[0] * segmentlengde,
                gjeldende[1] + forrige_retning[1] * segmentlengde,
            )
            punkter.append(gjeldende)
            antall_rettstrekk += 1

        if math.dist(gjeldende, malpunkt) >= forrige_avstand:
            break

    if gjeldende != malpunkt:
        punkter.extend(
            _lag_avsluttende_tangentbue(
                startpunkt=gjeldende,
                sluttpunkt=malpunkt,
                startrretning=forrige_retning,
                punktavstand=float(konfig["veg_bue_punktavstand"]),
            )
        )

    return LineString(punkter)


def _er_gyldig_veglinje(
    kandidat: LineString,
    landgeometri,
    kystlinje: LineString,
    eksisterende_veger: List[LineString],
    konfig: Dict[str, object],
) -> bool:
    if not kandidat.is_valid or not kandidat.is_simple:
        return False
    if not landgeometri.buffer(float(konfig["veg_korridor_buffer"])).covers(kandidat):
        return False
    if kandidat.crosses(kystlinje):
        return False

    for eksisterende_veg in eksisterende_veger:
        if kandidat.crosses(eksisterende_veg):
            return False
        if kandidat.distance(eksisterende_veg) < float(konfig["veg_min_avstand"]):
            if not _deler_endepunkt_med_eksisterende_veg(kandidat, eksisterende_veg, float(konfig["veg_min_avstand"])):
                return False
    return True


def _deler_endepunkt_med_eksisterende_veg(
    kandidat: LineString,
    eksisterende_veg: LineString,
    toleranse: float,
) -> bool:
    kandidat_ender = [Point(kandidat.coords[0]), Point(kandidat.coords[-1])]
    eksisterende_ender = [Point(eksisterende_veg.coords[0]), Point(eksisterende_veg.coords[-1])]
    return any(
        kandidatpunkt.distance(eksisterendepunkt) <= toleranse
        for kandidatpunkt in kandidat_ender
        for eksisterendepunkt in eksisterende_ender
    )


def _normaliser_vektor(vektor: Punkt) -> Punkt:
    lengde = math.hypot(vektor[0], vektor[1])
    if lengde == 0.0:
        return (0.0, 0.0)
    return (vektor[0] / lengde, vektor[1] / lengde)


def _roter_vektor(vektor: Punkt, vinkel: float) -> Punkt:
    cosinus = math.cos(vinkel)
    sinus = math.sin(vinkel)
    return (vektor[0] * cosinus - vektor[1] * sinus, vektor[0] * sinus + vektor[1] * cosinus)


def _vinkel_mellom_retninger(retning_a: Punkt, retning_b: Punkt) -> float:
    if retning_a == (0.0, 0.0) or retning_b == (0.0, 0.0):
        return 0.0
    skalarprodukt = max(-1.0, min(1.0, retning_a[0] * retning_b[0] + retning_a[1] * retning_b[1]))
    return math.acos(skalarprodukt)


def _beregn_buesegmentlengde(
    radius: float,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> float:
    faktor = float(
        tilfeldig.uniform(
            float(konfig["veg_bue_lengdefaktor_min"]),
            float(konfig["veg_bue_lengdefaktor_maks"]),
        )
    )
    return radius * faktor


def _lag_buesegment(
    startpunkt: Punkt,
    startrretning: Punkt,
    radius: float,
    svingfortegn: float,
    svingvinkel: float,
    punktavstand: float,
) -> Tuple[List[Punkt], Punkt, Punkt]:
    if radius <= 0.0 or svingvinkel <= 0.0 or startrretning == (0.0, 0.0):
        return [], startpunkt, startrretning

    venstrenormal = (-startrretning[1], startrretning[0])
    sentrum = (
        startpunkt[0] + venstrenormal[0] * radius * svingfortegn,
        startpunkt[1] + venstrenormal[1] * radius * svingfortegn,
    )
    startvektor = (startpunkt[0] - sentrum[0], startpunkt[1] - sentrum[1])
    totalvinkel = svingvinkel * svingfortegn
    buelengde = abs(radius * svingvinkel)
    antall_delsteg = max(3, int(math.ceil(buelengde / max(punktavstand, 1.0))))

    punkter: List[Punkt] = []
    for indeks in range(1, antall_delsteg + 1):
        andel = indeks / antall_delsteg
        rotert = _roter_vektor(startvektor, totalvinkel * andel)
        punkter.append((sentrum[0] + rotert[0], sentrum[1] + rotert[1]))

    sluttretning = _normaliser_vektor(_roter_vektor(startrretning, totalvinkel))
    return punkter, punkter[-1], sluttretning


def _lag_avsluttende_tangentbue(
    startpunkt: Punkt,
    sluttpunkt: Punkt,
    startrretning: Punkt,
    punktavstand: float,
) -> List[Punkt]:
    avstand = math.dist(startpunkt, sluttpunkt)
    if avstand == 0.0:
        return []

    if startrretning == (0.0, 0.0):
        return _legg_til_rett_avslutning(startpunkt, sluttpunkt, punktavstand)

    malretning = _normaliser_vektor((sluttpunkt[0] - startpunkt[0], sluttpunkt[1] - startpunkt[1]))
    kryssprodukt = startrretning[0] * malretning[1] - startrretning[1] * malretning[0]
    halvvinkel = _vinkel_mellom_retninger(startrretning, malretning)
    svingvinkel = min(math.pi * 0.95, halvvinkel * 2.0)

    if abs(kryssprodukt) < 1e-9 or svingvinkel < 1e-6:
        return _legg_til_rett_avslutning(startpunkt, sluttpunkt, punktavstand)

    sinus_halvvinkel = math.sin(svingvinkel / 2.0)
    if abs(sinus_halvvinkel) < 1e-9:
        return _legg_til_rett_avslutning(startpunkt, sluttpunkt, punktavstand)

    radius = avstand / (2.0 * abs(sinus_halvvinkel))
    buepunkter, _, _ = _lag_buesegment(
        startpunkt=startpunkt,
        startrretning=startrretning,
        radius=radius,
        svingfortegn=1.0 if kryssprodukt > 0.0 else -1.0,
        svingvinkel=svingvinkel,
        punktavstand=punktavstand,
    )
    if not buepunkter:
        return _legg_til_rett_avslutning(startpunkt, sluttpunkt, punktavstand)

    buepunkter[-1] = sluttpunkt
    return buepunkter


def _legg_til_rett_avslutning(
    startpunkt: Punkt,
    sluttpunkt: Punkt,
    maks_segmentlengde: float,
) -> List[Punkt]:
    avstand = math.dist(startpunkt, sluttpunkt)
    if avstand == 0.0:
        return []

    antall_delsegmenter = max(1, int(math.ceil(avstand / max(maks_segmentlengde, 1.0))))
    return [
        (
            startpunkt[0] + (sluttpunkt[0] - startpunkt[0]) * (indeks / antall_delsegmenter),
            startpunkt[1] + (sluttpunkt[1] - startpunkt[1]) * (indeks / antall_delsegmenter),
        )
        for indeks in range(1, antall_delsegmenter + 1)
    ]


def _velg_svingfortegn(
    forrige_retning: Punkt,
    malretning: Punkt,
    tilfeldig: np.random.Generator,
) -> float:
    kryssprodukt = forrige_retning[0] * malretning[1] - forrige_retning[1] * malretning[0]
    if kryssprodukt == 0.0:
        return float(tilfeldig.choice([-1.0, 1.0]))
    return 1.0 if kryssprodukt > 0.0 else -1.0


def _lag_3d_veglinje(
    veg2d: LineString,
    starthoyde: float,
    slutthoyde: float,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> LineString:
    punkter2d = [(punkt[0], punkt[1]) for punkt in veg2d.coords]
    hoyder: List[Optional[float]] = [None] * len(punkter2d)
    hoyder[0] = float(starthoyde)
    hoyder[-1] = float(slutthoyde)
    _fyll_hoyder_rekursivt(punkter2d, hoyder, 0, len(punkter2d) - 1, konfig, tilfeldig)
    punkter3d = [
        (punkt[0], punkt[1], float(hoyde if hoyde is not None else starthoyde))
        for punkt, hoyde in zip(punkter2d, hoyder)
    ]
    return LineString(punkter3d)


def _fyll_hoyder_rekursivt(
    punkter2d: List[Punkt],
    hoyder: List[Optional[float]],
    startindeks: int,
    sluttindeks: int,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> None:
    if sluttindeks - startindeks <= 1:
        return

    midtindeks = (startindeks + sluttindeks) // 2
    if hoyder[midtindeks] is None:
        # Sett høyde 100% linjært mellom endepunktene
        grunnhoyde = (float(hoyder[startindeks]) + float(hoyder[sluttindeks])) / 2.0
        hoyder[midtindeks] = grunnhoyde

    _fyll_hoyder_rekursivt(punkter2d, hoyder, startindeks, midtindeks, konfig, tilfeldig)
    _fyll_hoyder_rekursivt(punkter2d, hoyder, midtindeks, sluttindeks, konfig, tilfeldig)


def _beregn_antall_tettsteder(konfig: Dict[str, object], areal: float) -> int:
    grunnantall = int(konfig["tettsted_min_antall"])
    ekstra = int(areal / float(konfig["tettsted_areal_per_ekstra"]))
    return min(int(konfig["tettsted_maks_antall"]), grunnantall + ekstra)


def _finn_kystnaert_tettstedspunkt(
    kystlinje: LineString,
    landgeometri,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
    eksisterende_punkter: List[Point],
) -> Point:
    maks_forsok = int(konfig["tettsted_maks_forsok"])

    for krev_maks_avstand in (True, False):
        for _ in range(maks_forsok):
            fraksjon = float(tilfeldig.uniform(0.1, 0.9))
            grunnpunkt = kystlinje.interpolate(fraksjon, normalized=True)
            delta = float(konfig["tettsted_tangent_delta"])
            forrige_punkt = kystlinje.interpolate(max(0.0, fraksjon - (delta / max(kystlinje.length, delta))), normalized=True)
            neste_punkt = kystlinje.interpolate(min(1.0, fraksjon + (delta / max(kystlinje.length, delta))), normalized=True)
            dx = neste_punkt.x - forrige_punkt.x
            dy = neste_punkt.y - forrige_punkt.y
            lengde = math.hypot(dx, dy)
            if lengde == 0.0:
                continue

            normaler = [(-dy / lengde, dx / lengde), (dy / lengde, -dx / lengde)]
            tilfeldig.shuffle(normaler)

            for normal_x, normal_y in normaler:
                avstand = float(konfig["tettsted_kystavstand"])
                kandidat = Point(grunnpunkt.x + (normal_x * avstand), grunnpunkt.y + (normal_y * avstand))
                if not landgeometri.contains(kandidat):
                    continue
                if _punkt_har_gyldig_avstand(kandidat, eksisterende_punkter, konfig, krev_maks_avstand=krev_maks_avstand):
                    return kandidat

    representativt_punkt = landgeometri.representative_point()
    return Point(representativt_punkt.x, representativt_punkt.y)


def _finn_innlandstettstedspunkt(
    kystlinje: LineString,
    landgeometri,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
    eksisterende_punkter: List[Point],
    indeks: int,
    antall_innlandstettsteder: int,
) -> Point:
    kandidater: List[tuple[float, float, Point]] = []
    for _ in range(int(konfig["tettsted_kandidat_antall"])):
        kandidat = _lag_tilfeldig_landpunkt(landgeometri, konfig, tilfeldig)
        if kandidat is None:
            continue
        if _punkt_har_gyldig_avstand(kandidat, eksisterende_punkter, konfig, krev_maks_avstand=False):
            avstand_til_kyst = kandidat.distance(kystlinje)
            narmeste_tettsted = _narmeste_punktavstand(kandidat, eksisterende_punkter)
            kandidater.append((avstand_til_kyst, narmeste_tettsted, kandidat))

    if not kandidater:
        for _ in range(int(konfig["tettsted_kandidat_antall"])):
            kandidat = _lag_tilfeldig_landpunkt(landgeometri, konfig, tilfeldig)
            if kandidat is None:
                continue
            avstand_til_kyst = kandidat.distance(kystlinje)
            narmeste_tettsted = _narmeste_punktavstand(kandidat, eksisterende_punkter)
            kandidater.append((avstand_til_kyst, narmeste_tettsted, kandidat))

    if not kandidater:
        representativt_punkt = landgeometri.representative_point()
        return Point(representativt_punkt.x, representativt_punkt.y)

    kandidater.sort(key=lambda verdi: verdi[0], reverse=True)
    maksimal_kystavstand = kandidater[0][0]
    malavstand = _beregn_malavstand_for_innland(
        maksimal_kystavstand,
        indeks,
        antall_innlandstettsteder,
        konfig,
        tilfeldig,
    )

    beste_kandidat = min(
        kandidater,
        key=lambda verdi: (abs(verdi[0] - malavstand), -verdi[1]),
    )
    return beste_kandidat[2]


def _beregn_malavstand_for_innland(
    maksimal_kystavstand: float,
    indeks: int,
    antall_innlandstettsteder: int,
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> float:
    if antall_innlandstettsteder <= 1:
        return maksimal_kystavstand

    minste_kystandel = float(konfig["tettsted_innland_min_kystandel"])
    progresjon = indeks / max(1, antall_innlandstettsteder - 1)
    grunnandel = 1.0 - ((1.0 - minste_kystandel) * progresjon)
    jitter = float(tilfeldig.uniform(-float(konfig["tettsted_innland_avstand_jitter"]), float(konfig["tettsted_innland_avstand_jitter"])))
    malandel = min(1.0, max(minste_kystandel, grunnandel + jitter))
    return maksimal_kystavstand * malandel


def _narmeste_punktavstand(kandidat: Point, eksisterende_punkter: List[Point]) -> float:
    if not eksisterende_punkter:
        return float("inf")
    return min(kandidat.distance(punkt) for punkt in eksisterende_punkter)


def _lag_tilfeldig_landpunkt(landgeometri, konfig: Dict[str, object], tilfeldig: np.random.Generator) -> Optional[Point]:
    minx, miny, maxx, maxy = landgeometri.bounds
    margin = float(konfig["tettsted_boks_margin"])

    for _ in range(int(konfig["tettsted_maks_forsok"])):
        kandidat = Point(
            float(tilfeldig.uniform(minx + margin, maxx - margin)),
            float(tilfeldig.uniform(miny + margin, maxy - margin)),
        )
        if landgeometri.contains(kandidat):
            return kandidat
    return None


def _punkt_er_gyldig_tettsted(
    kandidat: Point,
    landgeometri,
    konfig: Dict[str, object],
    eksisterende_punkter: List[Point],
) -> bool:
    if not landgeometri.contains(kandidat):
        return False
    return _punkt_har_gyldig_avstand(kandidat, eksisterende_punkter, konfig, krev_maks_avstand=True)


def _punkt_har_gyldig_avstand(
    kandidat: Point,
    eksisterende_punkter: List[Point],
    konfig: Dict[str, object],
    krev_maks_avstand: bool,
) -> bool:
    if not eksisterende_punkter:
        return True

    minste_avstand = min(kandidat.distance(punkt) for punkt in eksisterende_punkter)
    if minste_avstand < float(konfig["tettsted_avstand_min"]):
        return False
    if krev_maks_avstand and minste_avstand > float(konfig["tettsted_avstand_maks"]):
        return False
    return True


def _velg_sammenhengende_sider(konfig: Dict[str, object], tilfeldig: np.random.Generator) -> List[str]:
    overstyrte_sider = konfig.get("valgte_sider")
    if overstyrte_sider:
        return _normaliser_sammenhengende_sider(list(overstyrte_sider))

    antall_sider = int(tilfeldig.integers(int(konfig["min_antall_sider"]), int(konfig["maks_antall_sider"]) + 1))
    startindeks = int(tilfeldig.integers(0, len(SIDE_REKKEFOLGE)))
    return [SIDE_REKKEFOLGE[(startindeks + indeks) % len(SIDE_REKKEFOLGE)] for indeks in range(antall_sider)]


def _normaliser_sammenhengende_sider(sider: List[str]) -> List[str]:
    normaliserte_sider = [side.lower() for side in sider]
    if len(set(normaliserte_sider)) != len(normaliserte_sider):
        raise ValueError("Valgte sider kan ikke inneholde duplikater.")

    for startindeks in range(len(SIDE_REKKEFOLGE)):
        kandidat = [
            SIDE_REKKEFOLGE[(startindeks + indeks) % len(SIDE_REKKEFOLGE)]
            for indeks in range(len(normaliserte_sider))
        ]
        if normaliserte_sider == kandidat or set(normaliserte_sider) == set(kandidat):
            return kandidat

    raise ValueError("Valgte sider må ligge inntil hverandre for å danne én kystlinje.")


def _lag_sammenhengende_kystlinje(
    bbox_polygon,
    valgte_sider: List[str],
    konfig: Dict[str, object],
    tilfeldig: np.random.Generator,
) -> LineString:
    maks_forsok = int(konfig["maks_forsok_per_side"])

    for _ in range(maks_forsok):
        kystpunkter: List[Punkt] = []

        hjornepunkter = _lag_hjornepunkter(
            bbox=bbox_polygon.bounds,
            avstand=float(konfig["kyst_avstand_fra_bbox"]),
            tilfeldig=tilfeldig,
            maksimal_hjorneandel=float(konfig.get("maksimal_hjorneandel", 0.3)),
        )

        for indeks, side in enumerate(valgte_sider):
            startpunkt, sluttpunkt, normal = _start_slutt_og_normal(side=side, hjornepunkter=hjornepunkter)
            sidepunkter = _del_segment_rekursivt(
                startpunkt=startpunkt,
                sluttpunkt=sluttpunkt,
                normal=normal,
                tilfeldig=tilfeldig,
                minste_segmentlengde=float(konfig["minste_segmentlengde"]),
                avviksfaktor=float(konfig["avviksfaktor"]),
                maks_innoveravvik=float(konfig["maks_innoveravvik"]),
                maks_utoveravvik=float(konfig["kyst_avstand_fra_bbox"]) * 0.95,
            )
            if indeks > 0:
                sidepunkter = sidepunkter[1:]
            kystpunkter.extend(sidepunkter)

        if len(valgte_sider) == len(SIDE_REKKEFOLGE) and kystpunkter[0] != kystpunkter[-1]:
            kystpunkter.append(kystpunkter[0])

        kystlinje = LineString(kystpunkter)
        if _er_gyldig_kystlinje(kystlinje, bbox_polygon):
            return kystlinje

    raise ValueError("Klarte ikke å generere en gyldig sammenhengende kystlinje.")


def _lag_havpolygon_fra_kystlinje(
    kystlinje: LineString,
    valgte_sider: List[str],
    bbox: Tuple[float, float, float, float],
) -> Polygon:
    kystpunkter = list(kystlinje.coords)
    startpunkt = kystpunkter[0]
    sluttpunkt = kystpunkter[-1]
    startprojeksjon = _projiser_til_bboxkant(startpunkt, valgte_sider[0], bbox)
    sluttprojeksjon = _projiser_til_bboxkant(sluttpunkt, valgte_sider[-1], bbox)
    grensepunkter = _lag_grensepunkter_langs_bbox(startprojeksjon, sluttprojeksjon, valgte_sider, bbox)
    return Polygon(kystpunkter + grensepunkter)


def _projiser_til_bboxkant(punkt: Punkt, side: str, bbox: Tuple[float, float, float, float]) -> Punkt:
    minx, miny, maxx, maxy = bbox
    if side == "vest":
        return (minx, punkt[1])
    if side == "nord":
        return (punkt[0], maxy)
    if side == "ost":
        return (maxx, punkt[1])
    if side == "sor":
        return (punkt[0], miny)
    raise ValueError(f"Ukjent side: {side}")


def _lag_grensepunkter_langs_bbox(
    startprojeksjon: Punkt,
    sluttprojeksjon: Punkt,
    valgte_sider: List[str],
    bbox: Tuple[float, float, float, float],
) -> List[Punkt]:
    grensepunkter: List[Punkt] = [sluttprojeksjon]

    for indeks, side in enumerate(reversed(valgte_sider)):
        if indeks == len(valgte_sider) - 1:
            neste_punkt = startprojeksjon
        else:
            neste_punkt = _hent_start_hjorne_for_side(side, bbox)

        if grensepunkter[-1] != neste_punkt:
            grensepunkter.append(neste_punkt)

    return grensepunkter


def _hent_start_hjorne_for_side(side: str, bbox: Tuple[float, float, float, float]) -> Punkt:
    minx, miny, maxx, maxy = bbox
    if side == "vest":
        return (minx, miny)
    if side == "nord":
        return (minx, maxy)
    if side == "ost":
        return (maxx, maxy)
    if side == "sor":
        return (maxx, miny)
    raise ValueError(f"Ukjent side: {side}")


def _lag_hjornepunkter(
    bbox: Tuple[float, float, float, float],
    avstand: float,
    tilfeldig: np.random.Generator,
    maksimal_hjorneandel: float,
) -> Dict[str, Punkt]:
    minx, miny, maxx, maxy = bbox
    bredde = maxx - minx - (2.0 * avstand)
    hoyde = maxy - miny - (2.0 * avstand)
    maks_x_inn = bredde * maksimal_hjorneandel
    maks_y_inn = hoyde * maksimal_hjorneandel

    return {
        "sv": (
            minx + avstand + float(tilfeldig.uniform(0.0, maks_x_inn)),
            miny + avstand + float(tilfeldig.uniform(0.0, maks_y_inn)),
        ),
        "nv": (
            minx + avstand + float(tilfeldig.uniform(0.0, maks_x_inn)),
            maxy - avstand - float(tilfeldig.uniform(0.0, maks_y_inn)),
        ),
        "no": (
            maxx - avstand - float(tilfeldig.uniform(0.0, maks_x_inn)),
            maxy - avstand - float(tilfeldig.uniform(0.0, maks_y_inn)),
        ),
        "so": (
            maxx - avstand - float(tilfeldig.uniform(0.0, maks_x_inn)),
            miny + avstand + float(tilfeldig.uniform(0.0, maks_y_inn)),
        ),
    }


def _start_slutt_og_normal(side: str, hjornepunkter: Dict[str, Punkt]) -> Tuple[Punkt, Punkt, Punkt]:
    if side == "vest":
        return hjornepunkter["sv"], hjornepunkter["nv"], (1.0, 0.0)
    if side == "nord":
        return hjornepunkter["nv"], hjornepunkter["no"], (0.0, -1.0)
    if side == "ost":
        return hjornepunkter["no"], hjornepunkter["so"], (-1.0, 0.0)
    if side == "sor":
        return hjornepunkter["so"], hjornepunkter["sv"], (0.0, 1.0)
    raise ValueError(f"Ukjent side: {side}")


def _del_segment_rekursivt(
    startpunkt: Punkt,
    sluttpunkt: Punkt,
    normal: Punkt,
    tilfeldig: np.random.Generator,
    minste_segmentlengde: float,
    avviksfaktor: float,
    maks_innoveravvik: float,
    maks_utoveravvik: float,
    er_forste_deling: bool = True,
) -> List[Punkt]:
    segmentlengde = math.dist(startpunkt, sluttpunkt)
    if segmentlengde <= minste_segmentlengde:
        return [startpunkt, sluttpunkt]

    midtpunkt = ((startpunkt[0] + sluttpunkt[0]) / 2.0, (startpunkt[1] + sluttpunkt[1]) / 2.0)
    maks_toveis_avvik = min(segmentlengde / avviksfaktor, maks_innoveravvik, maks_utoveravvik)
    if er_forste_deling:
        fortegn = float(tilfeldig.choice([-1.0, 1.0]))
        avvik = maks_toveis_avvik * fortegn
    else:
        avvik = float(tilfeldig.uniform(-maks_toveis_avvik, maks_toveis_avvik))
    forskyvet_midtpunkt = (midtpunkt[0] + normal[0] * avvik, midtpunkt[1] + normal[1] * avvik)

    venstre = _del_segment_rekursivt(
        startpunkt=startpunkt,
        sluttpunkt=forskyvet_midtpunkt,
        normal=normal,
        tilfeldig=tilfeldig,
        minste_segmentlengde=minste_segmentlengde,
        avviksfaktor=avviksfaktor,
        maks_innoveravvik=maks_innoveravvik,
        maks_utoveravvik=maks_utoveravvik,
        er_forste_deling=False,
    )
    hoyre = _del_segment_rekursivt(
        startpunkt=forskyvet_midtpunkt,
        sluttpunkt=sluttpunkt,
        normal=normal,
        tilfeldig=tilfeldig,
        minste_segmentlengde=minste_segmentlengde,
        avviksfaktor=avviksfaktor,
        maks_innoveravvik=maks_innoveravvik,
        maks_utoveravvik=maks_utoveravvik,
        er_forste_deling=False,
    )
    return venstre[:-1] + hoyre


def _er_gyldig_kystlinje(kystlinje: LineString, bbox_polygon) -> bool:
    if not kystlinje.is_valid:
        return False
    if not (kystlinje.is_simple or kystlinje.is_ring):
        return False
    return bbox_polygon.covers(kystlinje)

# --- Amøbeformet tettbebyggelse ---

def generer_tettbebyggelse(stedsnavntekst: gpd.GeoDataFrame, konfig: Dict[str, object]) -> gpd.GeoDataFrame:
    """
    Genererer polygon for tettbebyggelse rundt hvert tettstedspunkt.
    For hvert tettsted genereres 8 punkter i 8 retninger med radius i [400,800] meter ±30%.
    Polygonet fortettes slik at punktavstand er ca 100 meter og glattes med buffer.
    """
    import numpy as np
    from shapely.geometry import Polygon

    resultater = []
    antall_retn = 8
    for _, rad in stedsnavntekst.iterrows():
        x0, y0 = rad.geometry.x, rad.geometry.y
        base_radius = np.random.uniform(400, 800)
        punkter = []
        for i in range(antall_retn):
            vinkel = 2 * np.pi * i / antall_retn
            avvik = np.random.uniform(0.7, 1.3)
            r = base_radius * avvik
            x = x0 + r * np.cos(vinkel)
            y = y0 + r * np.sin(vinkel)
            punkter.append((x, y))
        poly = Polygon(punkter)
        # Fortett polygonen: interpoler punkter slik at punktavstand ~100m
        coords = list(poly.exterior.coords)
        fortettet_coords = []
        for i in range(len(coords)-1):
            x1, y1 = coords[i]
            x2, y2 = coords[i+1]
            fortettet_coords.append((x1, y1))
            dist = np.hypot(x2-x1, y2-y1)
            n_pts = int(dist // 100)
            for j in range(1, n_pts+1):
                t = j/(n_pts+1)
                nx = x1 + t*(x2-x1)
                ny = y1 + t*(y2-y1)
                fortettet_coords.append((nx, ny))
        poly_fortettet = Polygon(fortettet_coords)
        # Glatt polygonen med buffer(50)->buffer(-50)
        poly_glatt = poly_fortettet.buffer(50).buffer(-50)
        resultater.append({
            "geometry": poly_glatt,
            "objekttype": "N50-Tettbebyggelse",
            "navn": rad.get("navn", "")
        })
    if not resultater:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=konfig["crs"])
    return gpd.GeoDataFrame(resultater, geometry="geometry", crs=konfig["crs"])

