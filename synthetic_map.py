"""Orkestrator for generering av syntetisk kart."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, Optional

from syntetisk_kart.synthetic_n50_module import generer_havflate, generer_kystkontur

STANDARD_KONFIGURASJON: Dict[str, Any] = {
    "bbox": (500000.0, 7030000.0, 510000.0, 7040000.0),
    "crs": "EPSG:25833",
    "seed": None,
    "n50_filnavn": "N50.gpkg",
    "kystlag_navn": "n50_kystkontur",
    "havlag_navn": "n50_havflate",
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

    output_sti = Path(output_katalog)
    output_sti.mkdir(parents=True, exist_ok=True)
    filsti = output_sti / str(konfig["n50_filnavn"])
    if filsti.exists():
        filsti.unlink()

    kystkontur.to_file(filsti, layer=str(konfig["kystlag_navn"]), driver="GPKG")
    havflate.to_file(filsti, layer=str(konfig["havlag_navn"]), driver="GPKG", mode="a")
    return {"kystkontur": kystkontur, "havflate": havflate, "filsti": filsti, "seed": konfig["seed"]}


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
    print(f"Genererte {antall_linjer} kystlinjer i {resultat['filsti']} med seed {resultat['seed']}")


if __name__ == "__main__":
    main()
