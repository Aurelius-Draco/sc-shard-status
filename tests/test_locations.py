from scstatus.locations import Places, area_of


def test_location_codes_to_areas():
    assert area_of("RR_P3_LEO") == "pyro3" and area_of("RR_P3_LE0") == "pyro3"
    assert area_of("RR_CRU_L4") == "crusader" and area_of("Stanton2a") == "crusader"
    assert area_of("TheCollectorAsteroid_Stanton4") == "microtech"
    assert area_of("PyroSolarSystem") == "pyro-space"
    assert area_of("RR_JP_StantonPyro") == "gate-stanton-pyro"
    assert area_of("AsteroidCluster_2Bases_Pyro_Encounter_RegionD_001") == "pyro-space"
    assert area_of("vINVALID_LOCATION_ID") is None and area_of("") is None and area_of("Lorville") is None


def test_names_from_the_game_text_win(tmp_path):
    ini = tmp_path / "Data" / "Localization" / "english"
    ini.mkdir(parents=True)
    (ini / "global.ini").write_text("Pyro3=Bloom\nRR_CRU_L4=CRU-L4 Shallow Fields Station\nRR_CRU_L4_desc=long text\n"
                                    "Stanton2=Crusader\nitem_name_x=Something\n", encoding="utf-8")
    p = Places(tmp_path)
    assert p.where("RR_P3_LEO") == {"system": "pyro", "area": "pyro3", "area_name": "Bloom"}
    assert p.place("RR_CRU_L4") == "CRU-L4 Shallow Fields Station"
    assert p.place("RR_P3_LEO") == "station near Bloom"
    assert "rr_cru_l4_desc" not in p.names and "item_name_x" not in p.names


def test_overlay_misreads_and_readable_places():
    from scstatus.locations import Places, area_of, clean_code
    assert clean_code("Stantoni") == "Stanton1" and clean_code("Stanton3_Areal8") == "Stanton3_Area18"
    assert area_of("StantonI_WeepingCove") == "hurston" and area_of("vINVALID_LOCATION_ID") is None
    p = Places()
    p.names = {"stanton2b": "Daymar"}
    assert p.place("Stantonl_CuttersRig") == "Cutters Rig, Hurston"
    assert p.place("Stanton2b_ShubinMining_SCD1") == "Shubin Mining SCD1, Daymar"
    assert p.place("Stanton3b_ASD_Delve_Facility_004") == "ASD Delve Facility 004, a moon of ArcCorp"
