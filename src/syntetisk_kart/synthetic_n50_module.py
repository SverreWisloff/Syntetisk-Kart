"""Generering av syntetiske N50-objekter."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

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
            if _punkt_er_gyldig_tettsted(kandidat, landgeometri, konfig, eksisterende_punkter):
                return kandidat

    raise ValueError("Klarte ikke å plassere kysttettsted.")


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
        raise ValueError("Klarte ikke å plassere innlandstettsted.")

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
) -> List[Punkt]:
    segmentlengde = math.dist(startpunkt, sluttpunkt)
    if segmentlengde <= minste_segmentlengde:
        return [startpunkt, sluttpunkt]

    midtpunkt = ((startpunkt[0] + sluttpunkt[0]) / 2.0, (startpunkt[1] + sluttpunkt[1]) / 2.0)
    maks_toveis_avvik = min(segmentlengde / avviksfaktor, maks_innoveravvik, maks_utoveravvik)
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
    )
    return venstre[:-1] + hoyre


def _er_gyldig_kystlinje(kystlinje: LineString, bbox_polygon) -> bool:
    if not kystlinje.is_valid:
        return False
    if not (kystlinje.is_simple or kystlinje.is_ring):
        return False
    return bbox_polygon.covers(kystlinje)

