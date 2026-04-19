import math
from pathlib import Path

import numpy as np
from shapely.geometry import Point

from synthetic_map import generer_n50_kystkontur
from syntetisk_kart.synthetic_n50_module import _beregn_buesegmentlengde, _del_segment_rekursivt


TEST_BBOX = (500000.0, 7030000.0, 504000.0, 7034000.0)


def test_generer_n50_kystkontur_gir_gyldige_linjer(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 42,
        },
    )

    kyst = resultat["kystkontur"]

    assert len(kyst) == 1
    assert (tmp_path / "N50.gpkg").exists()
    assert set(kyst.geom_type) == {"LineString"}
    assert kyst.is_valid.all()
    assert kyst.length.min() > 0
    assert kyst.iloc[0]["sider"] == "vest,nord,ost,sor"
    assert kyst.geometry.iloc[0].is_ring


def test_generer_havflate_blir_lukket_polygon(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 42,
            "valgte_sider": ["vest", "nord"],
        },
    )

    havflate = resultat["havflate"]

    assert len(havflate) == 1
    assert set(havflate.geom_type).issubset({"Polygon", "MultiPolygon"})
    assert havflate.is_valid.all()
    assert havflate.area.iloc[0] > 0


def test_generer_n50_stedsnavntekst_gir_kyst_og_innlandspunkt(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 7,
            "valgte_sider": ["vest", "nord", "ost"],
        },
    )

    stedsnavn = resultat["stedsnavntekst"]

    assert len(stedsnavn) >= 2
    assert set(stedsnavn.geom_type) == {"Point"}
    assert stedsnavn.is_valid.all()
    assert (stedsnavn["hoyde"] == 15.0).any()
    assert (stedsnavn["hoyde"] > 15.0).any()
    assert (stedsnavn["navneobjekttype"] == "By").all()


def test_generer_n50_kystkontur_med_flere_sider_blir_en_sammenhengende_linje(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 7,
            "valgte_sider": ["vest", "nord", "ost"],
        },
    )

    kyst = resultat["kystkontur"]

    assert len(kyst) == 1
    assert kyst.geometry.iloc[0].is_simple


def test_innlandstettsteder_far_variert_avstand_til_kyst(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 7,
            "valgte_sider": ["vest", "nord", "ost"],
        },
    )

    innland = resultat["stedsnavntekst"].query("stedstype == 'innland'")
    kystlinje = resultat["kystkontur"].geometry.iloc[0]
    avstander = innland.geometry.apply(lambda geometri: Point(geometri.x, geometri.y).distance(kystlinje))

    assert len(avstander) >= 2
    assert avstander.max() - avstander.min() > 1500.0


def test_kystlinje_far_hjornepunkt_inntil_tretti_prosent_inn(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 11,
            "valgte_sider": ["vest"],
        },
    )

    geometri = resultat["kystkontur"].geometry.iloc[0]
    start_x, start_y = geometri.coords[0]
    slutt_x, slutt_y = geometri.coords[-1]

    assert 500300.0 <= start_x <= 501320.0
    assert 500300.0 <= slutt_x <= 501320.0
    assert 7030300.0 <= start_y <= 7031320.0
    assert 7032680.0 <= slutt_y <= 7033700.0
    assert (start_x, start_y) != (500300.0, 7030300.0)
    assert (slutt_x, slutt_y) != (500300.0, 7033700.0)


