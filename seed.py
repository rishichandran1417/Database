import os
import sys
import logging
from datetime import date, datetime, timedelta, timezone
import random

from database import get_db_connection, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ksrtc_seed")

DEPOT_NAME = "KSRTC Central Stores"


# 1. Realistic KSRTC Spare Parts Dataset
PARTS_DATA = [
    {
        "sku": "ENG-AL-001",
        "name": "Engine Oil Filter Spin-On",
        "category": "Engine",
        "description": "Full-flow spin-on lube oil filter for Ashok Leyland 'H' Series 6-Cylinder BS-IV/BS-VI bus engines.",
        "unit_cost": 850.00,
        "criticality": "Critical",
        "stock": 28,
        "safety_stock": 15,
        "reorder_point": 30,
        "max_stock": 80,
    },
    {
        "sku": "ENG-AL-002",
        "name": "Fuel Filter Element (Water Separator)",
        "category": "Engine",
        "description": "Secondary fuel filter element with water separator bowl for common rail diesel fuel injection.",
        "unit_cost": 1450.00,
        "criticality": "Critical",
        "stock": 14,
        "safety_stock": 20,
        "reorder_point": 35,
        "max_stock": 90,
    },
    {
        "sku": "ENG-AL-003",
        "name": "Turbocharger Cartridge Assembly (CHRA)",
        "category": "Engine",
        "description": "Wastegated turbocharger core assembly for Leyland Hino 180HP diesel bus engines.",
        "unit_cost": 24500.00,
        "criticality": "Critical",
        "stock": 3,
        "safety_stock": 2,
        "reorder_point": 5,
        "max_stock": 12,
    },
    {
        "sku": "ENG-AL-004",
        "name": "Radiator Coolant Hose Kit EPDM",
        "category": "Cooling System",
        "description": "Reinforced high-temperature upper and lower silicone/EPDM radiator hose set with constant-torque clamps.",
        "unit_cost": 2200.00,
        "criticality": "Essential",
        "stock": 18,
        "safety_stock": 10,
        "reorder_point": 25,
        "max_stock": 60,
    },
    {
        "sku": "ENG-AL-005",
        "name": "Poly-V Serpentine Alternator Belt 8PK",
        "category": "Engine",
        "description": "EPDM multi-ribbed alternator & water pump drive belt resistant to heat and oil.",
        "unit_cost": 1800.00,
        "criticality": "Essential",
        "stock": 42,
        "safety_stock": 15,
        "reorder_point": 30,
        "max_stock": 75,
    },
    {
        "sku": "BRK-AL-001",
        "name": "Brake Lining Set (Front & Rear Axle)",
        "category": "Braking System",
        "description": "Non-asbestos heavy commercial vehicle brake linings with rivets for 410mm diameter drum assemblies.",
        "unit_cost": 4500.00,
        "criticality": "Critical",
        "stock": 12,
        "safety_stock": 25,
        "reorder_point": 45,
        "max_stock": 120,
    },
    {
        "sku": "BRK-AL-002",
        "name": "S-Cam Brake Drum 410mm Heavy Commercial",
        "category": "Braking System",
        "description": "High-tensile gray cast iron brake drum balanced for front and drive rear axles on Leyland Viking buses.",
        "unit_cost": 12500.00,
        "criticality": "Critical",
        "stock": 8,
        "safety_stock": 8,
        "reorder_point": 16,
        "max_stock": 40,
    },
    {
        "sku": "BRK-AL-003",
        "name": "Air Brake Diaphragm Type 24 Booster",
        "category": "Braking System",
        "description": "Heavy-duty neoprene diaphragm for Type 24/30 spring brake actuators on bus pneumatic brake system.",
        "unit_cost": 750.00,
        "criticality": "Essential",
        "stock": 55,
        "safety_stock": 20,
        "reorder_point": 40,
        "max_stock": 100,
    },
    {
        "sku": "BRK-AL-004",
        "name": "Automatic Slack Adjuster Assembly",
        "category": "Braking System",
        "description": "Self-adjusting brake camshaft lever maintaining constant lining-to-drum running clearance.",
        "unit_cost": 3800.00,
        "criticality": "Essential",
        "stock": 16,
        "safety_stock": 10,
        "reorder_point": 22,
        "max_stock": 50,
    },
    {
        "sku": "TRN-AL-001",
        "name": "Clutch Plate 380mm Ceramic Button",
        "category": "Transmission",
        "description": "Heavy duty 380mm cerametallic driven plate with torsional damper springs for city bus stop-and-go duty.",
        "unit_cost": 14500.00,
        "criticality": "Critical",
        "stock": 5,
        "safety_stock": 8,
        "reorder_point": 18,
        "max_stock": 45,
    },
    {
        "sku": "TRN-AL-002",
        "name": "Clutch Pressure Plate Heavy Commercial",
        "category": "Transmission",
        "description": "Diaphragm spring clutch cover assembly balanced for Ashok Leyland 6-speed synchromesh transmission.",
        "unit_cost": 12500.00,
        "criticality": "Critical",
        "stock": 6,
        "safety_stock": 6,
        "reorder_point": 14,
        "max_stock": 35,
    },
    {
        "sku": "TRN-AL-003",
        "name": "Gearbox Synchronizer Ring 3rd/4th",
        "category": "Transmission",
        "description": "Molybdenum-coated brass synchronizer blocker ring for smooth gear engagement on overdrive gearboxes.",
        "unit_cost": 2100.00,
        "criticality": "Desirable",
        "stock": 22,
        "safety_stock": 10,
        "reorder_point": 20,
        "max_stock": 50,
    },
    {
        "sku": "SUS-AL-001",
        "name": "Leaf Spring Assembly (Front Main Plate)",
        "category": "Suspension",
        "description": "Parabolic multi-leaf spring main plate with military wrapped eyes and rubberized silent-bloc bushes.",
        "unit_cost": 9200.00,
        "criticality": "Critical",
        "stock": 7,
        "safety_stock": 10,
        "reorder_point": 20,
        "max_stock": 50,
    },
    {
        "sku": "SUS-AL-002",
        "name": "Heavy Duty Telescopic Shock Absorber",
        "category": "Suspension",
        "description": "Hydraulic twin-tube telescopic damper built specifically for passenger comfort on Kerala state highways.",
        "unit_cost": 7800.00,
        "criticality": "Essential",
        "stock": 19,
        "safety_stock": 12,
        "reorder_point": 24,
        "max_stock": 60,
    },
    {
        "sku": "STG-AL-001",
        "name": "Front Axle King Pin Unit Set",
        "category": "Steering",
        "description": "Case-hardened steel king pin with bronze thrust washers, roller bearings, and shims for front steer axle.",
        "unit_cost": 5400.00,
        "criticality": "Critical",
        "stock": 9,
        "safety_stock": 8,
        "reorder_point": 18,
        "max_stock": 40,
    },
    {
        "sku": "STG-AL-002",
        "name": "Steering Tie Rod End (Left/Right Hand)",
        "category": "Steering",
        "description": "Forged ball joint tie rod end for drag link assembly with dust boot cover and castellated nut.",
        "unit_cost": 4200.00,
        "criticality": "Critical",
        "stock": 15,
        "safety_stock": 10,
        "reorder_point": 22,
        "max_stock": 55,
    },
    {
        "sku": "ELE-AL-001",
        "name": "Alternator 24V 55A Heavy Duty Bus Spec",
        "category": "Electrical",
        "description": "Internal regulator brushless alternator for heavy transit bus battery charging and interior LED lighting.",
        "unit_cost": 28500.00,
        "criticality": "Critical",
        "stock": 4,
        "safety_stock": 4,
        "reorder_point": 8,
        "max_stock": 20,
    },
    {
        "sku": "ELE-AL-002",
        "name": "Starter Motor 24V 4.5kW Pre-Engaged",
        "category": "Electrical",
        "description": "Reduction-gear high-torque starter motor assembly with integrated solenoid for diesel compression engines.",
        "unit_cost": 24000.00,
        "criticality": "Critical",
        "stock": 3,
        "safety_stock": 3,
        "reorder_point": 7,
        "max_stock": 18,
    },
    {
        "sku": "ELE-AL-003",
        "name": "Heavy Commercial Bus Battery 12V 180Ah",
        "category": "Electrical",
        "description": "Deep-cycle vibration-resistant tubular flooded bus battery (installed in 24V pairs).",
        "unit_cost": 18500.00,
        "criticality": "Critical",
        "stock": 8,
        "safety_stock": 10,
        "reorder_point": 20,
        "max_stock": 45,
    },
    {
        "sku": "TYR-AL-001",
        "name": "All-Steel Radial Bus Tyre 295/80R22.5",
        "category": "Tyres & Wheels",
        "description": "Tubeless all-position radial commercial bus tyre optimized for wet grip and low rolling resistance.",
        "unit_cost": 32500.00,
        "criticality": "Critical",
        "stock": 14,
        "safety_stock": 15,
        "reorder_point": 30,
        "max_stock": 80,
    },
    {
        "sku": "TYR-AL-002",
        "name": "High-Mileage Retread Bus Tyre 10.00-20",
        "category": "Tyres & Wheels",
        "description": "Hot-cured high-mileage lug tread tyre on inspected nylon casing for rear drive axle bus service.",
        "unit_cost": 14200.00,
        "criticality": "Essential",
        "stock": 25,
        "safety_stock": 20,
        "reorder_point": 40,
        "max_stock": 90,
    },
    {
        "sku": "TYR-AL-003",
        "name": "Heavy Duty Commercial Inner Tube 10.00-20",
        "category": "Tyres & Wheels",
        "description": "Butyl rubber heavy-gauge inner tube with long-bend TR-78A valve for 20-inch split rim wheels.",
        "unit_cost": 1800.00,
        "criticality": "Essential",
        "stock": 35,
        "safety_stock": 15,
        "reorder_point": 35,
        "max_stock": 85,
    },
    {
        "sku": "LUB-AL-001",
        "name": "Engine Oil 15W-40 CI-4 Plus (20L Bucket)",
        "category": "Lubricants & Fluids",
        "description": "Premium multi-grade heavy duty diesel engine lubricating oil providing extended drain intervals.",
        "unit_cost": 5200.00,
        "criticality": "Critical",
        "stock": 30,
        "safety_stock": 20,
        "reorder_point": 45,
        "max_stock": 120,
    },
    {
        "sku": "LUB-AL-002",
        "name": "Gear Oil 80W-90 GL-5 (20L Bucket)",
        "category": "Lubricants & Fluids",
        "description": "Extreme pressure hypoid gear lubricant for heavy commercial vehicle manual transmissions and differentials.",
        "unit_cost": 4800.00,
        "criticality": "Essential",
        "stock": 22,
        "safety_stock": 15,
        "reorder_point": 30,
        "max_stock": 70,
    },
    {
        "sku": "LUB-AL-003",
        "name": "Heavy Duty Glycol Coolant (20L Can)",
        "category": "Lubricants & Fluids",
        "description": "Pre-diluted 50/50 ethylene glycol anti-freeze anti-corrosion long-life radiator coolant for tropical climate.",
        "unit_cost": 3600.00,
        "criticality": "Essential",
        "stock": 26,
        "safety_stock": 18,
        "reorder_point": 36,
        "max_stock": 80,
    },
]

