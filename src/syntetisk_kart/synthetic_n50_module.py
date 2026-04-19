"""Generering av syntetiske N50-objekter."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box

Punkt = Tuple[float, float]
SIDE_REKKEFOLGE = ["vest", "nord", "ost", "sor"]


def generer_kystkontur(konfig: Dict[str, object]) -> gpd.GeoDataFrame:
    """Generer én sammenhengende N50-kystkontur innenfor angitt bbox."""
    bbox_verdier = tuple(konfig["bbox"])
    bbox_polygon = box(*bbox_verdier)
    tilfeldig = np.random.default_rng(int(konfig["seed"]))
    valgte_sider = _velg_sammenhengende_sider(konfig, tilfeldig)
    kystlinje = _lag_sammenhengende_kystlinje(bbox_polygon, valgte_sider, konfig, tilfeldig)

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


def generer_stedsnavntekst(
    kystkontur: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Generer N50-stedsnavntekst som 3D-punkter for tettsteder."""
    tilfeldig = np.random.default_rng(int(konfig["seed"]) + int(konfig["stedsnavn_seed_offset"]))
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

    return gpd.GeoDataFrame(tettsteder, geometry="geometry", crs=konfig["crs"])


def generer_vegsenterlinje(
    stedsnavntekst: gpd.GeoDataFrame,
    kystkontur: gpd.GeoDataFrame,
    havflate: gpd.GeoDataFrame,
    konfig: Dict[str, object],
) -> gpd.GeoDataFrame:
    """Generer N50-vegsenterlinjer som 3D-linjer mellom tettsteder."""
    tilfeldig = np.random.default_rng(int(konfig["seed"]) + int(konfig["veg_seed_offset"]))
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

    for fra_indeks, til_indeks in forbindelser:
        fra_tettsted = tettsteder[fra_indeks]
        til_tettsted = tettsteder[til_indeks]
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
                maks_delstegvinkel=float(konfig["veg_maks_delstegvinkel"]),
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
                maks_buelengde=float(konfig["veg_maks_bueradius"]) * float(konfig["veg_bue_lengdefaktor_maks"]) * float(konfig["veg_sluttbue_maks_forhold"]),
                maks_delstegvinkel=float(konfig["veg_maks_delstegvinkel"]),
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
    maks_delstegvinkel: float,
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
    antall_delsteg = max(
        3,
        int(math.ceil(buelengde / max(punktavstand, 1.0))),
        int(math.ceil(abs(totalvinkel) / max(maks_delstegvinkel, 1e-6))),
    )

    punkter: List[Punkt] = []
    for indeks in range(1, antall_delsteg + 1):
        andel = indeks / antall_delsteg
        rotert = _roter_vektor(startvektor, totalvinkel * andel)
        punkter.append((sentrum[0] + rotert[0], sentrum[1] + rotert[1]))

    if len(punkter) == 1:
        sluttretning = _normaliser_vektor((punkter[-1][0] - startpunkt[0], punkter[-1][1] - startpunkt[1]))
    else:
        sluttretning = _normaliser_vektor((punkter[-1][0] - punkter[-2][0], punkter[-1][1] - punkter[-2][1]))
    return punkter, punkter[-1], sluttretning


def _lag_avsluttende_tangentbue(
    startpunkt: Punkt,
    sluttpunkt: Punkt,
    startrretning: Punkt,
    punktavstand: float,
    maks_buelengde: float,
    maks_delstegvinkel: float,
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
    buelengde = radius * svingvinkel
    if buelengde > maks_buelengde:
        antall_delbuer = max(2, int(math.ceil(buelengde / max(maks_buelengde, punktavstand))))
        alle_punkter: List[Punkt] = []
        gjeldende_start = startpunkt
        gjeldende_retning = startrretning
        for indeks in range(1, antall_delbuer + 1):
            andel = indeks / antall_delbuer
            delslutt = (
                startpunkt[0] + (sluttpunkt[0] - startpunkt[0]) * andel,
                startpunkt[1] + (sluttpunkt[1] - startpunkt[1]) * andel,
            )
            delpunkter = _lag_avsluttende_tangentbue(
                startpunkt=gjeldende_start,
                sluttpunkt=delslutt,
                startrretning=gjeldende_retning,
                punktavstand=punktavstand,
                maks_buelengde=maks_buelengde,
                maks_delstegvinkel=maks_delstegvinkel,
            )
            if not delpunkter:
                return _legg_til_rett_avslutning(startpunkt, sluttpunkt, punktavstand)
            alle_punkter.extend(delpunkter)
            if len(delpunkter) == 1:
                gjeldende_retning = _normaliser_vektor((delpunkter[-1][0] - gjeldende_start[0], delpunkter[-1][1] - gjeldende_start[1]))
            else:
                gjeldende_retning = _normaliser_vektor((delpunkter[-1][0] - delpunkter[-2][0], delpunkter[-1][1] - delpunkter[-2][1]))
            gjeldende_start = delslutt
        alle_punkter[-1] = sluttpunkt
        return alle_punkter

    buepunkter, _, _ = _lag_buesegment(
        startpunkt=startpunkt,
        startrretning=startrretning,
        radius=radius,
        svingfortegn=1.0 if kryssprodukt > 0.0 else -1.0,
        svingvinkel=svingvinkel,
        punktavstand=punktavstand,
        maks_delstegvinkel=maks_delstegvinkel,
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
        lengde = math.dist(punkter2d[startindeks], punkter2d[sluttindeks])
        grunnhoyde = (float(hoyder[startindeks]) + float(hoyder[sluttindeks])) / 2.0
        maks_avvik = lengde / float(konfig["veg_hoyde_avviksfaktor"])
        hoyder[midtindeks] = grunnhoyde + float(tilfeldig.uniform(-maks_avvik, maks_avvik))

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


def _lag_tilfeldig_landpunkt(landgeometri, konfig: Dict[str, object], tilfeldig: np.random.Generator) -> Point | None:
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
        grunnavvik = min(segmentlengde * 1.9, maks_toveis_avvik)
        fortegn = float(tilfeldig.choice([-1.0, 1.0]))
        avvik = grunnavvik * fortegn
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