def test_generer_n50_vegsenterlinje_gir_gyldige_3d_linjer(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 9,
            "valgte_sider": ["vest", "nord", "ost"],
        },
    )

    veger = resultat["vegsenterlinje"]
    kystlinje = resultat["kystkontur"].geometry.iloc[0]
    tettsteder = [Point(geometri.x, geometri.y) for geometri in resultat["stedsnavntekst"].geometry]

    assert len(veger) >= 1
    assert set(veger.geom_type) == {"LineString"}
    assert veger.is_valid.all()
    assert all(geometri.has_z for geometri in veger.geometry)
    assert all(not geometri.crosses(kystlinje) for geometri in veger.geometry)

    for geometri in veger.geometry:
        startpunkt = Point(geometri.coords[0][0], geometri.coords[0][1])
        sluttpunkt = Point(geometri.coords[-1][0], geometri.coords[-1][1])
        assert any(startpunkt.distance(tettsted) < 1e-6 for tettsted in tettsteder)
        assert any(sluttpunkt.distance(tettsted) < 1e-6 for tettsted in tettsteder)


def test_veger_far_glatte_buer_med_tangentkontinuitet(tmp_path: Path) -> None:
    resultat = generer_n50_kystkontur(
        output_katalog=tmp_path,
        bruker_konfig={
            "bbox": TEST_BBOX,
            "seed": 9,
            "valgte_sider": ["vest", "nord", "ost"],
        },
    )

    veger = resultat["vegsenterlinje"]
    antall_punkter = [len(list(geometri.coords)) for geometri in veger.geometry]
    assert max(antall_punkter) >= 6

    for geometri in veger.geometry:
        koordinater = list(geometri.coords)
        retninger = []
        segmentlengder = []
        for start, slutt in zip(koordinater, koordinater[1:]):
            dx = slutt[0] - start[0]
            dy = slutt[1] - start[1]
            retninger.append(math.atan2(dy, dx))
            segmentlengder.append(math.dist((start[0], start[1]), (slutt[0], slutt[1])))

        vinkelhopp = []
        for forrige, neste in zip(retninger, retninger[1:]):
            differanse = (neste - forrige + math.pi) % (2 * math.pi) - math.pi
            vinkelhopp.append(abs(differanse))

        assert max(vinkelhopp, default=0.0) <= 0.18
        assert max(segmentlengder, default=0.0) <= 410.0
        assert max(vinkelhopp[-3:], default=0.0) <= 0.18
        assert max(segmentlengder[-3:], default=0.0) <= 80.0
        assert sum(segmentlengder[-6:]) <= 1200.0


def test_generer_n50_kystkontur_blir_tilfeldig_uten_seed(tmp_path: Path) -> None:
    resultat_en = generer_n50_kystkontur(
        output_katalog=tmp_path / "en",
        bruker_konfig={"bbox": TEST_BBOX, "n50_filnavn": "N50_en.gpkg"},
    )
    resultat_to = generer_n50_kystkontur(
        output_katalog=tmp_path / "to",
        bruker_konfig={"bbox": TEST_BBOX, "n50_filnavn": "N50_to.gpkg"},
    )

    wkt_en = resultat_en["kystkontur"].geometry.to_wkt().tolist()
    wkt_to = resultat_to["kystkontur"].geometry.to_wkt().tolist()

    assert wkt_en != wkt_to


def test_buesegmentlengde_beregnes_fra_radius_og_faktor() -> None:
    konfig = {
        "veg_bue_lengdefaktor_min": 1.5,
        "veg_bue_lengdefaktor_maks": 1.5,
    }

    segmentlengde = _beregn_buesegmentlengde(
        radius=200.0,
        konfig=konfig,
        tilfeldig=np.random.default_rng(123),
    )

    assert segmentlengde == 300.0


def test_rekursiv_deling_kan_forskyve_begge_veier() -> None:
    punkter = _del_segment_rekursivt(
        startpunkt=(0.0, 0.0),
        sluttpunkt=(100.0, 0.0),
        normal=(0.0, 1.0),
        tilfeldig=np.random.default_rng(123),
        minste_segmentlengde=10.0,
        avviksfaktor=3.0,
        maks_innoveravvik=50.0,
        maks_utoveravvik=50.0,
    )

    y_verdier = [punkt[1] for punkt in punkter[1:-1]]

    assert any(verdi > 0 for verdi in y_verdier)
    assert any(verdi < 0 for verdi in y_verdier)