# 2. Authentic KSRTC Vendors & Suppliers
SUPPLIERS_DATA = [
    {
        "supplier_code": "SUP-TVS-01",
        "supplier_name": "TVS & Sons Private Limited",
        "contact_person": "M. S. Narayanan",
        "email": "spares.tvm@tvs.in",
        "phone": "+91 471 2471201",
        "category": "Original Equipment Spares",
        "lead_time_days": 5,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-BRL-02",
        "supplier_name": "Brakes India Private Limited",
        "contact_person": "K. V. Ramachandran",
        "email": "commercial.kl@brakesindia.com",
        "phone": "+91 484 2801452",
        "category": "Braking & Safety",
        "lead_time_days": 7,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-LUC-03",
        "supplier_name": "Lucas-TVS Limited",
        "contact_person": "Biju Abraham",
        "email": "aftermarket.tvm@lucastvs.com",
        "phone": "+91 471 2338910",
        "category": "Auto Electricals",
        "lead_time_days": 6,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-JAI-04",
        "supplier_name": "Jamna Auto Industries Limited",
        "contact_person": "S. Gurpreet Singh",
        "email": "fleet.sales@jaispring.com",
        "phone": "+91 1732 251811",
        "category": "Suspension & Springs",
        "lead_time_days": 10,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-MRF-05",
        "supplier_name": "MRF Limited - Heavy Commercial Division",
        "contact_person": "G. S. Pillai",
        "email": "ksrtc.fleet@mrfmail.com",
        "phone": "+91 484 2356781",
        "category": "Tyres & Retreads",
        "lead_time_days": 4,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-IOC-06",
        "supplier_name": "Indian Oil Corporation Limited (SERVO)",
        "contact_person": "R. Anand Kumar",
        "email": "servo.kerala@indianoil.in",
        "phone": "+91 484 2422300",
        "category": "Lubricants & Petroleum",
        "lead_time_days": 3,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-EXD-07",
        "supplier_name": "Exide Industries Limited",
        "contact_person": "Pradeep Menon",
        "email": "oem.south@exide.co.in",
        "phone": "+91 471 2321455",
        "category": "Storage Batteries",
        "lead_time_days": 5,
        "status": "Active",
    },
    {
        "supplier_code": "SUP-CWS-08",
        "supplier_name": "KSRTC Central Workshop, Pappanamcode",
        "contact_person": "Works Manager (Mechanical)",
        "email": "wm.centralworkshop@kerala.gov.in",
        "phone": "+91 471 2490150",
        "category": "In-house Reconditioning & Salvage",
        "lead_time_days": 2,
        "status": "Active",
    },
]


