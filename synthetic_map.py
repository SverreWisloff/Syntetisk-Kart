"""Orkestrator for generering av syntetisk kart."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, Optional

from syntetisk_kart.synthetic_n50_module import (
    generer_havflate,
    generer_kystkontur,
    generer_stedsnavntekst,
    generer_vegsenterlinje,
)

STANDARD_KONFIGURASJON: Dict[str, Any] = {
    "bbox": (497929.0, 7027929.0, 512071.0, 7042071.0),
    "crs": "EPSG:25833",
    "seed": None,
    "n50_filnavn": "N50.gpkg",
    "kystlag_navn": "n50_kystkontur",
    "havlag_navn": "n50_havflate",
    "stedsnavn_lag_navn": "n50_stedsnavntekst",
    "veglag_navn": "n50_vegsenterlinje",
    "tilgjengelige_sider": ["vest", "ost", "sor", "nord"],
    "min_antall_sider": 1,
    "maks_antall_sider": 4,
    "kyst_avstand_fra_bbox": 300.0,
    "hjornemargin": 300.0,
    "trim_forhold_ved_hjorner": 0.33,
    "maksimal_hjorneandel": 0.3,
    "minste_segmentlengde": 1.0,
    "avviksfaktor": 3.0,
    "maks_innoveravvik": 1000.0,
    "maks_forsok_per_side": 25,
    "stedsnavn_seed_offset": 1000,
    "tettsted_min_antall": 2,
    "tettsted_maks_antall": 6,
    "tettsted_areal_per_ekstra": 12000000.0,
    "tettsted_kystandel": 0.4,
    "tettsted_kystavstand": 200.0,
    "tettsted_avstand_min": 2000.0,
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
    ],
    "veg_seed_offset": 2000,
    "vegtype": "Riksveg",
    "veg_min_segmentlengde": 250.0,
    "veg_maks_segmentlengde": 700.0,
    "veg_min_bueradius": 150.0,
    "veg_maks_bueradius": 250.0,
    "veg_rett_sannsynlighet": 0.45,
    "veg_maks_rettstrekk": 2,
    "veg_maks_punkter": 24,
    "veg_maks_forsok": 150,
    "veg_min_avstand": 15.0,
    "veg_korridor_buffer": 25.0,
    "veg_slutt_buffer_segmenter": 3.0,
    "veg_maks_kurvevinkel": 0.5,
    "veg_hoyde_avviksfaktor": 40.0,
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

    output_sti = Path(output_katalog)
    output_sti.mkdir(parents=True, exist_ok=True)
    filsti = output_sti / str(konfig["n50_filnavn"])
    if filsti.exists():
        filsti.unlink()

    kystkontur.to_file(filsti, layer=str(konfig["kystlag_navn"]), driver="GPKG")
    havflate.to_file(filsti, layer=str(konfig["havlag_navn"]), driver="GPKG", mode="a")
    stedsnavntekst.to_file(filsti, layer=str(konfig["stedsnavn_lag_navn"]), driver="GPKG", mode="a")
    vegsenterlinje.to_file(filsti, layer=str(konfig["veglag_navn"]), driver="GPKG", mode="a")
    return {
        "kystkontur": kystkontur,
        "havflate": havflate,
        "stedsnavntekst": stedsnavntekst,
        "vegsenterlinje": vegsenterlinje,
        "filsti": filsti,
        "seed": konfig["seed"],
    }


def main() -> None:
    """Kjør generering av første N50-lag fra kommandolinjen."""
    parser = argparse.ArgumentParser(description="Generer syntetisk N50-kystkontur")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", default=".")
    args = parser.parse_args()

    resultat = generer_n50_kystkontur(
        output_katalog=args.output,
        bruker_konfig={"seed": args.seed},
    )
    antall_linjer = len(resultat["kystkontur"])
    antall_veger = len(resultat["vegsenterlinje"])
    print(
        f"Genererte {antall_linjer} kystlinjer og {antall_veger} veger i {resultat['filsti']} med seed {resultat['seed']}"
    )


if __name__ == "__main__":
    main()
