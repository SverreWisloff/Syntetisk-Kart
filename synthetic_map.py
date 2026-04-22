
from __future__ import annotations
from syntetisk_kart.synthetic_n50_module import generer_tettbebyggelse, generer_innsjokant
"""Orkestrator for generering av syntetisk kart."""

import argparse
import os
from pathlib import Path
from shapely.geometry import box
from typing import Any, Dict, Optional

from syntetisk_kart.synthetic_n50_module import (
    generer_havflate,
    generer_hoydekurve,
    generer_kystkontur,
    generer_stedsnavntekst,
    generer_terrengpunkt,
    generer_tin,
    generer_vegsenterlinje,
)

from geopandas import GeoDataFrame
import pandas as pd

STANDARD_KONFIGURASJON: Dict[str, Any] = {
    # BBOX med høyde (nord-sør) 8000 meter, behold samme sentrum
    # Opprinnelig: (497929.0, 7027929.0, 512071.0, 7042071.0)
    # Bredde beholdes (12000), høyde settes til 8000
    # Senter: ((499000+511000)/2, (7030429+7044571)/2) = (505000, 7037500)
    # Utvidet BBOX: 1000 meter bredere (500 meter på hver side)
    "bbox": (449500.0, 7033000.0, 462500.0, 7040000.0),
    "crs": "EPSG:25833",
    "seed": None,
    "n50_filnavn": "N50.gpkg",
    "kystlag_navn": "n50_kystkontur",
    "havlag_navn": "n50_havflate",
    "stedsnavn_lag_navn": "n50_stedsnavntekst",
    "veglag_navn": "n50_vegsenterlinje",
    "terrenglag_navn": "n50_terrengpunkt",
    "tinlag_navn": "n50_tin",
    "hoydekurve_lag_navn": "n50_hoydekurve",
    "trig_punkt_lag_navn": "n50_trigonometriskpunkt",
    "tilgjengelige_sider": ["vest", "ost", "sor", "nord"],
    "min_antall_sider": 4,
    "maks_antall_sider": 4,
    "kyst_avstand_fra_bbox": 300.0,
    "hjornemargin": 300.0,
    "trim_forhold_ved_hjorner": 0.33,
    "maksimal_hjorneandel": 0.3,
    "minste_segmentlengde": 200.0,
    "avviksfaktor": 2.0,
    "maks_innoveravvik": 1400.0,
    "maks_forsok_per_side": 25,
    "stedsnavn_seed_offset": 1000,
    "tettsted_min_antall": 2,
    "tettsted_maks_antall": 6,
    "tettsted_areal_per_ekstra": 12000000.0,
    "tettsted_kystandel": 0.4,
    "tettsted_kystavstand": 200.0,
    "tettsted_avstand_min": 2500.0,
    "tettsted_avstand_maks": 6000.0,
    "tettsted_kyst_hoyde": 15.0,
    "tettsted_hoyde_divisor": 20.0,
    "tettsted_innland_min_kystandel": 0.25,
    "tettsted_innland_avstand_jitter": 0.08,
    "tettsted_tangent_delta": 25.0,
    "tettsted_kandidat_antall": 250,
    "tettsted_maks_forsok": 500,
    "tettsted_boks_margin": 100.0,
    "tettsted_navn": [
        "Sjøvik",
        "Fjordnes",
        "Bergstad",
        "Dalheim",
        "Skogstrand",
        "Elverud",
        "Sverrestad",
        "Myggheim",
        "Vingleby",
        "Somlevik",
        "Huttemeitu",
    ],
    "veg_seed_offset": 2000,
    "vegtype": "Riksveg",
    "veg_min_segmentlengde": 150.0,
    "veg_maks_segmentlengde": 400.0,
    "veg_min_bueradius": 150.0,
    "veg_maks_bueradius": 250.0,
    "veg_bue_lengdefaktor_min": 1.0,
    "veg_bue_lengdefaktor_maks": 1.6,
    "veg_rett_sannsynlighet": 0.45,
    "veg_maks_rettstrekk": 1,
    "veg_maks_punkter": 80,
    "veg_maks_forsok": 150,
    "veg_min_avstand": 15.0,
    "veg_korridor_buffer": 25.0,
    "veg_slutt_buffer_segmenter": 3.0,
    "veg_maks_kurvevinkel": 0.3,
    "veg_min_svingvinkel": 0.35,
    "veg_retnings_toleranse": 0.08,
    "veg_bue_punktavstand": 25.0,
    "veg_maks_delstegvinkel": 0.08,
    "veg_sluttbue_maks_forhold": 3.0,
    "veg_hoyde_avviksfaktor": 40.0,
    "terreng_seed_offset": 3000,
    "terreng_niva1_punktavstand": 2000.0,
    "terreng_min_punktavstand": 35.0,
    "terreng_fjellkjerner_antall": 6,
    "terreng_fjell_min_kystavstand": 800.0,
    "terreng_fjell_min_tettstedavstand": 800.0,
    "terreng_fjell_hoyde_min": 100.0,
    "terreng_fjell_hoyde_maks": 320.0,
    "terreng_fjell_spredning_min": 1200.0,
    "terreng_fjell_spredning_maks": 2500.0,
    "terreng_flate_radius": 1000.0,
    "terreng_flate_hoydeavvik_min": 1.0,
    "terreng_flate_hoydeavvik_maks": 10.0,
    "terreng_fortetting_antall": [5, 3, 3, 3],
    "terreng_fortetting_maksavvik": [3.0, 1.0, 0.4, 0.1],
    "hoydekurve_ekvidistanse": 20.0,
    "hoydekurve_min_lengde": 50.0,
    # Antall iterasjoner for glatting av høydekurver (Chaikin)
    "hoydekurve_glatt_iterasjoner": 2,
    # Toleranse for filtrering av terrengpunkter som ikke gir verdi (meter)
    "terreng_filtrering_toleranse": 1.0,
    # Parametre for ÅpentOmråde, DyrketMark og Myr
    "apentomrade_hoyde_terskel": 250.0,
    "dyrketmark_maks_hoydeforskjell": 2.0,
    "myr_maks_hoydeforskjell": 10.0,
    # Andre parametre kan legges til etter behov
}


