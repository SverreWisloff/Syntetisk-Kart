"""
Modul for å generere innsjøkanter (N50-Innsjøkant) basert på lukkede høydekurver.
"""
import geopandas as gpd
from shapely.geometry import Polygon, LineString
import numpy as np


def finn_lukkede_hoydekurver(hoydekurver_gdf):
    """Returnerer GeoDataFrame med kun lukkede høydekurver."""
    return hoydekurver_gdf[hoydekurver_gdf.geometry.apply(lambda g: isinstance(g, LineString) and g.is_ring)]


def areal_og_bredde(polygon):
    areal = polygon.area
    min_bredde = polygon.minimum_clearance
    return areal, min_bredde


def generer_innsjokanter(hoydekurver_gdf, min_areal=300, min_bredde=15):
    """
    Finn lukkede høydekurver som er kandidater for innsjøkant.
    Returnerer GeoDataFrame med innsjøkanter (Polygoner).
    """
    lukkede = finn_lukkede_hoydekurver(hoydekurver_gdf)
    innsjo_polygons = []
    # For hver lukket høydekurve, sjekk om den omslutter 1-3 lukkede høydekurver med lavere høyde
    for idx, row in lukkede.iterrows():
        poly = Polygon(row.geometry)
        areal, bredde = areal_og_bredde(poly)
        if areal <= min_areal or bredde <= min_bredde:
            continue
        hoyde = row["hoyde"] if "hoyde" in row else None
        # Finn lukkede høydekurver som ligger inni denne og har lavere høyde
        inni = lukkede[(lukkede.index != idx) &
                      (lukkede.geometry.apply(lambda g: Polygon(g).within(poly))) &
                      (lukkede["hoyde"] < hoyde)]
        if 1 <= len(inni) <= 3:
            innsjo_polygons.append({
                "geometry": poly,
                "hoyde": hoyde
            })
    if innsjo_polygons:
        return gpd.GeoDataFrame(innsjo_polygons, geometry="geometry")
    else:
        # Returner tom GeoDataFrame med riktige kolonner
        return gpd.GeoDataFrame(columns=["geometry", "hoyde"], geometry="geometry")