def seed_database():
    """Idempotently populates the database with realistic KSRTC supply-chain data."""
    logger.info("Starting KSRTC database seed process...")
    init_db()

    with get_db_connection() as conn:
        with conn.transaction():
            # -------------------------------------------------------------
            # 1. Seed Parts and Inventory
            # -------------------------------------------------------------
            logger.info("Seeding parts and inventory...")
            part_id_map = {}
            for p in PARTS_DATA:
                row = conn.execute(
                    """INSERT INTO parts (sku, name, category, description, unit_cost, criticality)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (sku) DO UPDATE
                       SET name = EXCLUDED.name,
                           category = EXCLUDED.category,
                           description = EXCLUDED.description,
                           unit_cost = EXCLUDED.unit_cost,
                           criticality = EXCLUDED.criticality
                       RETURNING id, sku""",
                    (p["sku"], p["name"], p["category"], p["description"], p["unit_cost"], p["criticality"]),
                ).fetchone()

                part_id = row["id"]
                part_id_map[p["sku"]] = part_id

                # Upsert inventory
                conn.execute(
                    """INSERT INTO inventory (part_id, quantity, reorder_point, safety_stock, max_stock, updated_at)
                       VALUES (%s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (part_id) DO UPDATE
                       SET reorder_point = EXCLUDED.reorder_point,
                           safety_stock = EXCLUDED.safety_stock,
                           max_stock = EXCLUDED.max_stock,
                           updated_at = NOW()""",
                    (part_id, p["stock"], p["reorder_point"], p["safety_stock"], p["max_stock"]),
                )

            # -------------------------------------------------------------
            # 2. Seed Suppliers
            # -------------------------------------------------------------
            logger.info("Seeding suppliers...")
            supplier_id_map = {}
            for s in SUPPLIERS_DATA:
                row = conn.execute(
                    """INSERT INTO suppliers 
                       (supplier_code, supplier_name, contact_person, email, phone, category, lead_time_days, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (supplier_code) DO UPDATE
                       SET supplier_name = EXCLUDED.supplier_name,
                           contact_person = EXCLUDED.contact_person,
                           email = EXCLUDED.email,
                           phone = EXCLUDED.phone,
                           category = EXCLUDED.category,
                           lead_time_days = EXCLUDED.lead_time_days,
                           status = EXCLUDED.status
                       RETURNING id, supplier_code""",
                    (
                        s["supplier_code"],
                        s["supplier_name"],
                        s["contact_person"],
                        s["email"],
                        s["phone"],
                        s["category"],
                        s["lead_time_days"],
                        s["status"],
                    ),
                ).fetchone()
                supplier_id_map[s["supplier_code"]] = row["id"]

            # -------------------------------------------------------------
            # 3. Seed Supplier Parts Mappings (Prices & MOQs)
            # -------------------------------------------------------------
            logger.info("Seeding supplier-part pricing and lead time relationships...")
            mapping_rules = [
                # (sku, supplier_code, discount_factor, lead_days, moq)
                ("ENG-AL-001", "SUP-TVS-01", 0.95, 4, 10),
                ("ENG-AL-002", "SUP-TVS-01", 0.96, 4, 10),
                ("ENG-AL-003", "SUP-TVS-01", 0.98, 7, 1),
                ("ENG-AL-004", "SUP-TVS-01", 0.94, 5, 5),
                ("ENG-AL-005", "SUP-TVS-01", 0.95, 4, 10),
                ("BRK-AL-001", "SUP-BRL-02", 0.92, 6, 12),
                ("BRK-AL-002", "SUP-BRL-02", 0.95, 7, 4),
                ("BRK-AL-003", "SUP-BRL-02", 0.90, 5, 20),
                ("BRK-AL-004", "SUP-BRL-02", 0.93, 7, 5),
                ("TRN-AL-001", "SUP-TVS-01", 0.94, 6, 2),
                ("TRN-AL-002", "SUP-TVS-01", 0.95, 6, 2),
                ("TRN-AL-003", "SUP-CWS-08", 0.85, 2, 5),
                ("SUS-AL-001", "SUP-JAI-04", 0.93, 10, 4),
                ("SUS-AL-002", "SUP-JAI-04", 0.94, 8, 6),
                ("STG-AL-001", "SUP-TVS-01", 0.95, 5, 4),
                ("STG-AL-002", "SUP-TVS-01", 0.93, 5, 6),
                ("ELE-AL-001", "SUP-LUC-03", 0.92, 5, 2),
                ("ELE-AL-002", "SUP-LUC-03", 0.94, 5, 2),
                ("ELE-AL-003", "SUP-EXD-07", 0.91, 4, 4),
                ("TYR-AL-001", "SUP-MRF-05", 0.96, 3, 6),
                ("TYR-AL-002", "SUP-CWS-08", 0.70, 2, 10),
                ("TYR-AL-003", "SUP-MRF-05", 0.92, 3, 15),
                ("LUB-AL-001", "SUP-IOC-06", 0.90, 2, 10),
                ("LUB-AL-002", "SUP-IOC-06", 0.91, 3, 5),
                ("LUB-AL-003", "SUP-IOC-06", 0.88, 2, 8),
            ]

            for sku, sup_code, disc, l_days, moq in mapping_rules:
                if sku in part_id_map and sup_code in supplier_id_map:
                    pid = part_id_map[sku]
                    sid = supplier_id_map[sup_code]
                    base_cost = next(p["unit_cost"] for p in PARTS_DATA if p["sku"] == sku)
                    sup_price = round(base_cost * disc, 2)

                    conn.execute(
                        """INSERT INTO supplier_parts 
                           (supplier_id, part_id, supplier_unit_cost, lead_time_days, minimum_order_quantity)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (supplier_id, part_id) DO UPDATE
                           SET supplier_unit_cost = EXCLUDED.supplier_unit_cost,
                               lead_time_days = EXCLUDED.lead_time_days,
                               minimum_order_quantity = EXCLUDED.minimum_order_quantity""",
                        (sid, pid, sup_price, l_days, moq),
                    )

            # -------------------------------------------------------------
            # 4. Seed Demand History (90 Days for ML & Time Series Forecasting)
            # -------------------------------------------------------------
            logger.info("Seeding 90 days of daily consumption history for XGBoost forecasting...")
            today = date.today()
            random.seed(42)

            # Base daily consumption range per part
            consumption_profiles = {
                "ENG-AL-001": (1, 4),
                "ENG-AL-002": (1, 3),
                "ENG-AL-003": (0, 1),
                "ENG-AL-004": (0, 2),
                "ENG-AL-005": (1, 3),
                "BRK-AL-001": (2, 6),
                "BRK-AL-002": (0, 2),
                "BRK-AL-003": (1, 5),
                "BRK-AL-004": (0, 2),
                "TRN-AL-001": (0, 2),
                "TRN-AL-002": (0, 1),
                "TRN-AL-003": (0, 2),
                "SUS-AL-001": (0, 2),
                "SUS-AL-002": (1, 3),
                "STG-AL-001": (0, 2),
                "STG-AL-002": (1, 3),
                "ELE-AL-001": (0, 1),
                "ELE-AL-002": (0, 1),
                "ELE-AL-003": (0, 2),
                "TYR-AL-001": (1, 4),
                "TYR-AL-002": (2, 5),
                "TYR-AL-003": (1, 4),
                "LUB-AL-001": (2, 5),
                "LUB-AL-002": (1, 3),
                "LUB-AL-003": (1, 4),
            }

            for days_ago in range(90, 0, -1):
                cur_date = today - timedelta(days=days_ago)
                # Weekends have slightly lower maintenance turnover
                weekday_factor = 0.6 if cur_date.weekday() in (5, 6) else 1.0

                for sku, pid in part_id_map.items():
                    low, high = consumption_profiles.get(sku, (0, 2))
                    qty = int(round(random.randint(low, high) * weekday_factor))
                    if qty > 0:
                        conn.execute(
                            """INSERT INTO demand_history (part_id, date, quantity_consumed, depot)
                               VALUES (%s, %s, %s, %s)
                               ON CONFLICT (part_id, date, depot) DO UPDATE
                               SET quantity_consumed = EXCLUDED.quantity_consumed""",
                            (pid, cur_date, qty, DEPOT_NAME),
                        )

            # -------------------------------------------------------------
            # 5. Seed Purchase Orders and Items
            # -------------------------------------------------------------
            logger.info("Seeding realistic purchase orders...")
            po_samples = [
                {
                    "po_number": "PO-2026-0001",
                    "supplier_code": "SUP-BRL-02",
                    "status": "Received",
                    "days_ago": 15,
                    "expected_days": 8,
                    "received_days": 7,
                    "items": [
                        ("BRK-AL-001", 30, 4140.00),
                        ("BRK-AL-003", 40, 675.00),
                    ],
                },
                {
                    "po_number": "PO-2026-0002",
                    "supplier_code": "SUP-TVS-01",
                    "status": "Ordered",
                    "days_ago": 4,
                    "expected_days": -2,  # due in 2 days
                    "received_days": None,
                    "items": [
                        ("ENG-AL-001", 50, 807.50),
                        ("ENG-AL-002", 30, 1392.00),
                        ("TRN-AL-001", 10, 13630.00),
                    ],
                },
                {
                    "po_number": "PO-2026-0003",
                    "supplier_code": "SUP-MRF-05",
                    "status": "Draft",
                    "days_ago": 1,
                    "expected_days": -5,
                    "received_days": None,
                    "items": [
                        ("TYR-AL-001", 20, 31200.00),
                        ("TYR-AL-003", 30, 1656.00),
                    ],
                },
                {
                    "po_number": "PO-2026-0004",
                    "supplier_code": "SUP-IOC-06",
                    "status": "Received",
                    "days_ago": 28,
                    "expected_days": 25,
                    "received_days": 25,
                    "items": [
                        ("LUB-AL-001", 40, 4680.00),
                        ("LUB-AL-002", 20, 4368.00),
                    ],
                },
            ]

            for po_spec in po_samples:
                sid = supplier_id_map.get(po_spec["supplier_code"])
                order_dt = datetime.now(timezone.utc) - timedelta(days=po_spec["days_ago"])
                exp_dt = (
                    datetime.now(timezone.utc) - timedelta(days=po_spec["expected_days"])
                    if po_spec["expected_days"] >= 0
                    else datetime.now(timezone.utc) + timedelta(days=abs(po_spec["expected_days"]))
                )
                rec_dt = (
                    datetime.now(timezone.utc) - timedelta(days=po_spec["received_days"])
                    if po_spec["received_days"] is not None
                    else None
                )

                # Compute total
                tot = sum(qty * cost for _, qty, cost in po_spec["items"])

                po_row = conn.execute(
                    """INSERT INTO purchase_orders 
                       (po_number, supplier_id, status, order_date, expected_date, received_date, total_value)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (po_number) DO UPDATE
                       SET status = EXCLUDED.status,
                           total_value = EXCLUDED.total_value
                       RETURNING id""",
                    (po_spec["po_number"], sid, po_spec["status"], order_dt, exp_dt, rec_dt, tot),
                ).fetchone()

                poid = po_row["id"]
                # Clean existing items to allow idempotent re-seed
                conn.execute("DELETE FROM purchase_order_items WHERE purchase_order_id = %s", (poid,))

                for item_sku, qty, cost in po_spec["items"]:
                    pid = part_id_map[item_sku]
                    rec_qty = qty if po_spec["status"] == "Received" else 0
                    conn.execute(
                        """INSERT INTO purchase_order_items 
                           (purchase_order_id, part_id, quantity, unit_cost, received_quantity)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (poid, pid, qty, cost, rec_qty),
                    )

            # -------------------------------------------------------------
            # 6. Seed Model Run & Forecasts (XGBoost)
            # -------------------------------------------------------------
            logger.info("Seeding ML forecasting model run and forecast points...")
            mr_row = conn.execute(
                """INSERT INTO model_runs (model_name, model_version, status, metrics_json)
                   VALUES ('XGBoost-Demand-Predictor', 'v1.2', 'SUCCESS', %s::jsonb)
                   RETURNING id""",
                (
                    '{"mae": 1.42, "rmse": 2.18, "mape": 9.4, "horizon_days": 30, "algorithm": "Extreme Gradient Boosting Regressor", "feature_importance": {"lag_7": 0.35, "rolling_avg_14": 0.28, "day_of_week": 0.21, "lead_time": 0.16}}',
                ),
            ).fetchone()

            # Clean older forecasts before inserting fresh 30-day forecast points
            conn.execute("DELETE FROM forecasts WHERE model_name = 'XGBoost-Demand-Predictor'")
            for days_ahead in range(1, 31):
                fc_date = today + timedelta(days=days_ahead)
                for sku, pid in part_id_map.items():
                    low, high = consumption_profiles.get(sku, (1, 3))
                    fc_qty = round(random.uniform(low, high * 1.1), 1)
                    conn.execute(
                        """INSERT INTO forecasts (part_id, forecast_date, forecast_quantity, model_name, model_version)
                           VALUES (%s, %s, %s, 'XGBoost-Demand-Predictor', 'v1.2')""",
                        (pid, fc_date, fc_qty),
                    )

            # -------------------------------------------------------------
            # 7. Seed PuLP Procurement Optimization Recommendations
            # -------------------------------------------------------------
            logger.info("Seeding PuLP procurement optimization recommendations...")
            conn.execute("DELETE FROM procurement_recommendations WHERE model_name = 'PuLP-Procurement-Optimizer'")

            pulp_recommendations = [
                {
                    "sku": "BRK-AL-001",
                    "qty": 35,
                    "cost": 4140.00,
                    "priority": "Critical",
                    "reason": "Stock (12) is below Safety Stock (25). High demand projected for brake linings during monsoon operations.",
                },
                {
                    "sku": "ENG-AL-002",
                    "qty": 25,
                    "cost": 1392.00,
                    "priority": "Critical",
                    "reason": "Stock (14) breached safety threshold (20). High fuel contamination risk requires scheduled filter changes.",
                },
                {
                    "sku": "TRN-AL-001",
                    "qty": 15,
                    "cost": 13630.00,
                    "priority": "High",
                    "reason": "On-hand stock (5) below reorder level (18). Essential component to prevent bus breakdown on city routes.",
                },
                {
                    "sku": "SUS-AL-001",
                    "qty": 12,
                    "cost": 8556.00,
                    "priority": "High",
                    "reason": "Stock level (7) below safety stock (10). Parabolic springs required for scheduled chassis maintenance.",
                },
                {
                    "sku": "ELE-AL-003",
                    "qty": 14,
                    "cost": 16835.00,
                    "priority": "Medium",
                    "reason": "Stockout risk elevated. Buffer needed for early morning cold start replacements.",
                },
                {
                    "sku": "TYR-AL-001",
                    "qty": 18,
                    "cost": 31200.00,
                    "priority": "Critical",
                    "reason": "Front axle tubeless tyres depleted (14 units on hand, reorder point 30). Statutory safety requirement.",
                },
                {
                    "sku": "LUB-AL-001",
                    "qty": 20,
                    "cost": 4680.00,
                    "priority": "Medium",
                    "reason": "Stock below reorder point (45). Bulk replenishment optimal for price tier discount.",
                },
            ]

            for rec in pulp_recommendations:
                pid = part_id_map[rec["sku"]]
                est_tot = round(rec["qty"] * rec["cost"], 2)
                conn.execute(
                    """INSERT INTO procurement_recommendations 
                       (part_id, recommended_quantity, unit_cost, estimated_cost, priority, reason, model_name)
                       VALUES (%s, %s, %s, %s, %s, %s, 'PuLP-Procurement-Optimizer')""",
                    (pid, rec["qty"], rec["cost"], est_tot, rec["priority"], rec["reason"]),
                )

            # -------------------------------------------------------------
            # 8. Seed Initial Audit Transactions
            # -------------------------------------------------------------
            logger.info("Seeding initial inventory audit transactions...")
            for sku in ["BRK-AL-001", "ENG-AL-002", "TYR-AL-001", "LUB-AL-001"]:
                pid = part_id_map[sku]
                conn.execute(
                    """INSERT INTO inventory_transactions 
                       (part_id, transaction_type, quantity, reference_type, reference_id, transaction_date, notes)
                       VALUES (%s, 'ADJUSTMENT', %s, 'INITIAL_AUDIT', 'SEED_VERIFY', NOW() - INTERVAL '30 days', 'Initial physical stock audit at Central Depot')""",
                    (pid, PARTS_DATA[0]["stock"]),
                )

    logger.info("Successfully completed database seeding!")
    logger.info("KSRTC Central Depot PostgreSQL database is now fully populated.")


if __name__ == "__main__":
    try:
        seed_database()
        print("SEED SUCCESS: All KSRTC parts, inventory, suppliers, POs, and forecasts seeded.")
    except Exception as e:
        logger.error(f"Seed failed with error: {e}", exc_info=True)
        sys.exit(1)
