from __future__ import annotations

import math
from typing import Dict, List, Optional

import geopandas as gpd
import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point, Polygon
from shapely.ops import split

from .synthetic_n50_module import _lag_3d_veglinje


def generer_kommunal_veg(
    tettbebyggelse: gpd.GeoDataFrame,
    vegsenterlinje_fylke: gpd.GeoDataFrame,
    konfig: Dict,
    havflate: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Generer kommunalveg som ring langs tettbebyggelse, splittet i kryss med fylkesveg."""
    crs = konfig.get("crs") or tettbebyggelse.crs or vegsenterlinje_fylke.crs
    if tettbebyggelse.empty:
        return _tom_kommunalveg_gdf(crs)

    seed = konfig.get("seed")
    seed_offset = int(konfig.get("kommunal_veg_seed_offset", 2100))
    tilfeldig = np.random.default_rng(None if seed is None else int(seed) + seed_offset)

    hjorneradius = float(konfig.get("kommunal_veg_hjorneradius", 100.0))
    innover_buffer_basis = float(konfig.get("kommunal_veg_innover_buffer", 40.0))
    min_segmentlengde = float(konfig.get("kommunal_veg_min_segmentlengde", 20.0))

    fylkeslinjer = [linje for linje in (_til_2d_linje(geom) for geom in vegsenterlinje_fylke.geometry) if linje is not None]
    havgeom = None
    if havflate is not None and not havflate.empty:
        havdeler = [geom for geom in havflate.geometry if geom is not None and not geom.is_empty]
        if havdeler:
            havgeom = havdeler[0]

    kommunal_veger: List[dict] = []
    for polygon_id, tett_rad in tettbebyggelse.iterrows():
        polygon = _som_polygon(tett_rad.geometry)
        if polygon is None:
            continue

        # Hent høyden fra tettbebyggelsen (som har høyde fra stedsnavnteksten)
        tettsted_hoyde = float(tett_rad.get("hoyde", 0.0))

        # For kysttettsteder: klipp tettbebyggelsespolygon mot land (trekk fra hav)
        arbeidspolygon = polygon
        if havgeom is not None and polygon.intersects(havgeom):
            land_del = polygon.difference(havgeom)
            land_polygon = _som_polygon(land_del)
            if land_polygon is not None:
                arbeidspolygon = land_polygon

        ringpolygon = _lag_ringpolygon_med_buffer_og_avrunding(
            polygon=arbeidspolygon,
            innover_buffer=innover_buffer_basis,
            hjorneradius=hjorneradius,
        )
        if ringpolygon is None:
            continue
        ringlinje = LineString([(float(x), float(y)) for x, y in ringpolygon.exterior.coords])
        segmenter = _splitt_linje_mot_fylkesveger(ringlinje, fylkeslinjer)

        for segment in segmenter:
            if segment.length < min_segmentlengde:
                continue

            # Alle punkter i kommunalveien får samme høyde som tettstedet
            veg3d = _lag_3d_veglinje(
                veg2d=segment,
                starthoyde=tettsted_hoyde,
                slutthoyde=tettsted_hoyde,
                konfig=konfig,
                tilfeldig=tilfeldig,
            )
            kommunal_veger.append(
                {
                    "geometry": veg3d,
                    "objekttype": "N50-VegSenterlinjeKommunal",
                    "radius": hjorneradius,
                    "polygon_id": polygon_id,
                    "fra_veg_id": -1,
                    "til_veg_id": -1,
                    "side_av_fylkesveg": "ring_segment",
                }
            )

        interne_linjer = _lag_interne_linjer_i_ringpolygon(ringpolygon)
        for intern_linje in interne_linjer:
            internsegmenter = _splitt_linje_mot_fylkesveger(intern_linje, fylkeslinjer)
            for segment in internsegmenter:
                if segment.length < min_segmentlengde:
                    continue

                # Alle punkter i eikevegen får samme høyde som tettstedet
                veg3d = _lag_3d_veglinje(
                    veg2d=segment,
                    starthoyde=tettsted_hoyde,
                    slutthoyde=tettsted_hoyde,
                    konfig=konfig,
                    tilfeldig=tilfeldig,
                )
                kommunal_veger.append(
                    {
                        "geometry": veg3d,
                        "objekttype": "N50-VegSenterlinjeKommunal",
                        "radius": hjorneradius,
                        "polygon_id": polygon_id,
                        "fra_veg_id": -1,
                        "til_veg_id": -1,
                        "side_av_fylkesveg": "eikeveg_segment",
                    }
                )

    if not kommunal_veger:
        return _tom_kommunalveg_gdf(crs)
    return gpd.GeoDataFrame(kommunal_veger, geometry="geometry", crs=crs)


def _tom_kommunalveg_gdf(crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        columns=["geometry", "objekttype", "radius", "polygon_id", "fra_veg_id", "til_veg_id", "side_av_fylkesveg"],
        geometry="geometry",
        crs=crs,
    )


def _som_polygon(geometri) -> Optional[Polygon]:
    if geometri is None or geometri.is_empty:
        return None
    polygon = geometri.buffer(0)
    if polygon.is_empty:
        return None
    if polygon.geom_type == "Polygon":
        return polygon
    if hasattr(polygon, "geoms"):
        polygoner = [delgeom for delgeom in polygon.geoms if delgeom.geom_type == "Polygon" and not delgeom.is_empty]
        if polygoner:
            return max(polygoner, key=lambda delgeom: delgeom.area)
    return None


def _lag_ringpolygon_med_buffer_og_avrunding(
    polygon: Polygon,
    innover_buffer: float,
    hjorneradius: float,
) -> Optional[Polygon]:

    arbeidsflate = polygon.buffer(-innover_buffer)
    if arbeidsflate.is_empty:
        arbeidsflate = polygon.buffer(-max(innover_buffer * 0.5, 1.0))
    if arbeidsflate.is_empty:
        arbeidsflate = polygon

    skarp_polygon = _som_polygon(arbeidsflate)
    if skarp_polygon is None:
        return None

    # Forenkle til hoveddireksjonspunkter så buffer-avrunding gir synlige buer
    forenklet = skarp_polygon.simplify(hjorneradius, preserve_topology=True)
    forenklet_polygon = _som_polygon(forenklet)
    if forenklet_polygon is None or forenklet_polygon.is_empty:
        forenklet_polygon = skarp_polygon

    # Rund av konvekse hjørner (utovervendte): closing
    lukket = forenklet_polygon.buffer(hjorneradius, join_style=1).buffer(-hjorneradius, join_style=1)
    lukket_polygon = _som_polygon(lukket) or forenklet_polygon
    # Rund av konkave hjørner (innovervendte): opening
    aapnet = lukket_polygon.buffer(-hjorneradius, join_style=1).buffer(hjorneradius, join_style=1)
    avrundet_polygon = _som_polygon(aapnet)
    if avrundet_polygon is None:
        return lukket_polygon
    return avrundet_polygon


def _splitt_linje_mot_fylkesveger(ringlinje: LineString, fylkeslinjer: List[LineString]) -> List[LineString]:
    snittpunkter: List[Point] = []
    for fylkeslinje in fylkeslinjer:
        if not ringlinje.intersects(fylkeslinje):
            continue
        snitt = ringlinje.intersection(fylkeslinje)
        snittpunkter.extend(_punktgeometrier(snitt))

    if not snittpunkter:
        return [ringlinje]

    unike: List[Point] = []
    for punkt in snittpunkter:
        if all(punkt.distance(eksisterende) > 0.25 for eksisterende in unike):
            unike.append(punkt)

    if not unike:
        return [ringlinje]

    delt = split(ringlinje, MultiPoint(unike))
    linjer: List[LineString] = []
    for geometri in delt.geoms:
        if isinstance(geometri, LineString) and geometri.length > 0.0:
            linjer.append(geometri)
    return linjer or [ringlinje]


def _lag_interne_linjer_i_ringpolygon(ringpolygon: Polygon) -> List[LineString]:
    """Lag interne eikeveger fra side 1->4 og eventuelt 5->8 hvis nok sider."""
    antall_sider = 8
    sidepar = [(1, 4)]
    antall_koordinater = max(0, len(list(ringpolygon.exterior.coords)) - 1)
    if antall_koordinater >= antall_sider:
        sidepar.append((5, 8))
    interne_linjer: List[LineString] = []

    for startside, sluttside in sidepar:
        startpunkt = _midtpunkt_pa_side(ringpolygon, startside, antall_sider)
        sluttpunkt = _midtpunkt_pa_side(ringpolygon, sluttside, antall_sider)
        if startpunkt is None or sluttpunkt is None:
            continue

        kandidat = LineString([startpunkt, sluttpunkt])
        intern = _indre_del_av_linje_i_polygon(kandidat, ringpolygon)
        if intern is not None and intern.length > 0.0:
            interne_linjer.append(intern)

    return interne_linjer


def _midtpunkt_pa_side(polygon: Polygon, side_nr: int, antall_sider: int) -> Optional[Point]:
    if antall_sider <= 0:
        return None
    ring = LineString([(float(x), float(y)) for x, y in polygon.exterior.coords])
    if ring.length == 0.0:
        return None

    side_indeks = (int(side_nr) - 1) % antall_sider
    startmaal = (side_indeks / antall_sider) * ring.length
    sluttmaal = ((side_indeks + 1) / antall_sider) * ring.length
    midtmaal = (startmaal + sluttmaal) * 0.5
    return ring.interpolate(midtmaal)


def _indre_del_av_linje_i_polygon(linje: LineString, polygon: Polygon) -> Optional[LineString]:
    snitt = linje.intersection(polygon)
    if snitt is None or snitt.is_empty:
        return None
    if isinstance(snitt, LineString):
        return snitt
    if isinstance(snitt, MultiLineString):
        deler = [del_linje for del_linje in snitt.geoms if del_linje.length > 0.0]
        if deler:
            return max(deler, key=lambda del_linje: del_linje.length)
    if isinstance(snitt, GeometryCollection):
        deler = [delgeom for delgeom in snitt.geoms if isinstance(delgeom, LineString) and delgeom.length > 0.0]
        if deler:
            return max(deler, key=lambda del_linje: del_linje.length)
    return None


def _punktgeometrier(geometri) -> List[Point]:
    if geometri is None or geometri.is_empty:
        return []
    if geometri.geom_type == "Point":
        return [geometri]
    if geometri.geom_type == "MultiPoint":
        return list(geometri.geoms)
    if geometri.geom_type == "LineString":
        koordinater = list(geometri.coords)
        if not koordinater:
            return []
        return [Point(float(koordinater[0][0]), float(koordinater[0][1])), Point(float(koordinater[-1][0]), float(koordinater[-1][1]))]
    if hasattr(geometri, "geoms"):
        punkter: List[Point] = []
        for delgeom in geometri.geoms:
            punkter.extend(_punktgeometrier(delgeom))
        return punkter
    return []


def _til_2d_linje(geometri) -> Optional[LineString]:
    if geometri is None or geometri.is_empty:
        return None
    if isinstance(geometri, LineString):
        koordinater = [(float(punkt[0]), float(punkt[1])) for punkt in geometri.coords]
        if len(koordinater) >= 2:
            return LineString(koordinater)
        return None
    if isinstance(geometri, MultiLineString):
        deler = [
            LineString([(float(punkt[0]), float(punkt[1])) for punkt in del_linje.coords])
            for del_linje in geometri.geoms
            if len(del_linje.coords) >= 2
        ]
        if not deler:
            return None
        return max(deler, key=lambda del_linje: del_linje.length)
    return None


def _hoyde_for_punkt(punkt_xy: tuple[float, float], vegsenterlinje_fylke: gpd.GeoDataFrame) -> float:
    if vegsenterlinje_fylke is None or vegsenterlinje_fylke.empty:
        return 0.0
    punkt = Point(float(punkt_xy[0]), float(punkt_xy[1]))

    beste_avstand = float("inf")
    beste_hoyde = 0.0
    for _, veg_rad in vegsenterlinje_fylke.iterrows():
        linje3d = veg_rad.geometry
        linje2d = _til_2d_linje(linje3d)
        if linje2d is None or linje2d.length == 0.0:
            continue
        maal = float(linje2d.project(punkt))
        pa_linje = linje2d.interpolate(maal)
        avstand = float(pa_linje.distance(punkt))
        if avstand < beste_avstand:
            beste_avstand = avstand
            beste_hoyde = _interpoler_hoyde_pa_linje(linje3d, maal)
    return float(beste_hoyde)


def _interpoler_hoyde_pa_linje(linje: LineString, maal: float) -> float:
    koordinater = list(linje.coords)
    if len(koordinater) < 2:
        return 0.0
    if len(koordinater[0]) < 3:
        return 0.0

    gjenstaende = max(0.0, maal)
    for startpunkt, sluttpunkt in zip(koordinater, koordinater[1:]):
        segmentlengde = math.dist((float(startpunkt[0]), float(startpunkt[1])), (float(sluttpunkt[0]), float(sluttpunkt[1])))
        if segmentlengde == 0.0:
            continue
        if gjenstaende <= segmentlengde:
            andel = gjenstaende / segmentlengde
            return float(startpunkt[2] + ((sluttpunkt[2] - startpunkt[2]) * andel))
        gjenstaende -= segmentlengde
    return float(koordinater[-1][2])
