from scstatus.locations import Places
from scstatus.logparse import Session, parse_line, records
from scstatus.timeline import shard_label, ship_name, steps_from, timeline

LOG = """<2026-10-29T22:10:00.000Z> [Notice] <Join PU> address[1.2.3.4] port[64300] shard[pub_apse2a_12881860_020] locationId[0]
<2026-10-29T22:13:00.000Z> [Notice] <Context Establisher Done> establisher="CReplicationModel" runningTime=95.4 map="megamap" gamerules="SC_Default" sessionId="x"
<2026-10-29T22:14:08.740Z> [Notice] <SHUDEvent_OnNotification> Added notification "Entering Armistice Zone - Combat Prohibited: " [0] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]
<2026-10-29T22:14:28.760Z> [Notice] <RequestLocationInventory> Player[Test_Pilot] requested inventory for Location[RR_CRU_L4] [Team_CoreGameplayFeatures][Inventory]
<2026-10-29T22:14:40.000Z> [Notice] <RequestLocationInventory> Player[Test_Pilot] requested inventory for Location[RR_CRU_L4] [Team_CoreGameplayFeatures][Inventory]
<2026-10-29T22:15:00.000Z> [Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> SetVehicleSpawningInformations - VehicleEntityId: [123], LandingArea: Test_Pilot's
<2026-10-29T22:15:02.000Z> [Notice] <ATC_Reset_VehiclesBeingStoredCleared> ATC 'ORIG_m80_ShipATCDataManager_9001' [9001] clearing 0 entries from vehicles-being-stored list on Reset [Team_MissionFeatures][ATC]
<2026-10-29T22:16:00.000Z> [Notice] <ATC_Reset_VehiclesBeingStoredCleared> ATC 'DRAK_Cutlass_Black_ShipATCDataManager_9002' [9002] clearing 0 entries from vehicles-being-stored list on Reset [Team_MissionFeatures][ATC]
<2026-10-29T22:19:56.541Z> [Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][16840] | NOT AUTH | ORIG_m80_907178497025[907178497025]|CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected point rs_ext_pyro3_leo as their destination, routing locally [Team_CGP4][QuantumTravel]
<2026-10-29T22:21:00.000Z> [Notice] <Quantum Drive Arrived - Arrived at Final Destination> [ItemNavigation][CL][16840] | NOT AUTH | MISC_Freelancer_PU_AI_CRIM_908940232830[908940232830]|CSCItemNavigation::OnQuantumDriveArrived|Quantum Drive has arrived at final destination [Team_CGP4][QuantumTravel]
<2026-10-29T22:21:13.510Z> [Notice] <Quantum Drive Arrived - Arrived at Final Destination> [ItemNavigation][CL][16840] | NOT AUTH | ORIG_m80_907178497025[907178497025]|CSCItemNavigation::OnQuantumDriveArrived|Quantum Drive has arrived at final destination [Team_CGP4][QuantumTravel]
<2026-10-29T22:25:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Very Hungry: " [5] to queue. New queue size: 1, MissionId: [11111111-2222-3333-4444-555555555555], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]
"""


def _session():
    s = Session("Game.log")
    for raw in records(LOG.splitlines(True)):
        s.add(parse_line(raw))
    return s


def test_travel_places_and_ships_are_parsed():
    s = _session()
    kinds = [e["kind"] for e in s.travel]
    assert kinds == ["armistice", "location", "ship_retrieved", "qt_target", "qt_arrived"]   # repeat place dropped
    assert s.travel[2]["ship"] == "ORIG_m80"            # named by the ATC line just after, not the later one
    assert s.travel[3]["dest"] == "rs_ext_pyro3_leo" and s.travel[3]["ship"] == "ORIG_m80"
    assert s.travel[4]["dest"] == "rs_ext_pyro3_leo"     # the AI ship's arrival was ignored


def test_timeline_reads_plainly_and_never_names_the_player():
    p = Places()
    p.names = {"rr_cru_l4": "CRU-L4 Shallow Fields Station", "pyro3": "Bloom"}
    items = timeline(_session(), p)
    texts = [i["text"] for i in items]
    assert texts == ["Joined shard AU-20", "Loaded into the game (95 s)", "Entered an armistice zone",
                     "At CRU-L4 Shallow Fields Station", "Retrieved ORIG M80 from the hangar", "Set course to Bloom",
                     "Arrived near Bloom", "Accepted contract \"Very Hungry\""]
    assert {i["group"] for i in items} == {"connection", "place", "ship", "travel", "contract"}
    assert not any("Test_Pilot" in t for t in texts)
    assert items[3]["area"] == "crusader" and items[3]["code"] == "RR_CRU_L4"


def test_steps_built_from_the_timeline():
    p = Places()
    p.names = {"rr_cru_l4": "CRU-L4 Shallow Fields Station", "pyro3": "Bloom"}
    steps = steps_from(timeline(_session(), p), "The objective doesn't update.")
    assert steps == ["Join shard AU-20.", "Be at CRU-L4 Shallow Fields Station.", "Retrieve ORIG M80 from the hangar.",
                     "Set a quantum course to Bloom and arrive.", "Accept the contract \"Very Hungry\".",
                     "The objective doesn't update."]


def test_issue_council_steps_use_the_timeline_and_fall_back_without_one():
    from scstatus.report import steps_for
    p = Places()
    p.names = {"rr_cru_l4": "CRU-L4 Shallow Fields Station", "pyro3": "Bloom"}
    s = _session()
    f = {"title": "\"Very Hungry\": deliveries never counted", "area": "Contracts", "fields": {},
         "first_ts": s.end + 60, "last_ts": s.end + 120}
    steps = steps_for(f, s, p)
    assert steps[0] == "Join shard AU-20." and steps[-1] == "The objective does not progress."
    assert "Accept the contract \"Very Hungry\"." in steps
    other = {"title": "Ship spawned inside the pad", "area": "Ships", "fields": {}, "first_ts": s.end + 60}
    assert steps_for(other, s, p)[-1] == "Ship spawned inside the pad."
    assert steps_for(other)[0] == "(Describe what you were doing.)"        # no session: the template


def test_names():
    assert shard_label("pub_euw1b_12881860_410") == "EU-410" and shard_label("odd") == "odd"
    assert ship_name("RSI_Constellation_Mk5_Centaurus") == "RSI Constellation Mk5 Centaurus"
