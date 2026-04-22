"""
Modul for å generere innsjøkanter (N50-Innsjøkant) basert på lukkede høydekurver.

Funksjonene her brukes til å identifisere og lage polygoner for innsjøer ut fra høydekurver.
Alle terskelverdier og parametre sendes inn som argumenter, ikke hardkodet.
"""
import geopandas as gpd
from shapely.geometry import Polygon, LineString


def finn_lukkede_hoydekurver(hoydekurver_gdf):
    """
    Returnerer kun de høydekurvene som er lukkede (is_ring).
    Args:
        hoydekurver_gdf: GeoDataFrame med høydekurver.
    Returnerer:
        GeoDataFrame med lukkede høydekurver (LineString).
    """
    return hoydekurver_gdf[hoydekurver_gdf.geometry.apply(lambda g: isinstance(g, LineString) and g.is_ring)]


def areal_og_bredde(polygon):
    """
    Beregn areal og minste bredde for et polygon.
    Args:
        polygon: Shapely Polygon.
    Returnerer:
        Tuple (areal, min_bredde)
    """
    areal = polygon.area
    min_bredde = polygon.minimum_clearance
    return areal, min_bredde


def generer_innsjokanter(
    hoydekurver_gdf,
    min_areal=300,
    min_bredde=15,
    min_antall_inni=1,
    maks_antall_inni=3
):
    """
    Finn lukkede høydekurver som er kandidater for innsjøkant.
    Args:
        hoydekurver_gdf: GeoDataFrame med høydekurver.
        min_areal: Minimum areal for innsjø (m²).
        min_bredde: Minimum bredde for innsjø (meter).
        min_antall_inni: Minimum antall lukkede høydekurver inni (default 1).
        maks_antall_inni: Maks antall lukkede høydekurver inni (default 3).
    Returnerer:
        GeoDataFrame med innsjøkanter (Polygoner).
    """
    lukkede = finn_lukkede_hoydekurver(hoydekurver_gdf)
    innsjo_polygons = []
    # For hver lukket høydekurve, sjekk om den omslutter min_antall_inni-maks_antall_inni lukkede høydekurver med lavere høyde
    for idx, row in lukkede.iterrows():
        poly = Polygon(row.geometry)
        areal, bredde = areal_og_bredde(poly)
        if areal <= min_areal or bredde <= min_bredde:
            continue
        hoyde = row["hoyde"] if "hoyde" in row else None
        # Finn lukkede høydekurver som ligger inni denne og har lavere høyde
        inni = lukkede[(lukkede.index != idx)
                      & (lukkede.geometry.apply(lambda g: Polygon(g).within(poly)))
                      & (lukkede["hoyde"] < hoyde)]
        if min_antall_inni <= len(inni) <= maks_antall_inni:
            innsjo_polygons.append({
                "geometry": poly,
                "hoyde": hoyde
            })
    if innsjo_polygons:
        return gpd.GeoDataFrame(innsjo_polygons, geometry="geometry")
    else:
        # Returner tom GeoDataFrame med riktige kolonner
        return gpd.GeoDataFrame(columns=["geometry", "hoyde"], geometry="geometry")