def _merge_config(standardverdier: Dict[str, Any], overstyringer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Slå sammen standardverdier og brukerparametre."""
    samlet = dict(standardverdier)
    if not overstyringer:
        return samlet

    for nokkel, verdi in overstyringer.items():
        if isinstance(verdi, dict) and isinstance(samlet.get(nokkel), dict):
            samlet[nokkel] = _merge_config(samlet[nokkel], verdi)
        else:
            samlet[nokkel] = verdi
    return samlet


def _klargjor_seed(konfig: Dict[str, Any]) -> int:
    """Finn eller generer seed for én kjøring."""
    seed_verdi = konfig.get("seed")
    if seed_verdi is None:
        return int.from_bytes(os.urandom(8), "big")
    return int(seed_verdi)


def generer_n50_kystkontur(
    output_katalog: str | Path = ".",
    bruker_konfig: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generer og lagre N50-kystkontur som GeoPackage."""
    konfig = _merge_config(STANDARD_KONFIGURASJON, bruker_konfig)
    konfig["seed"] = _klargjor_seed(konfig)
    kystkontur = generer_kystkontur(konfig)
    havflate = generer_havflate(kystkontur, konfig)
    stedsnavntekst = generer_stedsnavntekst(kystkontur, havflate, konfig)
    vegsenterlinje = generer_vegsenterlinje(stedsnavntekst, kystkontur, havflate, konfig)
    terrengpunkt, trig_punkt = generer_terrengpunkt(kystkontur, havflate, stedsnavntekst, vegsenterlinje, konfig)
    tin = generer_tin(terrengpunkt, havflate, konfig)

    tettbebyggelse = generer_tettbebyggelse(stedsnavntekst, konfig)
    # 1. Generer høydekurver uten innsjøkant-filter
    hoydekurve = generer_hoydekurve(terrengpunkt, havflate, konfig)
    # 2. Generer innsjøkant basert på høydekurver
    innsjo_kant = generer_innsjokant(terrengpunkt, havflate, hoydekurve, konfig)
    # 3. Filtrer høydekurver med innsjøkant
    from shapely.ops import unary_union
    innsjo_union = unary_union(innsjo_kant.geometry) if not innsjo_kant.empty else None
    if innsjo_union:
        hoydekurve = hoydekurve[~hoydekurve.geometry.within(innsjo_union)]


    # 4. Generer N50-Myr

    from syntetisk_kart.synthetic_n50_module import generer_myr, generer_apentomrade, generer_dyrketmark
    myr = generer_myr(tin, innsjo_kant, tettbebyggelse, konfig)

    # 5. Generer N50-ÅpentOmråde
    apentomrade = generer_apentomrade(tin, konfig)



    # Klipp alle arealdekke-lag mot landareal (bbox minus havflate)
    from shapely.ops import unary_union
    bbox_polygon = box(*tuple(konfig["bbox"]))
    landareal = bbox_polygon.difference(havflate.geometry.iloc[0])

    def klipp_til_land(gdf):
        if gdf is None or gdf.empty:
            return gdf
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.intersection(landareal)
        gdf = gdf[~gdf.is_empty & gdf.geometry.notnull()]
        return gdf

    innsjo_kant = klipp_til_land(innsjo_kant)
    tettbebyggelse = klipp_til_land(tettbebyggelse)
    myr = klipp_til_land(myr)
    apentomrade = klipp_til_land(apentomrade)

    # Slå sammen eksisterende arealdekke: myr, innsjøkant, tettbebyggelse, åpent område
    arealdekke_lag = []
    for lag in [myr, innsjo_kant, tettbebyggelse, apentomrade]:
        if lag is not None and not lag.empty:
            arealdekke_lag.append(lag)
    if arealdekke_lag:
        eksisterende_arealdekke = GeoDataFrame(pd.concat(arealdekke_lag, ignore_index=True), geometry="geometry", crs=konfig["crs"])
    else:
        eksisterende_arealdekke = GeoDataFrame(columns=["geometry"], geometry="geometry", crs=konfig["crs"])

    # Bruk tidligere dyrketmark-algoritme til å lage ÅpentOmråde
    apentomrade2 = generer_dyrketmark(tin, eksisterende_arealdekke, konfig)
    apentomrade2 = klipp_til_land(apentomrade2)

    # 7. Generer N50-Skog: alt landareal minus union av alle andre arealdekker
    alle_arealdekker = []
    for lag in [kystkontur, innsjo_kant, tettbebyggelse, myr, apentomrade, apentomrade2]:
        if lag is not None and not lag.empty:
            alle_arealdekker.extend(list(lag.geometry))
    if alle_arealdekker:
        ikke_skog = unary_union(alle_arealdekker)
        skog_geom = landareal.difference(ikke_skog)
    else:
        skog_geom = landareal
    # Del opp i polygoner hvis MultiPolygon
    if skog_geom.is_empty:
        skog_gdf = GeoDataFrame(columns=["geometry"], geometry="geometry", crs=konfig["crs"])
    elif skog_geom.geom_type == "Polygon":
        skog_gdf = GeoDataFrame([{"geometry": skog_geom, "objekttype": "N50-Skog"}], geometry="geometry", crs=konfig["crs"])
    elif skog_geom.geom_type == "MultiPolygon":
        skog_gdf = GeoDataFrame([
            {"geometry": p, "objekttype": "N50-Skog"} for p in skog_geom.geoms if not p.is_empty and p.is_valid
        ], geometry="geometry", crs=konfig["crs"])
    else:
        skog_gdf = GeoDataFrame(columns=["geometry"], geometry="geometry", crs=konfig["crs"])

    output_sti = Path(output_katalog)
    output_sti.mkdir(parents=True, exist_ok=True)
    filsti = output_sti / str(konfig["n50_filnavn"])
    if filsti.exists():
        filsti.unlink()

    kystkontur.to_file(filsti, layer=str(konfig["kystlag_navn"]), driver="GPKG")
    havflate.to_file(filsti, layer=str(konfig["havlag_navn"]), driver="GPKG", mode="a")
    stedsnavntekst.to_file(filsti, layer=str(konfig["stedsnavn_lag_navn"]), driver="GPKG", mode="a")
    vegsenterlinje.to_file(filsti, layer=str(konfig["veglag_navn"]), driver="GPKG", mode="a")
    terrengpunkt.to_file(filsti, layer=str(konfig["terrenglag_navn"]), driver="GPKG", mode="a")
    tin.to_file(filsti, layer=str(konfig["tinlag_navn"]), driver="GPKG", mode="a")
    hoydekurve.to_file(filsti, layer=str(konfig["hoydekurve_lag_navn"]), driver="GPKG", mode="a")
    trig_punkt.to_file(filsti, layer=str(konfig["trig_punkt_lag_navn"]), driver="GPKG", mode="a")
    tettbebyggelse.to_file(filsti, layer="n50_tettbebyggelse", driver="GPKG", mode="a")
    innsjo_kant.to_file(filsti, layer="n50_innsjokant", driver="GPKG", mode="a")
    myr.to_file(filsti, layer="n50_myr", driver="GPKG", mode="a")
    apentomrade.to_file(filsti, layer="n50_apentomrade", driver="GPKG", mode="a")
    apentomrade2.to_file(filsti, layer="n50_apentomrade2", driver="GPKG", mode="a")
    skog_gdf.to_file(filsti, layer="n50_skog", driver="GPKG", mode="a")
    return {
        "kystkontur": kystkontur,
        "havflate": havflate,
        "stedsnavntekst": stedsnavntekst,
        "vegsenterlinje": vegsenterlinje,
        "terrengpunkt": terrengpunkt,
        "tin": tin,
        "hoydekurve": hoydekurve,
        "trigonometriskpunkt": trig_punkt,
        "tettbebyggelse": tettbebyggelse,
        "innsjokant": innsjo_kant,
        "myr": myr,
        "apentomrade": apentomrade,
        "apentomrade2": apentomrade2,
        "skog": skog_gdf,
        "filsti": filsti,
        "seed": konfig["seed"],
    }


def main() -> None:
    """Kjør generering av første N50-lag fra kommandolinjen."""
    parser = argparse.ArgumentParser(description="Generer syntetisk N50-kystkontur")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", default=".")
    args = parser.parse_args()

    # Sett fast seed for reproduserbarhet
    fast_seed = 12345
    bruker_konfig = {"seed": fast_seed}
    print("Starter full generering og lagring av N50.gpkg...")
    result = generer_n50_kystkontur(output_katalog=args.output, bruker_konfig=bruker_konfig)
    print(f"Antall myr: {len(result['myr'])}")
    print(f"Antall innsjøkant: {len(result['innsjokant'])}")
    print(f"N50.gpkg skrevet til: {result['filsti']}")
    print(f"Antall terrengpunkt: {len(result['terrengpunkt'])}")


if __name__ == "__main__":
    main()
